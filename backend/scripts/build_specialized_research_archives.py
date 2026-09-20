"""Finalize the generated Remaining 22 cohort and all 34 research archives."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data/seeds/specialized_institutions.json"
P0 = ROOT / "data/checkpoints/specialized_institutions_coverage_01.json"
P1 = ROOT / "data/checkpoints/specialized_institutions_coverage_01_p1.json"
SECOND_ROUND = ROOT / "data/checkpoints/specialized_second_round_evidence.json"
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
    second_rows = json.loads(SECOND_ROUND.read_text(encoding="utf-8"))["institutions"]
    if len(second_rows) != 22 or len({row["name"] for row in second_rows}) != 22:
        raise RuntimeError("second-round evidence must contain exactly the generated Remaining 22 cohort")
    second = {row["name"]: row for row in second_rows}
    old = {row["name"]: row for row in p0 + p1}
    now = datetime.now(timezone.utc).isoformat()
    remaining: list[dict] = []
    archives: list[dict] = []
    for row in master:
        first = old.get(row["name"], {})
        entries = first.get("official_entries", first.get("entries", []))
        failures = first.get("failed_entries", [])
        lead_count = int(first.get("candidates", len(first.get("facts", []))))
        round2 = second.get(row["name"])
        checked_sources = [
            {"url": url, "source_type": "first_round_official_entry", "phase": 1, "result": "checked"}
            for url in entries
        ]
        if round2:
            checked_sources.extend({**item, "phase": 2} for item in round2["checked_sources"])
        deduped_sources = []
        seen_urls = set()
        for item in checked_sources:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            deduped_sources.append(item)
        current_has_data = row["coverage_state"] != "no_relation_data"
        final_status = round2["final_status"] if round2 else (
            "VERIFIED_DATA" if current_has_data else "NEEDS_DEEPER_REVIEW"
        )
        status_reason = round2["status_reason"] if round2 else (
            "数据库已有可核验关系，并已完成第一轮官方来源复核。"
            if current_has_data else "未找到第二轮研究档案。"
        )
        archive = {
            "institution_id": row["existing_school_id"],
            "name": row["name"],
            "categories": row["category"],
            "priority": row["priority"],
            "official_root": row["official_url"],
            "checked_sources": deduped_sources,
            "discovery_queries": round2["discovery_queries"] if round2 else [],
            "candidate_count": lead_count + (int(round2["candidate_count"]) if round2 else 0),
            "verified_relations": sum(
                int(row.get(key, 0)) for key in ("recognition", "notification", "participation")
            ),
            "professional_references": int(row.get("professional_reference", 0)),
            "last_checked_at": now,
            "final_status": final_status,
            "status_reason": status_reason,
            "first_round_status": first.get("status", "COMPLETED_WITH_GAPS"),
            "first_round_lead_count": lead_count,
            "failure_reasons": failures or [first.get("notes", "未形成可写关系")],
            "missing_evidence": evidence_gap(first),
        }
        archives.append(archive)
        if round2:
            remaining.append(
                {
                    "name": row["name"],
                    "categories": row["category"],
                    "priority": row["priority"],
                    "first_round_status": archive["first_round_status"],
                    "first_round_entries": entries,
                    "first_round_lead_count": lead_count,
                    "failure_reasons": archive["failure_reasons"],
                    "missing_evidence": archive["missing_evidence"],
                    "second_round_queries": round2["discovery_queries"],
                    "second_round_checked_sources": round2["checked_sources"],
                    "second_round_candidate_count": round2["candidate_count"],
                    "final_status": final_status,
                    "status_reason": status_reason,
                }
            )
    if len(remaining) != 22:
        raise RuntimeError(f"expected fixed Remaining 22 cohort, got {len(remaining)}")
    research_complete = all(item["final_status"] for item in archives)
    OUT.write_text(
        json.dumps(
            {"name": "SPECIALIZED_REMAINING_22", "generated_at": now, "count": 22, "institutions": remaining},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ARCHIVE.write_text(
        json.dumps(
            {
                "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
                "generated_at": now,
                "research_complete": research_complete,
                "institutions": archives,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"remaining": len(remaining), "archives": len(archives), "research_complete": research_complete},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
