"""Produce a reproducible root-cause audit of the original 32-school Batch A run."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "data/checkpoints/general_undergraduate_batch_a.json"
MASTER_REPORT = ROOT / "data/reports/general_undergraduate_master.json"
REPORT = ROOT / "data/reports/general_undergraduate_discovery_fix_01_baseline_audit.json"


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    master = json.loads(MASTER_REPORT.read_text(encoding="utf-8"))
    rows = []
    primary_counts: Counter[str] = Counter()
    for school in checkpoint["schools"]:
        policy = school["policy_pass"]
        if policy["status"] == "failed" and policy["errors"]:
            primary = "technical_access_restriction"
        elif school.get("qa_note"):
            primary = "classifier_false_positive_path"
        else:
            primary = "one_hop_discovery_strategy_failure"
        primary_counts[primary] += 1
        rows.append({
            "school": school["school"],
            "primary_root_cause": primary,
            "pages_discovered": policy["pages_discovered"],
            "pages_fetched": policy["pages_fetched"],
            "documents_found": policy["documents_found"],
            "policies_found_before_qa": policy["policies_found"],
            "policy_errors": policy["errors"],
            "radar_status": school["radar_status"],
        })

    observed = {
        "official_homepage_unreachable": {
            "count": primary_counts["technical_access_restriction"], "instrumented": True
        },
        "internal_search_failed": {"count": 0, "instrumented": False},
        "search_engine_summary_only": {"count": 0, "instrumented": False},
        "page_found_but_classifier_filtered": {"count": 0, "instrumented": False},
        "policy_page_found_but_attachment_missed": {"count": 0, "instrumented": False},
        "attachment_found_but_download_failed": {"count": 0, "instrumented": True},
        "competition_notice_found_without_policy": {"count": 0, "instrumented": False},
        "redirect_failure": {"count": 0, "instrumented": True},
        "http_403": {"count": 0, "instrumented": True},
        "http_412": {"count": 0, "instrumented": True},
        "javascript_rendering_failure": {"count": 0, "instrumented": False},
        "classifier_false_positive_schools": {
            "count": primary_counts["classifier_false_positive_path"], "instrumented": True
        },
        "classifier_false_positive_documents": {
            "count": sum(
                row["policies_found_before_qa"]
                for row in rows
                if row["primary_root_cause"] == "classifier_false_positive_path"
            ),
            "instrumented": True,
        },
        "secondary_radar_timeout": {
            "count": sum("timeout" in row["radar_status"] for row in rows), "instrumented": True
        },
    }
    payload = {
        "task": "GENERAL_UNDERGRADUATE_DISCOVERY_FIX_01_BASELINE_AUDIT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_status": {"ACCESS_LIMITED": len(rows)},
        "mutually_exclusive_primary_root_causes": dict(primary_counts),
        "observed_failure_mechanisms": observed,
        "telemetry_caveat": (
            "A zero with instrumented=false means no observable event was recorded because the old run "
            "did not execute or persist that discovery stage; it is not proof the mechanism never occurred."
        ),
        "batch_a_selection_audit": {
            "source_undergraduate": master["source_undergraduate"],
            "excluded_priority_or_specialized": master["excluded_priority_or_specialized"],
            "master_total": master["target_total"],
            "batch_a": master["batch_a"],
            "batch_b": master["batch_b"],
            "basis": "explicit hard-coded BATCH_A_SCHOOLS pilot map",
            "not_based_on": ["historical admissions batch", "public university tier", "score or rank"],
            "conclusion": "artificially narrow pilot; not a complete natural stratum",
        },
        "schools": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary": dict(primary_counts),
        "batch_a": master["batch_a"],
        "batch_b": master["batch_b"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
