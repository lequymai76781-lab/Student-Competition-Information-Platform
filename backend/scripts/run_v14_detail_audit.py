"""V14 20-page detail audit + hall display audit (read-mostly)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


SAMPLE_IDS = [
    1,  # 教育部主办、多 Edition
    2,  # 挑战杯（大挑）
    3,  # 挑战杯（小挑）
    4,  # 数学建模
    5,  # 电赛多 Edition
    8,  # 计算机赛事（ICPC）
    21,  # 三创
    29,  # 仅高校secondary主办（v13）
    34,  # 计算机设计
    35,  # C4 无历史 Edition
    36,  # 蓝桥 JS 壳
    40,  # 集成电路（v13 secondary）
    42,  # 信息安全（v13 secondary）
    45,  # 机械工程创新（v13 secondary）
    56,  # 商业精英无历史
    65,  # 教育部/国家语委
    70,  # 化工实验（v13 secondary）
    77,  # 统计建模（v13 secondary）
    99,  # 数学竞赛多 Edition
    125,  # 研究生企创
]

RAW_STATUS_TOKENS = (
    "verified_official",
    "authority_confirmed",
    "school_confirmed",
    "pending_verification",
    "association_confirmed",
    "non_competition",
)


def main() -> None:
    client = TestClient(app)
    hall = []
    for offset in (0, 100):
        page = client.get(f"/api/competitions?limit=100&offset={offset}").json()["data"]
        if not page:
            break
        hall.extend(page)
    hall_ids = [row["id"] for row in hall]
    hidden_checks = {
        "duplicate_102": 102 not in hall_ids,
        "duplicate_118": 118 not in hall_ids,
        "non_competition_7": 7 not in hall_ids,
        "non_competition_12": 12 not in hall_ids,
        "no_evidence_unverified_110": 110 not in hall_ids,
        "core_confirmed_present": any(
            competition_id in hall_ids for competition_id in (1, 4, 65)
        ),
    }

    results = []
    for competition_id in SAMPLE_IDS:
        item = {
            "competition_id": competition_id,
            "checks": [],
            "warns": [],
            "fails": [],
        }
        response = client.get(f"/api/competitions/{competition_id}")
        if response.status_code != 200:
            item["fails"].append(f"detail http {response.status_code}")
            results.append(item)
            continue
        data = response.json()["data"]
        item["name"] = data["name"]
        if not data["name"]:
            item["fails"].append("empty name")
        for key in ("co_organizers", "guiding_organizations", "undertakers"):
            if data.get(key) is None:
                item["fails"].append(f"{key} is null (should be list)")
        if data.get("official_website") and not str(data["official_website"]).startswith(("http://", "https://")):
            item["fails"].append("official_website not http(s)")
        label = data.get("official_verification_status") or ""
        if any(token in label for token in RAW_STATUS_TOKENS):
            item["fails"].append("raw verification token leaked to label")
        elif label in ("暂未核实", ""):
            item["warns"].append("verification label generic")
        years = [edition["year"] for edition in data.get("editions", [])]
        if years != sorted(years, reverse=True):
            item["fails"].append("editions not sorted desc")
        if not years:
            item["warns"].append("no editions (expected for some)")
        if data.get("verification_status") in ("pending_verification", "school_confirmed"):
            if data["verification_status"] == "pending_verification" and label != "信息核验中":
                item["fails"].append("pending label mismatch")
            if data["verification_status"] == "school_confirmed" and label != "高校正式收录":
                item["fails"].append("school label mismatch")
        if data.get("university_registration_deadline") and not item.get("university_selected"):
            item["warns"].append("competition body contains campus deadline")
        if not data.get("sources"):
            item["warns"].append("no source rows")
        if data.get("verification_status") not in {
            "verified_official",
            "authority_confirmed",
            "association_confirmed",
            "pending_verification",
            "school_confirmed",
        }:
            item["warns"].append(f"status {data.get('verification_status')}")
        results.append(item)

    report = {
        "round": "v14 core-library detail/hall audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hall_total": len(hall_ids),
        "hidden_checks": hidden_checks,
        "samples": results,
        "summary": {
            "PASS": sum(
                1 for item in results if not item["fails"] and not item["warns"]
            ),
            "WARN": sum(1 for item in results if not item["fails"] and item["warns"]),
            "FAIL": sum(1 for item in results if item["fails"]),
        },
    }
    out = PROJECT_ROOT / "data" / "reports" / "v14_detail_audit.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
