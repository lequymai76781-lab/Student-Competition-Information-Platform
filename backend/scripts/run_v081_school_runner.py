"""Single-school V0.8.1 discovery runner used as an isolated subprocess.

The orchestrator (run_v081_211_radar_fix.py) spawns one subprocess per school
with a hard timeout, so a slow/stuck university site cannot stall the whole
50-school batch.

Usage:
    python run_v081_school_runner.py <input.json> <output.json>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.university_radar_discovery_service import UniversityRadarDiscoveryService


def main() -> None:
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    university = payload["university"]
    matcher = payload.get("matcher", {})
    reverse_names = payload.get("reverse_names", [])
    observed_at = datetime.fromisoformat(payload.get("observed_at"))
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    started = time.monotonic()
    service = UniversityRadarDiscoveryService()
    try:
        result = service._discover_university(university, "", matcher, reverse_names, observed_at)
    finally:
        service.close()
    print(f"school={university['name']} phase=discover elapsed={time.monotonic() - started:.1f}s", file=sys.stderr)
    output_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
