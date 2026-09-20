from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionLead,
    CompetitionTrack,
    ReviewQueue,
    UniversityCompetitionEditionRelation,
)
from app.repositories.stats_repository import StatsRepository
from app.services.competition_detail_enrichment_service import CompetitionDetailEnrichmentService
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.competition_discovery_service import CompetitionDiscoveryService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.fact_intelligence_service import FactIntelligenceService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V0.7 discovery acceptance and competition detail enrichment.")
    parser.add_argument(
        "--recheck-seed",
        default=str(PROJECT_ROOT / "data" / "seeds" / "v07_partial_rechecks.json"),
    )
    parser.add_argument(
        "--universities",
        default=str(PROJECT_ROOT / "data" / "seeds" / "985_universities.json"),
    )
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "data" / "reports" / "v07_competition_enrichment_acceptance_report.json"),
    )
    parser.add_argument("--common-limit", type=int, default=30)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    seed_path = Path(args.recheck_seed)
    universities_path = Path(args.universities)
    report_path = Path(args.report)

    importer = CompetitionDiscoveryImportService()
    enrichment = CompetitionDetailEnrichmentService()
    fact_service = FactIntelligenceService()
    intelligence = CompetitionIntelligenceService()
    discovery = CompetitionDiscoveryService()

    with SessionLocal() as db:
        recheck = importer.import_json(
            db,
            seed_path,
            universities_path,
            batch_name="v07-partial-recheck",
        )
        db.commit()
        enrichment_result = enrichment.run(db, common_limit=max(args.common_limit, 30))
        fact_service.refresh_source_tiers(db)
        fact_service.refresh_verification(db)
        db.commit()
        intelligence.apply_tags(db)
        intelligence.refresh_all(db)
        db.commit()

        report = {
            "version": "v0.7",
            "recheck_seed": seed_path.name,
            "partial_recheck": recheck,
            "enrichment_pipeline": enrichment_result,
            "platform_stats": StatsRepository().get_platform_stats(db),
            "discovery_coverage": discovery.coverage_summary(db),
            "detail_completeness": detail_completeness(db),
            "v06_new_competition_audit": v06_new_competition_audit(db, enrichment_result),
            "deadline_acceptance": deadline_acceptance(db),
            "random_detail_acceptance": random_detail_acceptance(db),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def detail_completeness(db) -> dict[str, int]:
    competitions = list(
        db.execute(
            select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
        ).scalars()
    )
    editions = list(db.execute(select(CompetitionEdition)).scalars())
    relations = list(db.execute(select(UniversityCompetitionEditionRelation)).scalars())
    action_relations = [
        relation
        for relation in relations
        if relation.notice_type in {"registration_notice", "internal_selection", "submission_notice"}
    ]
    return {
        "competitions": len(competitions),
        "with_description": _present(competitions, "description"),
        "with_organizer": _present(competitions, "organizer"),
        "with_official_website": _present(competitions, "official_website"),
        "with_official_account": _present(competitions, "official_account"),
        "with_founded_year": sum(item.founded_year is not None for item in competitions),
        "with_frequency": _present(competitions, "frequency"),
        "with_target_students": _present(competitions, "target_students"),
        "with_team_rules": sum(
            item.team_type not in (None, "")
            and (item.team_type == "个人赛" or item.min_team_size is not None or item.max_team_size is not None)
            for item in competitions
        ),
        "with_competition_format": _present(competitions, "competition_format"),
        "with_tracks": db.scalar(select(func.count(func.distinct(CompetitionTrack.competition_id)))) or 0,
        "with_2026_edition": len({edition.competition_id for edition in editions if edition.year == 2026}),
        "with_official_registration_url": len(
            {edition.competition_id for edition in editions if edition.official_registration_url}
        ),
        "with_official_registration_deadline": len(
            {edition.competition_id for edition in editions if edition.official_registration_deadline}
        ),
        "with_university_internal_deadline": len(
            {
                relation.competition_edition_id
                for relation in action_relations
                if relation.college_id is None and relation.internal_registration_deadline is not None
            }
        ),
        "with_college_internal_deadline": len(
            {
                relation.competition_edition_id
                for relation in action_relations
                if relation.college_id is not None
                and (relation.college_registration_deadline or relation.internal_registration_deadline)
            }
        ),
        "field_fact_sources": db.scalar(select(func.count()).select_from(CompetitionFactSource)) or 0,
    }


def v06_new_competition_audit(db, enrichment_result: dict) -> dict[str, object]:
    competitions = list(db.execute(select(Competition).where(Competition.id.between(119, 141))).scalars())
    confirmed = [
        item
        for item in competitions
        if item.verification_status in {"verified_official", "verified_multi_source"}
    ]
    return {
        "v06_new_competitions": len(competitions),
        "confirmed_real": len(confirmed),
        "duplicate_merged": 0,
        "university_scope": sum(item.competition_scope == "university" for item in competitions),
        "tracks": sum(item.competition_type == "track" for item in competitions),
        "non_competition": sum(not item.is_competition for item in competitions),
        "pending_review": sum(item.verification_status in {"unverified", "suspected", "conflicting"} for item in competitions),
        "duplicate_groups": enrichment_result.get("duplicate_groups", []),
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "competition_type": item.competition_type,
                "competition_scope": item.competition_scope,
                "verification_status": item.verification_status,
            }
            for item in competitions
        ],
    }


def deadline_acceptance(db) -> dict[str, int]:
    editions = list(db.execute(select(CompetitionEdition)).scalars())
    relations = list(db.execute(select(UniversityCompetitionEditionRelation)).scalars())
    action_relations = [
        relation
        for relation in relations
        if relation.notice_type in {"registration_notice", "internal_selection", "submission_notice"}
    ]
    university_by_edition = {
        relation.competition_edition_id
        for relation in action_relations
        if relation.college_id is None and relation.internal_registration_deadline is not None
    }
    college_by_edition = {
        relation.competition_edition_id
        for relation in action_relations
        if relation.college_id is not None
        and (relation.college_registration_deadline or relation.internal_registration_deadline)
    }
    official_by_edition = {edition.id for edition in editions if edition.official_registration_deadline is not None}
    return {
        "university_competition_edition_relations": len(relations),
        "college_relations": sum(relation.college_id is not None for relation in relations),
        "official_and_university_deadline": len(official_by_edition & university_by_edition),
        "official_university_college_deadline": len(
            official_by_edition & university_by_edition & college_by_edition
        ),
        "registration_notice": sum(relation.notice_type == "registration_notice" for relation in relations),
        "internal_selection": sum(relation.notice_type == "internal_selection" for relation in relations),
        "submission_notice": sum(relation.notice_type == "submission_notice" for relation in relations),
        "award_news": sum(relation.notice_type == "award_news" for relation in relations),
    }


def random_detail_acceptance(db) -> list[dict[str, object]]:
    active_ids = list(
        db.execute(
            select(Competition.id)
            .join(CompetitionEdition)
            .where(CompetitionEdition.current_status.in_(["registration_open", "submission_open"]))
            .order_by(Competition.id)
            .limit(10)
        ).scalars()
    )
    if len(active_ids) < 10:
        extra_ids = list(
            db.execute(
                select(Competition.id)
                .where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
                .order_by(Competition.id)
            ).scalars()
        )
        active_ids.extend(item for item in extra_ids if item not in active_ids)
    competitions = list(
        db.execute(select(Competition).where(Competition.id.in_(active_ids[:10])).order_by(Competition.id)).scalars()
    )
    result = []
    for item in competitions:
        editions = list(db.execute(select(CompetitionEdition).where(CompetitionEdition.competition_id == item.id)).scalars())
        source_fields = {
            field
            for field in db.execute(
                select(CompetitionFactSource.field_name).where(CompetitionFactSource.competition_id == item.id)
            ).scalars()
        }
        result.append(
            {
                "competition_id": item.id,
                "name": item.name,
                "has_description": bool(item.description),
                "has_organizer": bool(item.organizer),
                "has_history": bool(item.founded_year or item.first_held_year or item.frequency or item.development_history),
                "has_participant_rules": bool(item.target_students or item.team_type),
                "has_format_or_tracks": bool(item.competition_format or item.tracks),
                "has_2026_edition": any(edition.year == 2026 for edition in editions),
                "has_registration_path": any(edition.official_registration_url for edition in editions),
                "traceable_fields": len(source_fields),
            }
        )
    return result


def _present(items: list[Competition], field_name: str) -> int:
    return sum(getattr(item, field_name, None) not in (None, "", []) for item in items)


if __name__ == "__main__":
    main()
