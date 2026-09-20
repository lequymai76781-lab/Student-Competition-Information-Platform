"""V1.0.1 migration drill: empty DB -> alembic upgrade head."""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent


def main() -> None:
    temp_db = ROOT / "data" / "tmp_migration_empty.sqlite"
    temp_db.unlink(missing_ok=True)
    sqlite3.connect(temp_db).close()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{temp_db.as_posix()}"
    env["ENVIRONMENT"] = "test"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    success = result.returncode == 0
    table_count = 0
    revision = None
    if success:
        conn = sqlite3.connect(temp_db)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        table_count = len(tables)
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()
    report = {
        "success": success,
        "table_count": table_count,
        "head_revision": revision,
        "log_tail": (result.stdout or "")[-5000:] + "\nSTDERR:\n" + (result.stderr or "")[-5000:],
        "drill_at": datetime.now().isoformat(),
    }
    (ROOT / "data" / "reports" / "v101_migration_drill.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_db.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
