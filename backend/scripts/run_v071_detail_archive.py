from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.repositories.stats_repository import StatsRepository
from app.services.competition_detail_archive_service import CompetitionDetailArchiveService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V0.7.1 existing-competition detail archive pipeline.")
    parser.add_argument("--seed", default=str(PROJECT_ROOT / "data" / "seeds" / "v071_detail_archive.json"))
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "data" / "reports" / "v071_detail_archive_acceptance_report.json"),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    service = CompetitionDetailArchiveService()
    with SessionLocal() as db:
        import_result = service.import_json(db, args.seed)
        db.commit()
        acceptance = service.acceptance(db, import_result["updated_ids"])
        report = {
            "version": "v0.7.1",
            "import": import_result,
            "acceptance": acceptance,
            "platform_stats": StatsRepository().get_platform_stats(db),
        }
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
