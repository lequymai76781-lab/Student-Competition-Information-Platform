"""Generate the V1 maintenance queue report (read-mostly, writes reports only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal  # noqa: E402
from app.services.maintenance_queue_service import generate_maintenance_queue  # noqa: E402


def main() -> None:
    out = PROJECT_ROOT / "data" / "reports" / "v14_maintenance_queue.json"
    with SessionLocal() as db:
        report = generate_maintenance_queue(db)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
