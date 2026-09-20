from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import Competition, University
from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService


NAMES = ["西南财经大学", "华中农业大学", "武汉理工大学"]
OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "reports" / "v082_three_school_regression.json"


def main() -> None:
    db = SessionLocal()
    try:
        rows = []
        for university in db.execute(select(University).where(University.name.in_(NAMES))).scalars():
            rows.append(
                {
                    "name": university.name,
                    "short_name": university.short_name,
                    "aliases": university.aliases or [],
                    "official_domain": university.official_domain,
                    "official_website": university.official_website,
                }
            )
        service = UniversityRadarDiscoveryService()
        try:
            competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))).scalars())
            matcher = service._build_matcher(db, competitions)
            reverse_names = service._reverse_search_names(db)
            observed_at = datetime.now(timezone.utc)
            discovered = []
            for index, row in enumerate(rows):
                result = service._discover_university(
                    row,
                    f"v082-three-school-{index + 1:02d}",
                    matcher,
                    reverse_names,
                    observed_at,
                )
                discovered.append(result)
                print(json.dumps(
                    {
                        "school": row["name"],
                        "batch": result["report"]["batch_name"],
                        "status": result["report"]["status"],
                        "funnel": result["report"].get("discovery_funnel", {}),
                    },
                    ensure_ascii=False,
                ), flush=True)
        finally:
            service.close()

        payload = {
            "version": "v0.8.2",
            "retrieved_at": observed_at.isoformat(),
            "scope": "three_school_regression",
            "discovery_reports": [item["report"] for item in discovered],
            "leads": [lead for item in discovered for lead in item["leads"]],
            "edition_relations": [relation for item in discovered for relation in item["relations"]],
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("VERSION", payload["version"])
        for report in payload["discovery_reports"]:
            print("\nSCHOOL", report["university"])
            print("batch", report["batch_name"])
            print("status", report["status"])
            print("funnel", json.dumps(report.get("discovery_funnel", {}), ensure_ascii=False))
            print("leads", report["competition_leads"], "matched", report["matched_competitions"])
            print("reason", report.get("reason"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
