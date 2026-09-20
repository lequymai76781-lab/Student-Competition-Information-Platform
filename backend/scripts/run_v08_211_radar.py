import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionLead,
    CompetitionSource,
    University,
    UniversityCompetitionEditionRelation,
)
from app.repositories.stats_repository import StatsRepository
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.competition_discovery_service import CompetitionDiscoveryService
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and import V0.8 non-985 211 university competition notices.")
    parser.add_argument(
        "--universities",
        default=str(PROJECT_ROOT / "data" / "seeds" / "211_non_985_universities.json"),
    )
    parser.add_argument(
        "--seed",
        default=str(PROJECT_ROOT / "data" / "seeds" / "v08_211_radar_discovery.json"),
    )
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "data" / "reports" / "v08_211_radar_report.json"),
    )
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--import-only", action="store_true")
    args = parser.parse_args()

    universities_path = Path(args.universities)
    seed_path = Path(args.seed)
    report_path = Path(args.report)
    directory = json.loads(universities_path.read_text(encoding="utf-8"))
    university_rows = directory["universities"]

    with SessionLocal() as db:
        if not args.import_only:
            radar = UniversityRadarDiscoveryService()
            try:
                payload = radar.discover(db, university_rows)
            finally:
                radar.close()
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.discover_only:
                print(json.dumps(discovery_snapshot(payload), ensure_ascii=False, indent=2))
                return
        else:
            payload = json.loads(seed_path.read_text(encoding="utf-8"))

        importer = CompetitionDiscoveryImportService()
        fact_service = FactIntelligenceService()
        intelligence = CompetitionIntelligenceService()
        batch_results = []
        for batch in payload.get("batches", []):
            result = importer.import_json(db, seed_path, universities_path, batch_name=batch["name"])
            result["source_tiers"] = fact_service.refresh_source_tiers(db)
            result["verification"] = fact_service.refresh_verification(db)
            db.commit()
            batch_results.append({"batch": batch["name"], **result})

        tags = intelligence.apply_tags(db)
        statistics = intelligence.refresh_all(db)
        freshness = CompetitionFreshnessService().refresh_all(db)
        db.commit()
        coverage = CompetitionDiscoveryService().v08_coverage_summary(db)
        report = {
            "version": "v0.8",
            "directory": {
                "scope": directory.get("scope"),
                "expected_count": directory.get("expected_count"),
                "actual_count": len(university_rows),
                "source_url": directory.get("directory_source_url"),
            },
            "discovery": discovery_snapshot(payload),
            "batches": batch_results,
            "freshness": freshness,
            "tags": tags,
            "statistics": statistics,
            "platform_stats": StatsRepository().get_platform_stats(db),
            "coverage": coverage,
            "source_diversity": source_diversity(db),
            "database_counts": database_counts(db),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def discovery_snapshot(payload: dict) -> dict:
    reports = payload.get("discovery_reports", [])
    admitted_urls = {item.get("source_url") for item in payload.get("official_records", [])}
    return {
        "batch_count": len(payload.get("batches", [])),
        "school_count": len(reports),
        "status_counts": dict(Counter(item["status"] for item in reports)),
        "lead_count": len(payload.get("leads", [])),
        "verified_official_leads": sum(
            item.get("verification_status") == "verified_official" for item in payload.get("leads", [])
        ),
        "wechat_leads": sum(item.get("source_platform") == "wechat_search" for item in payload.get("leads", [])),
        "matched_leads": sum(
            bool(item.get("detected_competition_name")) or item.get("source_url") in admitted_urls
            for item in payload.get("leads", [])
        ),
        "edition_relations": len(payload.get("edition_relations", [])),
        "new_competitions": len(payload.get("official_records", [])),
        "schools": reports,
    }


def source_diversity(db) -> dict:
    sources = list(db.execute(select(CompetitionSource).where(CompetitionSource.is_demo.is_(False))).scalars())
    leads = list(db.execute(select(CompetitionLead)).scalars())
    domains = {urlparse(source.source_url).netloc.lower() for source in sources if urlparse(source.source_url).netloc}
    source_types_by_competition: dict[int, set[str]] = {}
    for source in sources:
        if source.competition_id:
            source_types_by_competition.setdefault(source.competition_id, set()).add(source.source_type)
    return {
        "competition_source_types": dict(Counter(source.source_type for source in sources)),
        "lead_source_types": dict(Counter(lead.source_type for lead in leads)),
        "lead_platforms": dict(Counter(lead.source_platform or "unknown" for lead in leads)),
        "lead_source_scopes": dict(
            Counter((lead.metadata_json or {}).get("source_scope") or "unspecified" for lead in leads)
        ),
        "unique_source_domains": len(domains),
        "competitions_with_two_source_types": sum(len(types) >= 2 for types in source_types_by_competition.values()),
    }


def database_counts(db) -> dict:
    models = {
        "universities": University,
        "competitions": Competition,
        "competition_editions": CompetitionEdition,
        "competition_leads": CompetitionLead,
        "competition_sources": CompetitionSource,
        "university_competition_edition_relations": UniversityCompetitionEditionRelation,
        "competition_fact_revisions": CompetitionFactRevision,
    }
    return {name: db.scalar(select(func.count()).select_from(model)) or 0 for name, model in models.items()}


if __name__ == "__main__":
    main()
