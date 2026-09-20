"""V1.0.1 restore drill: backup -> temp DB -> start backend -> health -> sample."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import os
from datetime import datetime
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent


def main() -> None:
    backup_dir = ROOT / "data" / "backups"
    backups = sorted(backup_dir.glob("backup-*.sqlite"))
    if not backups:
        raise SystemExit("没有可用的备份文件，请先运行 backup_database.py")
    backup = backups[-1]
    manifest_path = backup.with_name(backup.name.replace(".sqlite", "") + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    temp_db = ROOT / "data" / "backups" / f"restore-drill-{datetime.now().strftime('%H%M%S')}.sqlite"
    shutil.copyfile(backup, temp_db)

    conn = sqlite3.connect(temp_db)
    restored_counts = {}
    count_errors = {}
    for table in manifest["table_counts"]:
        try:
            restored_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError as exc:
            restored_counts[table] = -1
            count_errors[table] = str(exc)
    conn.close()
    count_matches = all(
        restored_counts.get(key) == value for key, value in manifest["table_counts"].items()
    )

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{temp_db.as_posix()}"
    env["ENVIRONMENT"] = "test"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    health = None
    competition_count = None
    try:
        deadline = time.time() + 30
        with httpx.Client(timeout=5) as client:
            while time.time() < deadline:
                try:
                    response = client.get("http://127.0.0.1:8002/api/health")
                    if response.status_code == 200:
                        health = response.status_code
                        break
                except httpx.HTTPError:
                    time.sleep(1)
            if health == 200:
                comps = client.get("http://127.0.0.1:8002/api/competitions?limit=1")
                comps_data = comps.json()
                competition_count = len(comps_data.get("data") or [])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    report = {
        "backup": str(backup),
        "restored_db": str(temp_db),
        "table_counts_match": count_matches,
        "restored_counts": restored_counts,
        "count_errors": count_errors,
        "health_status": health,
        "competition_sample_count": competition_count,
        "drill_at": datetime.now().isoformat(),
    }
    report_path = ROOT / "data" / "reports" / "v101_restore_drill.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for _ in range(10):
        try:
            temp_db.unlink(missing_ok=True)
            break
        except PermissionError:
            time.sleep(1)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
