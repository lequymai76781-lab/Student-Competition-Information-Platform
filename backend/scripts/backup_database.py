"""V1.0.1 database backup: timestamped SQLite copy + manifest."""

import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        raise SystemExit("备份脚本当前仅支持 SQLite 数据库")
    source = Path(settings.database_url.replace("sqlite:///", ""))
    if not source.exists():
        raise SystemExit(f"数据库不存在：{source}")
    backup_dir = ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"backup-{timestamp}.sqlite"
    # consistent copy via sqlite backup API
    src_conn = sqlite3.connect(source)
    dst_conn = sqlite3.connect(target)
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    conn = sqlite3.connect(target)
    tables = {
        "competitions": "competitions",
        "competition_editions": "competition_editions",
        "competition_sources": "competition_sources",
        "competition_fact_revisions": "competition_fact_revisions",
        "universities": "universities",
        "colleges": "colleges",
        "users": "users",
        "user_profiles": "user_profiles",
        "favorites": "favorites",
        "notifications": "notifications",
        "user_correction_submissions": "user_correction_submissions",
        "competition_update_events": "competition_update_events",
        "admin_audit_logs": "admin_audit_logs",
        "beta_feedback": "beta_feedback",
    }
    counts = {}
    for label, table in tables.items():
        try:
            counts[label] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            counts[label] = -1
    conn.close()
    manifest = {
        "source": str(source),
        "backup_file": str(target),
        "size_bytes": target.stat().st_size,
        "created_at": datetime.now().isoformat(),
        "table_counts": counts,
    }
    manifest_path = backup_dir / f"backup-{timestamp}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
