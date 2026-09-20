"""Run the v12 evidence-grounded fact enrichment (dry-run by default)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal  # noqa: E402
from app.services.v12_fact_enrichment_service import (  # noqa: E402
    REGISTRY_DIR_DEFAULT,
    V12FactEnrichmentService,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default dry-run)")
    parser.add_argument("--registry", type=Path, default=REGISTRY_DIR_DEFAULT)
    parser.add_argument(
        "--report-out",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "v12_fact_enrichment_report.json",
    )
    parser.add_argument(
        "--website-autofill",
        action="store_true",
        help="also fill official_website from verified S website sources",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    service = V12FactEnrichmentService()
    with SessionLocal() as db:
        report = service.run(
            db,
            registry_dir=args.registry,
            dry_run=dry_run,
            now=datetime.now(timezone.utc),
        )
        autofill = None
        if args.website_autofill:
            autofill = service.fill_official_website_from_sources(db, dry_run=dry_run)
            report["official_website_autofill"] = autofill
        if not dry_run:
            db.commit()
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
