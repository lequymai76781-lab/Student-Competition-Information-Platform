"""Repair the Batch A rows affected by the old hard-coded Double First-Class flag.

The general-undergraduate master excludes every 985/211/Double First-Class and
specialized institution before it creates the internal A/B collection queues.
This migration is deliberately limited to the 32 names in ``general_a``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/v02.sqlite"
BATCHES = ROOT / "data/seeds/general_undergraduate_batches.json"
REPORT = ROOT / "data/reports/general_undergraduate_flag_repair.json"


def main() -> None:
    payload = json.loads(BATCHES.read_text(encoding="utf-8"))
    names = payload["batches"]["general_a"]
    placeholders = ",".join("?" for _ in names)
    query = (
        "SELECT id,name,is_985,is_211,is_double_first_class "
        f"FROM universities WHERE name IN ({placeholders}) ORDER BY name"
    )

    with sqlite3.connect(DB) as db:
        rows = db.execute(query, names).fetchall()
        found = {row[1] for row in rows}
        missing = sorted(set(names) - found)
        priority_conflicts = [row[1] for row in rows if row[2] or row[3]]
        if missing or priority_conflicts:
            raise RuntimeError(
                f"refusing repair: missing={missing}, 985_or_211={priority_conflicts}"
            )
        affected = [row[1] for row in rows if row[4]]
        db.execute(
            f"UPDATE universities SET is_double_first_class=0 WHERE name IN ({placeholders})",
            names,
        )
        after = db.execute(
            f"SELECT COUNT(*) FROM universities WHERE name IN ({placeholders}) "
            "AND is_double_first_class=1",
            names,
        ).fetchone()[0]

    report = {
        "task": "GENERAL_UNDERGRADUATE_DISCOVERY_FIX_01_FLAG_REPAIR",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "general_a only; no Batch B rows",
        "batch_a_count": len(names),
        "affected_before": len(affected),
        "affected_names": affected,
        "double_first_class_true_after": after,
        "passed": after == 0,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
