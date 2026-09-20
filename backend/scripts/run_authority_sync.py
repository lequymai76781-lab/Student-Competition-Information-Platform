"""Run the repeatable authority-source sync pipeline.

Usage:
    python backend/scripts/run_authority_sync.py            # dry-run
    python backend/scripts/run_authority_sync.py --apply    # write changes

The registry is data/seeds/authority_registry/*.json. Output goes to
data/reports/authority_sync_report.json.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.services.authority_sync_service import REGISTRY_DIR_DEFAULT, AuthoritySyncService


def main() -> None:
    parser = argparse.ArgumentParser(description="Authority main-library sync pipeline")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument(
        "--registry-dir",
        type=Path,
        default=REGISTRY_DIR_DEFAULT,
        help="directory containing authority registry JSON entries",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "authority_sync_report.json",
        help="report output path",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        report = AuthoritySyncService().run(
            db,
            registry_dir=args.registry_dir,
            dry_run=not args.apply,
            now=datetime.now(timezone.utc),
        )
        if args.apply:
            db.commit()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
