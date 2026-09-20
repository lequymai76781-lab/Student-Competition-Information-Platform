import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionLead, CompetitionSource, UniversityCompetitionEditionRelation
from app.repositories.stats_repository import StatsRepository
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.competition_discovery_service import CompetitionDiscoveryService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.fact_intelligence_service import FactIntelligenceService


def main() -> None:
    parser = argparse.ArgumentParser(description="Import V0.6 985 competition discovery seed in batches.")
    parser.add_argument(
        "--seed",
        default=str(PROJECT_ROOT / "data" / "seeds" / "v06_985_competition_discovery.json"),
    )
    parser.add_argument(
        "--universities",
        default=str(PROJECT_ROOT / "data" / "seeds" / "985_universities.json"),
    )
    parser.add_argument("--batch", action="append", help="Run only the named batch. Can be passed more than once.")
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "data" / "reports" / "v06_985_competition_discovery_report.json"),
    )
    args = parser.parse_args()

    seed_path = Path(args.seed)
    universities_path = Path(args.universities)
    report_path = Path(args.report)
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    selected_batches = args.batch or [batch["name"] for batch in payload.get("batches", [])]

    importer = CompetitionDiscoveryImportService()
    intelligence = CompetitionIntelligenceService()
    fact_service = FactIntelligenceService()
    discovery_service = CompetitionDiscoveryService()
    results = []

    with SessionLocal() as db:
        for batch_name in selected_batches:
            result = importer.import_json(db, seed_path, universities_path, batch_name=batch_name)
            result["source_tiers"] = fact_service.refresh_source_tiers(db)
            result["verification"] = fact_service.refresh_verification(db)
            db.commit()
            result["tags"] = intelligence.apply_tags(db)
            result["statistics"] = intelligence.refresh_all(db)
            results.append({"batch": batch_name, **result})

        stats = StatsRepository().get_platform_stats(db)
        coverage = discovery_service.coverage_summary(db)
        report = {
            "seed": seed_path.name,
            "batches": results,
            "platform_stats": stats,
            "discovery_coverage": coverage,
            "source_diversity": source_diversity(db),
            "database_counts": database_counts(db),
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def source_diversity(db) -> dict:
    sources = list(db.execute(select(CompetitionSource).where(CompetitionSource.is_demo.is_(False))).scalars())
    leads = list(db.execute(select(CompetitionLead)).scalars())
    domains = [urlparse(source.source_url).netloc.lower() for source in sources if urlparse(source.source_url).netloc]
    return {
        "competition_source_types": dict(Counter(source.source_type for source in sources)),
        "lead_source_types": dict(Counter(lead.source_type for lead in leads)),
        "lead_platforms": dict(Counter(lead.source_platform or "unknown" for lead in leads)),
        "official_domains": dict(Counter(domains).most_common(30)),
        "unique_source_domains": len(set(domains)),
    }


def database_counts(db) -> dict:
    return {
        "competitions": db.scalar(select(func.count()).select_from(Competition)) or 0,
        "competition_editions": db.scalar(select(func.count()).select_from(CompetitionEdition)) or 0,
        "competition_leads": db.scalar(select(func.count()).select_from(CompetitionLead)) or 0,
        "competition_sources": db.scalar(select(func.count()).select_from(CompetitionSource)) or 0,
        "university_competition_edition_relations": db.scalar(
            select(func.count()).select_from(UniversityCompetitionEditionRelation)
        )
        or 0,
    }


if __name__ == "__main__":
    main()
