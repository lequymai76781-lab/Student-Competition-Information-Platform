"""Reproducible read-only replay of the fixed human Golden Set and old queues.

Outputs are separate analysis artifacts. Never updates human labels, frozen
predictions, candidate status, formal facts, or relationship records.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from app.services.golden_calibration_analysis import analyze_calibration
from app.services.source_document_classifier import classify_document, DOCUMENT_TYPES, RULE_VERSION
from app.services.document_policy_service import candidate_source
from app.services import document_calibration_policy as policy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".codex-qa/golden-calibration-20261001"

def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def digest(name):
    return sha256((ROOT / name).read_bytes()).hexdigest()

def main():
    before = read(".codex-qa/golden-calibration-20261001/before.json")
    assert all(digest(name) == value for name, value in before["protected"].items()), "Protected input changed since snapshot"
    manifest = read(".codex-qa/golden-set-20261001/live/manifest.json")
    human = read(".codex-qa/golden-calibration-20261001/human-snapshot.json")
    annotations = human["annotations"]
    originals = read(".codex-qa/document-policy/replay-verified/source-replay.json")
    baseline = analyze_calibration(manifest["items"], annotations)
    assert baseline["integrity"]["complete_100_human"] and baseline["integrity"]["frozen_prediction_match"]
    repaired_sources = [{**deepcopy(item), "classification": classify_document(item)} for item in originals]
    by_id = {str(item["source_id"]): item for item in repaired_sources}
    human_by_id = {str(item["source_id"]): item for item in annotations}
    repaired_items = []
    for item in manifest["items"]:
        current = by_id[str(item["source_id"])]["classification"]
        repaired_items.append({**deepcopy(item), "predicted_type": current["document_type"],
            "predicted_confidence": current["confidence"], "predicted_secondary_types": current["secondary_types"],
            "informational_only": current["informational_only"], "classification_status": current["classification_status"],
            "matched_rules": current["matched_rules"], "rule_version": current["rule_version"]})
    repaired = analyze_calibration(repaired_items, annotations)
    repaired["evaluation_context"] = "Same 100 original source inputs and unchanged human truth, after general rules repaired using this set. Development replay, not independent validation. Stored prediction mismatch is expected; original snapshot integrity is reported separately."
    changed = []
    for original, after in zip(manifest["items"], repaired_items):
        human_type = human_by_id[str(original["source_id"])]["human_primary_type"]
        if original["predicted_type"] != after["predicted_type"]:
            changed.append({"source_id": original["source_id"], "title": original["title"], "human_primary_type": human_type,
                "before": original["predicted_type"], "after": after["predicted_type"],
                "before_correct": original["predicted_type"] == human_type, "after_correct": after["predicted_type"] == human_type})
    source_for_candidate = {cid: item for item in originals for cid in item.get("candidate_ids", [])}
    rows = []
    target = ROOT / ".codex-qa/mid-scale/candidates.sqlite"
    with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for row in db.execute("SELECT * FROM review_queue WHERE item_type='field_candidate' ORDER BY id"):
            entity = SimpleNamespace(**dict(row)); doc = json.loads(entity.raw_value)
            context = doc.get("collection_context") or {}; proposals = doc.get("proposals") or []
            classification = classify_document(candidate_source(doc, entity), has_fact_changes=bool(proposals),
                has_conflicts=bool(context.get("flags")), has_valuable_relation=context.get("kind") == "school_mapping")
            saved_source = source_for_candidate.get(entity.id)
            reference = human_by_id.get(str(saved_source["source_id"])) if saved_source else None
            rows.append({"candidate_id": entity.id, "original_status": entity.status,
                "projected_queue_status": "informational" if classification["informational_only"] else "pending",
                "classification": classification, "proposal_count": len(proposals),
                "school_mapping": context.get("kind") == "school_mapping", "flags": context.get("flags") or [],
                "source_id": saved_source["source_id"] if saved_source else None,
                "human_reference": {"source_id":reference["source_id"], "human_primary_type":reference["human_primary_type"],
                    "annotated_at":reference["annotated_at"], "status":"COMPLETED_IN_GOLDEN_SET_NOT_IMPORTED"} if reference else None})
    assert len(rows) == 254
    queue = {"candidate_total": len(rows), "before_classifier": {"AUTO_CLASSIFIED":112,"NEEDS_QUICK_CONFIRM":14,"NEEDS_MANUAL_CLASSIFICATION":128},
        "after_classifier":dict(Counter(r["classification"]["classification_status"] for r in rows)),
        "after_queue":dict(Counter(r["projected_queue_status"] for r in rows)), "previous_replay_pending":252,
        "field_rows":sum(bool(r["proposal_count"]) for r in rows), "field_proposals":sum(r["proposal_count"] for r in rows),
        "school_mapping_rows":sum(r["school_mapping"] for r in rows), "flagged_rows":sum(bool(r["flags"]) for r in rows),
        "existing_human_source_reference_rows":sum(bool(r["human_reference"]) for r in rows),
        "classification_remaining_if_human_reference_reused":dict(Counter(r["classification"]["classification_status"] for r in rows if not r["human_reference"])),
        "human_reference_note":"These labels were already completed by the user, not automatic classifications or imported fact approvals. Queue projections do not mutate persisted state.",
        "unique_source_total":len(originals), "unique_source_after_classifier":dict(Counter(r["classification"]["classification_status"] for r in repaired_sources)),
        "unique_source_after_informational":sum(r["classification"]["informational_only"] for r in repaired_sources),
        "automatic_classification_workload_reduction":0.0, "timed_human_workload_reduction":None}
    proof = read(".codex-qa/golden-calibration-20261001/policy-safety-evidence.json")
    relation_key = next(key for key,value in proof.items() if isinstance(value,list) and len(value)==59)
    relation_records = proof[relation_key]
    audited = {a["audit_id"]:a for a in human["audits"] if a["kind"]=="relations" and a["status"]=="annotated"}
    plan = []
    for record in relation_records:
        rid = record.get("relation_id", record.get("id"))
        assert rid is not None, list(record)
        audit = audited.get(f"relation:{rid}")
        plan.append({"relation_id":rid,"policy_document_id":9,"strategy":"NEEDS_QUICK_CONFIRM",
            "automatic_formal_write_authorized":False,"existing_human_audit":audit,
            "pending_policy_document_validation":True,"persisted_relation_modified":False})
    summary = {"dataset_id":manifest["dataset_id"], "snapshot_at":human["read_at"], "baseline":baseline,
        "repaired":repaired, "changed_predictions":changed, "rule_version":RULE_VERSION,
        "calibration_policy_version":policy.VERSION,
        "per_class_decision":{kind:{"auto_threshold":None,"auto_enabled":False,
            "human_support":baseline["per_class"][kind]["support"],"reason":"No reliable automatic cutoff established; limited support and uncalibrated score. Suggestion requires human confirmation."} for kind in DOCUMENT_TYPES},
        "global_auto_threshold":None, "quick_confirm_threshold":None,
        "routing_definition":{"AUTO_CLASSIFIED":"Disabled until independent evidence supports a class cutoff.",
            "NEEDS_QUICK_CONFIRM":"An explicit type suggestion exists, without competing actions or high-risk signals; a human must confirm.",
            "NEEDS_MANUAL_CLASSIFICATION":"Unknown, ambiguous, high-risk or conflicting evidence; requires fuller review."},
        "queue":queue, "policy_automatic_relations":0,"policy_quick_confirm_relations":59,
        "policy_human_audits":sum(a["kind"]=="policies" and a["status"]=="annotated" for a in human["audits"]),
        "relation_human_audits":len(audited),"previous_policy_pending_tasks":454,"policy_confirmation_tasks_including_hold":513,
        "status":"BLOCKED", "reason":"No reliable numerical AUTO threshold; remaining policy false positives; incomplete informational safety and source-policy validation."}
    write("source-replay-calibrated.json",repaired_sources)
    write("candidate-replay-calibrated.json",rows)
    write("relationship-review-plan.json",plan)
    write("calibration-results.json",summary)
    assert all(digest(name) == value for name, value in before["protected"].items()), "Protected input changed during replay"
    print(json.dumps({"human_n":baseline["human_n"],"before_accuracy":baseline["accuracy"],"after_accuracy":repaired["accuracy"],
        "changed_predictions":len(changed),"improvements":sum(not c["before_correct"] and c["after_correct"] for c in changed),
        "regressions":sum(c["before_correct"] and not c["after_correct"] for c in changed),"queue":queue,"status":"BLOCKED"},ensure_ascii=False))

if __name__ == "__main__":
    main()
