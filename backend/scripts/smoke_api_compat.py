"""V0.9 read-only API compatibility smoke test.

Verifies the public endpoints still return the same top-level shapes after the
additive data-architecture migration. Read-only; no test data is created.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    client = TestClient(app)
    checks = [
        ("GET", "/api/health", 200, ["success"], ""),
        ("GET", "/api/competitions?limit=3", 200, [], "data"),
        ("GET", "/api/competitions/1", 200, ["editions", "sources"], "data"),
        ("GET", "/api/universities/1", 200, ["colleges"], "data"),
        ("GET", "/api/stats", 200, ["competitions", "universities", "editions"], "data"),
        ("GET", "/api/tags", 200, [], "data"),
    ]
    failed = 0
    for method, path, expected_status, expected_keys, data_key in checks:
        response = client.request(method, path)
        ok = response.status_code == expected_status
        payload = response.json() if response.content else {}
        target = payload.get(data_key, payload) if data_key else payload
        if ok and expected_keys:
            ok = all(key in target for key in expected_keys)
        print(f"{'OK ' if ok else 'FAIL'} {method} {path} -> {response.status_code}")
        failed += int(not ok)
    detail = client.get("/api/competitions/1").json().get("data", {})
    editions = detail.get("editions") or []
    sample = editions[0] if editions else {}
    print("edition_sample_keys_present:", all(key in sample for key in ("host_location", "edition_rules_url", "edition_status")))
    print("SMOKE_RESULT:", "PASS" if failed == 0 else f"FAIL({failed})")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
