"""Isolated shallow-first discovery for one ordinary undergraduate school."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.university_radar_discovery_service import CrawlBudget, UniversityRadarDiscoveryService


def main() -> None:
    input_path, output_path = map(Path, sys.argv[1:3])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    observed_at = datetime.fromisoformat(payload["observed_at"])
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    service = UniversityRadarDiscoveryService()
    service.budget = CrawlBudget(**payload["crawl_budget"])
    started = time.monotonic()
    try:
        result = service._discover_university(
            payload["university"], "", payload.get("matcher", {}),
            payload.get("reverse_names", []), observed_at,
        )
    finally:
        service.close()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    output_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
