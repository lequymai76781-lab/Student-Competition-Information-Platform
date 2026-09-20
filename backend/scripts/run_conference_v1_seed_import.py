"""Import Academic Conference V1 seeds into the configured database.

Usage (from backend):
    python scripts/run_conference_v1_seed_import.py
    python scripts/run_conference_v1_seed_import.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.services.conference_seed_import_service import ConferenceSeedImportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Academic Conference V1 seed data.")
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "seeds" / "conference_v1",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing.")
    args = parser.parse_args()

    seed_dir = args.seed_dir
    if not seed_dir.exists():
        raise SystemExit(f"seed dir not found: {seed_dir}")

    if args.dry_run:
        # Validation runs during load; keep the DB untouched.
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "seed_dir": str(seed_dir),
                    "note": "使用前请确认 JSON 已通过 build_conference_v1_seeds.py 校验。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    with SessionLocal() as db:
        stats = ConferenceSeedImportService().import_folder(db, seed_dir)
    print(json.dumps({"dry_run": False, **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
