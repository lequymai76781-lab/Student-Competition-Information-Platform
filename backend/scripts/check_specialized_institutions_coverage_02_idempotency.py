"""Run the coverage-02 importer once more and compare semantic DB snapshots."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from import_specialized_institutions_02 import run_import

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
REPORT = ROOT / "data/reports/specialized_institutions_coverage_02_idempotency.json"
TASK = "SPECIALIZED_INSTITUTIONS_COVERAGE_02"


def metadata(value):
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def snapshot() -> dict:
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        relations = [dict(row) for row in db.execute("SELECT * FROM university_competition_edition_relations") if metadata(row["metadata"]).get("task") == TASK]
        policies = [dict(row) for row in db.execute("SELECT * FROM policy_documents") if metadata(row["metadata"]).get("task") == TASK]
        sources = [dict(row) for row in db.execute("SELECT * FROM competition_sources") if metadata(row["metadata"]).get("task") == TASK]
        payload = {
            "relations": sorted((row["university_id"], row["competition_edition_id"], row["internal_notice_url"]) for row in relations),
            "policies": sorted((row["university_id"], row["source_url"], row["scope_type"]) for row in policies),
            "sources": sorted((row["competition_id"], row["source_url"], row["source_type"]) for row in sources),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {"counts": {key: len(value) for key, value in payload.items()}, "digest": hashlib.sha256(raw.encode("utf-8")).hexdigest()}


def main() -> None:
    before = snapshot()
    importer = run_import()
    after = snapshot()
    result = {
        "task": TASK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": before == after and not importer["stats"],
        "before": before,
        "after": after,
        "second_run_stats": importer["stats"],
    }
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
