"""Apply the reverse QA for the previous 13 competitions and resolve two uncertain event semantics."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.database.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionSource,
    UniversityCompetitionEditionRelation,
)

REVIEW = ROOT / "data/reports/specialized_previous_13_review.json"
UNCERTAIN = ROOT / "data/reports/specialized_uncertain_resolutions.json"
RESULT = ROOT / "data/reports/specialized_reverse_audit_result.json"


def digest(*parts: str) -> str:
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()


def ensure_source(db, competition: Competition, url: str, name: str, title: str, content: str, now: datetime) -> int:
    found = db.scalar(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == url,
            CompetitionSource.source_type == "professional_institution_official",
        )
    )
    if found:
        return 0
    db.add(
        CompetitionSource(
            competition_id=competition.id,
            source_type="professional_institution_official",
            authority_level="A2",
            source_name=name,
            source_url=url,
            source_platform="official_website",
            retrieved_at=now,
            is_official=True,
            is_verified=True,
            credibility_score=90,
            reliability_tier=2,
            verification_status="verified_official",
            raw_title=title,
            raw_content=content,
            content_hash=digest(url, content),
            metadata_json={"task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01", "audit": "previous_13"},
        )
    )
    return 1


def ensure_fact(db, competition: Competition, edition: CompetitionEdition | None, field: str, value: dict, url: str, source_name: str, note: str, now: datetime) -> int:
    found = db.scalar(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == competition.id,
            CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
            CompetitionFactSource.field_name == field,
            CompetitionFactSource.source_url == url,
        )
    )
    if found:
        return 0
    db.add(
        CompetitionFactSource(
            competition_id=competition.id,
            competition_edition_id=edition.id if edition else None,
            field_name=field,
            fact_value=value,
            source_type="professional_institution_official",
            source_name=source_name,
            source_url=url,
            reliability_tier=2,
            source_level="B",
            is_official=True,
            verification_status="verified_official",
            observed_at=now,
            last_verified_at=now,
            source_hash=digest(url, field, json.dumps(value, ensure_ascii=False)),
            notes=note,
        )
    )
    return 1


def delete_isolated_previous_competition(db, competition: Competition) -> dict:
    edition_ids = list(
        db.scalars(select(CompetitionEdition.id).where(CompetitionEdition.competition_id == competition.id))
    )
    relations = list(
        db.scalars(
            select(UniversityCompetitionEditionRelation).where(
                UniversityCompetitionEditionRelation.competition_edition_id.in_(edition_ids)
            )
        )
    ) if edition_ids else []
    if any((item.metadata_json or {}).get("task") != "SPECIALIZED_INSTITUTIONS_COVERAGE_01" for item in relations):
        raise RuntimeError(f"refusing to delete {competition.name}: relation outside this task")
    deleted = {"relations": len(relations), "editions": len(edition_ids), "direct_references": {}}
    if edition_ids:
        db.execute(
            delete(UniversityCompetitionEditionRelation).where(
                UniversityCompetitionEditionRelation.competition_edition_id.in_(edition_ids)
            )
        )
        db.execute(
            delete(CompetitionFactSource).where(
                CompetitionFactSource.competition_edition_id.in_(edition_ids)
            )
        )
        db.execute(
            delete(CompetitionSource).where(CompetitionSource.competition_edition_id.in_(edition_ids))
        )
    seen_tables: set[str] = set()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "competitions" or table.name in seen_tables:
            continue
        columns = [fk.parent for fk in table.foreign_keys if fk.target_fullname == "competitions.id"]
        if not columns:
            continue
        seen_tables.add(table.name)
        count = 0
        for column in columns:
            result = db.execute(delete(table).where(column == competition.id))
            count += result.rowcount or 0
        if count:
            deleted["direct_references"][table.name] = count
    db.execute(delete(Competition).where(Competition.id == competition.id))
    return deleted


def apply_previous_review(db, items: list[dict], now: datetime) -> tuple[list[dict], int]:
    outcomes = []
    sources_created = 0
    for item in items:
        competition = db.scalar(select(Competition).where(Competition.name == item["competition"]))
        if competition is None:
            outcomes.append({**item, "result": "ALREADY_REMOVED"})
            continue
        if item["action"] == "DELETE":
            deletion = delete_isolated_previous_competition(db, competition)
            outcomes.append({**item, "result": "DELETED", "deletion": deletion})
            continue
        old_url = competition.description_source_url
        competition.organizer = item["organizer"]
        competition.competition_type = item["event_type"]
        competition.entity_type = "competition"
        competition.is_competition = True
        competition.description_source_url = item["source_url"]
        competition.last_verified_at = now
        editions = list(
            db.scalars(select(CompetitionEdition).where(CompetitionEdition.competition_id == competition.id))
        )
        for edition in editions:
            edition.source_url = item["source_url"]
            edition.last_verified_at = now
        relations = []
        if editions:
            relations = list(
                db.scalars(
                    select(UniversityCompetitionEditionRelation).where(
                        UniversityCompetitionEditionRelation.competition_edition_id.in_([edition.id for edition in editions])
                    )
                )
            )
        for relation in relations:
            if relation.internal_notice_url == old_url:
                relation.internal_notice_url = item["source_url"]
                relation.last_verified_at = now
                relation.source_hash = digest(item["source_url"], relation.notice_title or "")
        facts = list(
            db.scalars(select(CompetitionFactSource).where(CompetitionFactSource.competition_id == competition.id))
        )
        for fact in facts:
            if fact.source_url == old_url:
                fact.source_url = item["source_url"]
                fact.last_verified_at = now
        sources_created += ensure_source(
            db, competition, item["source_url"], item["source_name"], item["competition"], item["reason"], now
        )
        sources_created += ensure_fact(
            db,
            competition,
            editions[0] if editions else None,
            "organizer",
            {"value": item["organizer"]},
            item["source_url"],
            item["source_name"],
            item["reason"],
            now,
        )
        sources_created += ensure_fact(
            db,
            competition,
            editions[0] if editions else None,
            "event_type",
            {"value": item["event_type"]},
            item["source_url"],
            item["source_name"],
            item["reason"],
            now,
        )
        outcomes.append({**item, "result": "PASS_AFTER_CORRECTION"})
    return outcomes, sources_created


def ensure_semantic_edition(db, competition: Competition, year: int, event_type: str, url: str, source_name: str, reason: str, now: datetime) -> int:
    edition = db.scalar(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition.id,
            CompetitionEdition.year == year,
        )
    )
    created = 0
    if edition is None:
        edition = CompetitionEdition(
            competition_id=competition.id,
            year=year,
            edition_name=f"{year}年{competition.name}",
            source_url=url,
            verification_status="verified_official",
            is_verified=True,
            last_verified_at=now,
        )
        db.add(edition)
        db.flush()
        created += 1
    created += ensure_fact(
        db,
        competition,
        edition,
        "event_type",
        {"value": event_type, "edition_specific": True},
        url,
        source_name,
        reason,
        now,
    )
    return created


def apply_uncertain_resolutions(db, items: list[dict], now: datetime) -> tuple[list[dict], int]:
    outcomes = []
    created = 0
    for item in items:
        competition = db.scalar(select(Competition).where(Competition.name == item["competition"]))
        if competition is None:
            competition = db.scalar(select(Competition).where(Competition.name == item["canonical_name"]))
        if competition is None:
            raise RuntimeError(f"missing uncertain competition {item['competition']}")
        former = list(competition.former_names or [])
        if competition.name != item["canonical_name"] and competition.name not in former:
            former.append(competition.name)
        competition.name = item["canonical_name"]
        competition.former_names = former or None
        competition.organizer = item["organizer"]
        competition.competition_type = item["current_event_type"]
        competition.entity_type = "event"
        competition.is_competition = False
        competition.description_source_url = item["current_source_url"]
        competition.last_verified_at = now
        created += ensure_source(
            db,
            competition,
            item["current_source_url"],
            "官方主办方",
            item["canonical_name"],
            item["reason"],
            now,
        )
        created += ensure_source(
            db,
            competition,
            item["historical_source_url"],
            "官方主办方",
            f"{item['canonical_name']}历史届次",
            item["reason"],
            now,
        )
        historical_year = 2012 if "桃李杯" in item["canonical_name"] else 2015
        created += ensure_semantic_edition(
            db,
            competition,
            historical_year,
            item["historical_event_type"],
            item["historical_source_url"],
            "官方主办方",
            item["reason"],
            now,
        )
        created += ensure_semantic_edition(
            db,
            competition,
            2026,
            item["current_event_type"],
            item["current_source_url"],
            "官方主办方",
            item["reason"],
            now,
        )
        outcomes.append({**item, "applied": True})
    return outcomes, created


def main() -> None:
    review_items = json.loads(REVIEW.read_text(encoding="utf-8"))["items"]
    uncertain_items = json.loads(UNCERTAIN.read_text(encoding="utf-8"))["items"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        previous_outcomes, previous_created = apply_previous_review(db, review_items, now)
        uncertain_outcomes, semantic_created = apply_uncertain_resolutions(db, uncertain_items, now)
        db.commit()
    result = {
        "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
        "generated_at": now.isoformat(),
        "previous_13": {
            "reviewed": len(previous_outcomes),
            "pass_after_correction": sum(item["result"] == "PASS_AFTER_CORRECTION" for item in previous_outcomes),
            "deleted": sum(item["result"] == "DELETED" for item in previous_outcomes),
            "outcomes": previous_outcomes,
        },
        "uncertain": {
            "resolved": len(uncertain_outcomes),
            "remaining_uncertain": 0,
            "outcomes": uncertain_outcomes,
        },
        "audit_evidence_created": previous_created + semantic_created,
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "previous_13": result["previous_13"],
        "uncertain_resolved": result["uncertain"]["resolved"],
        "audit_evidence_created": result["audit_evidence_created"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
