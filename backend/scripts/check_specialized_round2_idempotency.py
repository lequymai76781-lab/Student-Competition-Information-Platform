"""Prove that the round-two importer is semantically idempotent."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
IMPORTER = ROOT / "backend/scripts/import_specialized_institutions_round2.py"
REPORT = ROOT / "data/reports/specialized_round2_idempotency.json"
TABLES = (
    "universities", "colleges", "majors", "competitions", "competition_editions",
    "university_competition_edition_relations", "policy_documents",
    "competition_policy_recognitions", "competition_sources", "competition_fact_sources",
)
VOLATILE = {
    "created_at", "updated_at", "observed_at", "retrieved_at", "crawled_at",
    "last_verified_at", "last_seen_at", "source_updated_at", "next_check_at",
}


def semantic_digest() -> str:
    payload = {}
    with sqlite3.connect(DB) as db:
        for table in TABLES:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})") if row[1] not in VOLATILE]
            order = "id" if "id" in columns else columns[0]
            rows = db.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY {order}").fetchall()
            payload[table] = {"columns": columns, "rows": rows}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_importer():
    spec = importlib.util.spec_from_file_location("specialized_round2_importer", IMPORTER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    before = semantic_digest()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        load_importer().main()
    stats = json.loads(output.getvalue())
    after = semantic_digest()
    passed = before == after and all(value == 0 for value in stats.values())
    result = {
        "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "semantic_digest_before": before,
        "semantic_digest_after": after,
        "importer_stats": stats,
    }
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
