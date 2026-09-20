import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionLead,
    CompetitionPolicyRecognition,
    CompetitionSource,
    PolicyDocument,
    PolicyRawItem,
    Tag,
    University,
)

REPORT_PATH = PROJECT_ROOT / "data" / "reports" / "v04_fact_intelligence_acceptance_report.json"
PRE_V04_TOTAL = 121


def count(db, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def main() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        visible = list(
            db.execute(
                select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
            ).scalars()
        )
        visible_ids = {item.id for item in visible}
        raw_items = list(db.execute(select(PolicyRawItem)).scalars())
        leads = list(db.execute(select(CompetitionLead)).scalars())
        sources = list(db.execute(select(CompetitionSource).where(CompetitionSource.is_demo.is_(False))).scalars())
        editions = list(db.execute(select(CompetitionEdition)).scalars())
        source_types = Counter(source.source_type for source in sources)
        lead_types = Counter(lead.source_type for lead in leads)
        entity_types = Counter(item.entity_type for item in raw_items)
        verification = Counter(item.verification_status for item in visible)
        fact_sources = list(db.execute(select(CompetitionFactSource)).scalars())

        next_30_deadlines = 0
        next_90_openings = 0
        for edition in editions:
            if edition.competition_id not in visible_ids or not edition.is_verified:
                continue
            deadlines = [value for value in (edition.registration_deadline, edition.submission_deadline) if value and value >= now]
            if deadlines and min(deadlines) <= now + timedelta(days=30):
                next_30_deadlines += 1
            if edition.registration_start and now <= edition.registration_start <= now + timedelta(days=90):
                next_90_openings += 1

        complete_detail = sum(
            bool(item.organizer and item.official_website and item.description and item.category)
            and any(edition.is_verified for edition in item.editions)
            for item in visible
        )
        wut_source_competitions = {
            source.competition_id
            for source in sources
            if source.source_url.startswith("local-source://wuhan-sports-university")
        }
        source_competition_map: dict[int, list[CompetitionSource]] = {}
        for source in sources:
            if source.competition_id:
                source_competition_map.setdefault(source.competition_id, []).append(source)
        wut_only = sum(
            all(source.source_url.startswith("local-source://wuhan-sports-university") for source in source_competition_map[item_id])
            for item_id in wut_source_competitions
        )
        university_names = {
            (lead.metadata_json or {}).get("university")
            for lead in leads
            if lead.source_type == "university_official" and (lead.metadata_json or {}).get("university")
        }
        github_leads = [
            lead for lead in leads if (lead.metadata_json or {}).get("repository") == "Nemoyuzx/contest-ddl"
        ]
        wechat_leads = [lead for lead in leads if "wechat" in (lead.source_platform or "").lower()]
        official_site_sources = [
            source
            for source in sources
            if source.source_platform == "official_website"
            or source.source_type in {"official_notice", "competition_official", "organizer_official_notice"}
        ]
        other_university_sources = [
            source
            for source in sources
            if source.source_type in {"university_policy", "university_official", "university_official_notice"}
            and not source.source_url.startswith("local-source://wuhan-sports-university")
        ]
        registration_open = sum(
            edition.is_verified
            and edition.current_status == "registration_open"
            and edition.registration_deadline is not None
            and edition.registration_deadline >= now
            for edition in editions
        )
        policy_985_coverage = count(
            db,
            PolicyDocument,
            PolicyDocument.is_demo.is_(False),
            PolicyDocument.is_verified.is_(True),
            PolicyDocument.university_id.in_(
                select(University.id).where(University.is_985.is_(True), University.is_demo.is_(False))
            ),
        )
        covered_985_universities = int(
            db.scalar(
                select(func.count(func.distinct(PolicyDocument.university_id))).where(
                    PolicyDocument.is_demo.is_(False),
                    PolicyDocument.is_verified.is_(True),
                    PolicyDocument.university_id.in_(
                        select(University.id).where(University.is_985.is_(True), University.is_demo.is_(False))
                    ),
                )
            )
            or 0
        )

        github_projects = [
            {"repository": "Tomzkl/college-competitions-skill", "license": "MIT", "status": "imported_seed"},
            {"repository": "Nemoyuzx/contest-ddl", "license": "MIT", "status": "imported_as_leads"},
            {"repository": "xcg1125/college-competition-ddl", "license": "not_confirmed", "status": "not_imported"},
            {"repository": "Freedomisgood/Competition-Yellow-Pages", "license": "not_confirmed", "status": "not_imported_stale"},
            {"repository": "kelin-gpu/campus-competition-agent", "license": "not_confirmed", "status": "not_imported"},
        ]

        acceptance = {
            "01_competition_total": len(visible),
            "02_new_competitions": count(db, Competition, Competition.id > PRE_V04_TOTAL),
            "03_cleaned_non_competition_entities": sum(not item.is_competition for item in db.execute(select(Competition)).scalars()),
            "04_awards": entity_types["award"],
            "05_activities": entity_types["activity"] + entity_types["festival"],
            "06_exhibitions": entity_types["exhibition"],
            "07_unknown": entity_types["unknown"],
            "08_aliases": count(db, CompetitionAlias, CompetitionAlias.is_demo.is_(False)),
            "09_parents": count(db, Competition, Competition.competition_type == "series", Competition.is_competition.is_(True)),
            "10_children": count(db, Competition, Competition.parent_competition_id.is_not(None), Competition.is_competition.is_(True)),
            "11_tags": count(db, Tag),
            "12_source_distribution": {
                "competition_sources": dict(sorted(source_types.items())),
                "lead_sources": dict(sorted(lead_types.items())),
                "fact_sources": dict(sorted(Counter(source.source_type for source in fact_sources).items())),
            },
            "13_wuhan_sports_only_sources": wut_only,
            "14_github_sources": {
                "existing_competition_source_records": source_types["github_seed"] + source_types["github"],
                "v04_discovery_leads": len(github_leads),
                "accepted_projects": 2,
            },
            "15_other_university_sources": len(other_university_sources) + lead_types["university_official"],
            "16_official_site_sources": len(official_site_sources),
            "17_university_wechat_leads": 0,
            "18_event_wechat_leads": 0,
            "19_platform_leads": lead_types["third_party_platform"],
            "20_social_leads": lead_types["social"],
            "21_multi_source_verified_competitions": verification["verified_multi_source"],
            "22_verified_official": verification["verified_official"],
            "23_verified_multi_source": verification["verified_multi_source"],
            "24_secondary_source_only": verification["secondary_source_only"],
            "25_unverified": verification["unverified"],
            "26_suspected": verification["suspected"],
            "27_editions": len(editions),
            "28_2026_editions": sum(edition.year == 2026 for edition in editions),
            "29_registration_open": registration_open,
            "30_deadlines_within_30_days": next_30_deadlines,
            "31_openings_within_90_days": next_90_openings,
            "32_organizer_present": sum(bool(item.organizer) for item in visible),
            "33_official_site_present": sum(bool(item.official_website) for item in visible),
            "34_founded_year_present": sum(bool(item.founded_year) for item in visible),
            "35_description_present": sum(bool(item.description) for item in visible),
            "36_complete_detail_count": complete_detail,
            "37_policy_documents": count(db, PolicyDocument, PolicyDocument.is_demo.is_(False)),
            "38_school_college_relations": count(
                db, CompetitionPolicyRecognition, CompetitionPolicyRecognition.is_demo.is_(False)
            ),
            "39_985_coverage": f"{covered_985_universities}/39",
            "40_universities_actually_crawled": {"count": len(university_names), "names": sorted(university_names)},
            "41_real_github_projects": {"searched": len(github_projects), "accepted": 2, "projects": github_projects},
            "42_wechat_leads": len(wechat_leads),
            "43_third_party_platform_leads": lead_types["third_party_platform"],
            "44_ultimately_verified_competitions": verification["verified_official"] + verification["verified_multi_source"],
        }
        report = {
            "version": "V0.4",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "definitions": {
                "competition_total": "is_demo=false and is_competition=true",
                "activities": "activity and festival entities grouped for the requested 44-item report",
                "ultimately_verified": "verified_official + verified_multi_source",
                "github_discovery": "third-party data remains in CompetitionLead until independently verified",
            },
            "acceptance": acceptance,
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
