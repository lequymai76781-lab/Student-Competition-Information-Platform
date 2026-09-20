"""Build remaining-school and 34-school research archives from existing artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data/seeds/specialized_institutions.json"
P0 = ROOT / "data/checkpoints/specialized_institutions_coverage_01.json"
P1 = ROOT / "data/checkpoints/specialized_institutions_coverage_01_p1.json"
OUT = ROOT / "data/checkpoints/SPECIALIZED_REMAINING_22.json"
ARCHIVE = ROOT / "data/checkpoints/specialized_institution_research_archives.json"


def evidence_gap(item: dict) -> list[str]:
    facts = item.get("facts", [])
    notes = item.get("notes", "")
    gaps = []
    if not facts and not item.get("candidates", 0):
        gaps.append("缺少具名专业赛事或制度证据")
    if "目录" in notes or "目录" in "".join(item.get("failed_entries", [])):
        gaps.append("缺少可核验的具名目录或附件")
    if not item.get("entries") and not item.get("official_entries"):
        gaps.append("缺少可访问的核心教学/实践部门入口")
    return gaps or ["已有线索尚未形成带官方来源的正式关系"]


def main() -> None:
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    p0 = json.loads(P0.read_text(encoding="utf-8"))["schools"]
    p1 = json.loads(P1.read_text(encoding="utf-8"))["schools"]
    old = {row["name"]: row for row in p0 + p1}
    now = datetime.now(timezone.utc).isoformat()
    remaining, archives = [], []
    for row in master:
        first = old.get(row["name"], {})
        entries = first.get("official_entries", first.get("entries", []))
        failures = first.get("failed_entries", [])
        lead_count = int(first.get("candidates", len(first.get("facts", []))))
        base = {
            "institution_id": row["existing_school_id"], "name": row["name"],
            "categories": row["category"], "priority": row["priority"],
            "official_root": row["official_url"], "checked_sources": entries,
            "discovery_queries": [], "candidate_count": lead_count,
            "verified_relations": sum(int(row.get(k, 0)) for k in ("recognition","notification","participation")),
            "professional_references": int(row.get("professional_reference", 0)),
            "last_checked_at": now,
            "final_status": "VERIFIED_DATA" if row["coverage_state"] != "no_relation_data" else None,
            "status_reason": "数据库已有可核验关系" if row["coverage_state"] != "no_relation_data" else None,
        }
        archives.append(base)
        if row["coverage_state"] == "no_relation_data":
            remaining.append({
                "name": row["name"], "categories": row["category"], "priority": row["priority"],
                "first_round_status": first.get("status", "COMPLETED_WITH_GAPS"),
                "first_round_entries": entries, "first_round_lead_count": lead_count,
                "failure_reasons": failures or [first.get("notes", "未形成可写关系")],
                "missing_evidence": evidence_gap(first),
            })
    if len(remaining) != 22:
        raise RuntimeError(f"expected 22 remaining, got {len(remaining)}")
    OUT.write_text(json.dumps({"name":"SPECIALIZED_REMAINING_22","generated_at":now,"count":22,"institutions":remaining}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    ARCHIVE.write_text(json.dumps({"task":"SPECIALIZED_INSTITUTIONS_COVERAGE_01","generated_at":now,"institutions":archives}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"remaining":len(remaining),"archives":len(archives)}, ensure_ascii=False))


if __name__ == "__main__": main()
