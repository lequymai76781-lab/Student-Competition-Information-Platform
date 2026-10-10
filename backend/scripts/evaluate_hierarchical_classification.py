"""Read-only evaluation on the unchanged 100/200/254 original evidence sets.

All writes are analysis JSON under .codex-qa/hierarchical-classification-20261001.
No HTTP requests, generated performance rows, label mutations, or DB writes.
Run from repository root with backend/venv/Scripts/python.exe this-file.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / ".codex-qa/hierarchical-classification-20261001"
INPUTS = {
    "human": ".codex-qa/golden-calibration-20261001/human-snapshot.json",
    "manifest": ".codex-qa/golden-set-20261001/live/manifest.json",
    "originals": ".codex-qa/document-policy/replay-verified/source-replay.json",
    "repaired": ".codex-qa/golden-calibration-20261001/source-replay-calibrated.json",
    "old_results": ".codex-qa/golden-calibration-20261001/calibration-results.json",
    "policy_proof": ".codex-qa/golden-calibration-20261001/policy-safety-evidence.json",
    "policy_replay": ".codex-qa/document-policy/replay-verified/policy-replay.json",
    "policy_db": ".codex-qa/document-policy/replay-verified/policy-replay.sqlite",
    "candidate_db": ".codex-qa/mid-scale/candidates.sqlite",
    "formal_db": "data/v02.sqlite",
}


def open_readonly_database(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def read(name):
    return json.loads((ROOT / INPUTS[name]).read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _classification_prediction(classification, *, mapped=False):
    from app.services.document_taxonomy import map_primary_type
    fine = classification.get("document_type")
    return {**deepcopy(classification), "predicted_type": map_primary_type(fine) if mapped else fine,
            "predicted_fine_type": fine}


def _new_prediction(classification):
    return {**deepcopy(classification), "predicted_type": classification["primary_type"],
            "predicted_fine_type": classification["document_type"]}


def main():
    from app.services.document_taxonomy import FINE_TO_PRIMARY, HIERARCHY_VERSION, PRIMARY_TYPES
    from app.services.document_policy_service import candidate_source
    from app.services.golden_calibration_analysis import analyze_calibration
    from app.services.hierarchical_source_classifier import classify_source_document
    from app.services.hierarchical_classification_metrics import (
        build_evaluation_records, classification_metrics, global_threshold_curves,
        paired_bootstrap, policy_threshold_curves, routing_metrics, paired_policy_error_test,
    )
    from app.services.source_document_classifier import DOCUMENT_TYPES

    protected_before = {path: digest(ROOT / path) for path in INPUTS.values()}
    runtime_code_paths = ["backend/app/services/document_taxonomy.py", "backend/app/services/hierarchical_source_classifier.py", "backend/app/services/policy_safety_classifier.py", "backend/app/services/document_calibration_policy.py", "backend/app/services/hierarchical_classification_metrics.py", "backend/scripts/evaluate_hierarchical_classification.py"]
    runtime_code_sha256 = {path: digest(ROOT / path) for path in runtime_code_paths}
    manifest, human, original_sources = read("manifest"), read("human"), read("originals")
    repaired_sources, previous, proof, policy_replay = read("repaired"), read("old_results"), read("policy_proof"), read("policy_replay")
    annotations = human["annotations"]
    integrity = analyze_calibration(manifest["items"], annotations)["integrity"]
    assert integrity["complete_100_human"] and integrity["frozen_prediction_match"], integrity
    assert len(original_sources) == len(repaired_sources) == 200
    assert len({r["source_id"] for r in original_sources}) == 200
    assert {r["source_id"] for r in original_sources} == {r["source_id"] for r in repaired_sources}
    assert not manifest.get("fixture_only"), "Real human evaluation cannot use fixture-only manifest"
    assert tuple(PRIMARY_TYPES) == ("participation", "result", "information", "policy", "update", "repost", "other")
    fine_identity = {kind: kind for kind in DOCUMENT_TYPES}
    human_by_id = {str(row["source_id"]): row for row in annotations}
    original_by_id = {str(row["source_id"]): row for row in original_sources}
    repaired_by_id = {str(row["source_id"]): row for row in repaired_sources}
    frozen_predictions = {str(r["source_id"]): {"predicted_type": r["predicted_type"], "confidence": r["predicted_confidence"]} for r in manifest["items"]}
    repaired_predictions = {identity: _classification_prediction(source["classification"]) for identity, source in repaired_by_id.items()}
    merged_predictions = {identity: _classification_prediction(source["classification"], mapped=True) for identity, source in repaired_by_id.items()}
    frozen = build_evaluation_records(annotations, frozen_predictions, fine_identity)
    repaired = build_evaluation_records(annotations, repaired_predictions, fine_identity)
    merged = build_evaluation_records(annotations, merged_predictions, FINE_TO_PRIMARY)
    current_sources = [{**deepcopy(source), "classification": classify_source_document(source)} for source in original_sources]
    new_predictions = {str(r["source_id"]): _new_prediction(r["classification"]) for r in current_sources}
    current = build_evaluation_records(annotations, new_predictions, FINE_TO_PRIMARY)
    comparison = {
        "frozen_old20": classification_metrics(frozen, DOCUMENT_TYPES),
        "repaired_old20": classification_metrics(repaired, DOCUMENT_TYPES),
        "mechanically_merged7": classification_metrics(merged),
        "hierarchical7": classification_metrics(current),
    }
    assert comparison["frozen_old20"]["accuracy"] == .43
    assert comparison["repaired_old20"]["accuracy"] == .55
    changes = []
    for row, old in zip(current, merged):
        if row["predicted_type"] != old["predicted_type"]:
            changes.append({"source_id": row["source_id"], "title": original_by_id[row["source_id"]]["title"],
                            "human_primary_type": row["human_primary_type"], "human_secondary_types": row["human_secondary_types"],
                            "human_primary7": row["true_type"], "merged7": old["predicted_type"], "new7": row["predicted_type"],
                            "old_correct": old["predicted_type"] == old["true_type"], "new_correct": row["predicted_type"] == row["true_type"]})
    source_for_candidate = {candidate_id: source for source in original_sources for candidate_id in source.get("candidate_ids", [])}
    candidates = []
    with open_readonly_database(ROOT / INPUTS["candidate_db"]) as db:
        for raw in db.execute("SELECT * FROM review_queue WHERE item_type='field_candidate' ORDER BY id"):
            entity = SimpleNamespace(**dict(raw))
            doc = json.loads(entity.raw_value)
            context, proposals = doc.get("collection_context") or {}, doc.get("proposals") or []
            source = candidate_source(doc, entity)
            classification = classify_source_document(source, has_fact_changes=bool(proposals),
                has_conflicts=bool(context.get("flags")), has_valuable_relation=context.get("kind") == "school_mapping")
            saved_source = source_for_candidate.get(entity.id)
            source_identity = str(saved_source["source_id"]) if saved_source else None
            annotation = human_by_id.get(source_identity)
            candidates.append({"candidate_id": entity.id, "source_id": f"candidate:{entity.id}", "original_source_id": source_identity,
                               "original_status": entity.status, "source_input": source, "classification": classification,
                               **_new_prediction(classification), "proposal_count": len(proposals),
                               "proposal_fields": [p.get("field_name", p.get("field")) for p in proposals],
                               "school_mapping": context.get("kind") == "school_mapping", "flags": context.get("flags") or [],
                               "projected_queue_status": "informational" if classification["informational_only"] else "pending",
                               "true_type": FINE_TO_PRIMARY[annotation["human_primary_type"]] if annotation else None,
                               "human_secondary_types": deepcopy(annotation["human_secondary_types"]) if annotation else [],
                               "informational_safe": annotation.get("informational_safe") if annotation else None,
                               "human_reference": deepcopy(annotation) if annotation else None})
    assert len(candidates) == 254
    human_reused = [r for r in candidates if r["human_reference"]]
    human_remaining = [r for r in candidates if not r["human_reference"]]
    assert len(human_reused) == 116
    candidate_routes, remaining_routes = routing_metrics(candidates), routing_metrics(human_remaining)
    for routes in (candidate_routes, remaining_routes):
        routes["auto_accuracy_wilson95"] = None
        routes["interval_note"] = "Candidate rows repeat source IDs; they are not independent labeled samples. No row-level binomial interval is reported."
    previous_required = sum(previous["queue"]["after_classifier"].get(k, 0) for k in ("NEEDS_QUICK_CONFIRM", "NEEDS_MANUAL_CLASSIFICATION"))
    candidate_summary = {
        **candidate_routes, "candidate_total": len(candidates),
        "source_pool_n": len(current_sources), "historical_candidate_total": 254, "historical_pending_after_old_replay": 252,
        "previous_classifier_status_counts": previous["queue"]["after_classifier"],
        "current_classifier_status_counts": dict(Counter(r["classification_status"] for r in candidates)),
        "current_primary_type_counts": {kind: sum(r["predicted_type"] == kind for r in candidates) for kind in PRIMARY_TYPES},
        "projected_queue_status_counts": dict(Counter(r["projected_queue_status"] for r in candidates)),
        "actual_type_task_reduction_n": previous_required - candidate_routes["human_type_task_n"],
        "actual_type_task_reduction_fraction": (previous_required - candidate_routes["human_type_task_n"]) / previous_required,
        "existing_completed_human_reference_rows": len(human_reused),
        "existing_completed_human_source_n": len({r["original_source_id"] for r in human_reused}),
        "remaining_routes_after_human_reference_reuse": remaining_routes,
        "reference_reuse_extra_task_reduction_n": candidate_routes["human_type_task_n"] - remaining_routes["human_type_task_n"],
        "remaining_document_classification_human_tasks": remaining_routes["human_type_task_n"],
        "total_task_reduction_including_existing_human_labels_fraction": (previous_required - remaining_routes["human_type_task_n"]) / previous_required,
        "human_reference_note": "116 candidate rows already link to completed original human labels. Reuse is a separate projection, not new automatic predictions, new human labels, or persisted approval.",
        "field_fact_review": {"candidate_rows_with_proposals": sum(bool(r["proposal_count"]) for r in candidates),
                              "field_proposals": sum(r["proposal_count"] for r in candidates),
                              "school_mapping_rows": sum(r["school_mapping"] for r in candidates),
                              "flagged_rows": sum(bool(r["flags"]) for r in candidates),
                              "automatic_fact_approvals": 0,
                              "note": "Field facts and relationship evidence still require their own review; classification task reduction is not field task reduction."},
        "timed_human_workload_reduction": None,
    }
    source_routes = routing_metrics([{**_new_prediction(r["classification"]), "source_id": r["source_id"]} for r in current_sources])
    original_policy9 = next((r for r in original_sources if r.get("policy_document_id") == 9), None)
    with open_readonly_database(ROOT / INPUTS["policy_db"]) as db:
        policy_row = dict(db.execute("SELECT * FROM policy_documents WHERE id=9").fetchone())
    policy_metadata = json.loads(policy_row["metadata"] or "{}")
    policy9_input = {"title": policy_row["title"], "section": policy_metadata.get("section"), "document_format": policy_row["parser_type"], "content_preview": (policy_row["content_text"] or "")[:3500],
                     "content_text": policy_row["content_text"] or "", "source_url": policy_row["source_url"],
                     "publisher": policy_row["publisher"], "attachment_titles": [policy_row["original_filename"]] if policy_row["original_filename"] else []}
    policy9 = {"policy_document_id": 9, "classification": classify_source_document(policy9_input, has_valuable_relation=True),
               "source_input": policy9_input, "original_frozen_source": original_policy9,
               "frozen_source_classification": classify_source_document(original_policy9) if original_policy9 else None,
               "original_policy_row": policy_row, "old_policy_replay": next(r for r in policy_replay if r["policy_document_id"] == 9),
               "old_policy_safety_evidence": proof["doc9"], "relation_records": proof["auto_relations"],
               "human_policy_audits": [a for a in human["audits"] if a.get("kind") == "policies"],
               "human_relation_audits": [a for a in human["audits"] if a.get("kind") == "relations"],
               "formal_mutation_applied": False,
               "note": "Original 59 relationship evidence records exported intact. Root integration audit separately applies official/validity/matching/version gates; a correct document classification alone cannot authorize these relations."}
    assert len(policy9["relation_records"]) == 59
    per_predicted_class = {kind: {"hypothetical_threshold_curves": global_threshold_curves([r for r in current if r["predicted_type"] == kind]),
                                 "actual_routing": routing_metrics([r for r in current if r["predicted_type"] == kind])} for kind in PRIMARY_TYPES}
    result = {
        "analysis_version": "hierarchical-evaluation-1", "hierarchy_version": HIERARCHY_VERSION,
        "runtime_code_sha256": runtime_code_sha256,
        "dataset_id": manifest["dataset_id"], "human_snapshot_at": human["read_at"], "human_integrity": integrity,
        "comparison": comparison,
        "coarsening_accuracy_gain": comparison["mechanically_merged7"]["accuracy"] - comparison["repaired_old20"]["accuracy"],
        "semantic_rule_accuracy_gain": comparison["hierarchical7"]["accuracy"] - comparison["mechanically_merged7"]["accuracy"],
        "metric_comparison_note": "20-class and 7-class macro denominators differ. Mechanical merging isolates taxonomy coarsening; paired bootstrap compares only seven-class predictions on identical sources and truth.",
        "paired_bootstrap_new7_vs_mechanically_merged7": paired_bootstrap(merged, current),
        "paired_policy_error_comparison": paired_policy_error_test(merged, current),
        "global_hypothetical_threshold_curves": global_threshold_curves(current),
        "policy_independent_threshold_curves": policy_threshold_curves(current),
        "policy_default_binary": policy_threshold_curves(current, thresholds=(0.,))[0],
        "policy_automatic_safe_threshold": None,
        "policy_threshold_note": "The six policy thresholds filter the independent affirmative evidence decision and policy_confidence; class confidence is not used. These are descriptive filters, not approved production thresholds.",
        "actual_golden_routing": routing_metrics(current), "per_predicted_class": per_predicted_class,
        "proposed_information_evidence": {
            "predicted_information_n": sum(r["predicted_type"] == "information" for r in current),
            "placement_wrong_n": global_threshold_curves(current, thresholds=(0.,))[0]["information_misplacement_auto_n"],
            "placement_wrong_source_ids": global_threshold_curves(current, thresholds=(0.,))[0]["information_misplacement_auto_source_ids"],
            "factual_safety_unanswered_n": sum(r["predicted_type"] == "information" and r.get("informational_safe") not in ("yes", "no") for r in current),
            "factual_safety_answers": dict(Counter(r.get("informational_safe") or "unanswered" for r in current if r["predicted_type"] == "information")),
            "actual_informational_only_n": sum(r.get("informational_only") is True for r in current),
            "note": "Proposed information class is distinct from permission to remove a source from fact review. Original human primary/secondary safety and factual-safety labels are not inferred."},
        "actual_source200_routing": source_routes, "candidate254": candidate_summary,
        "update_safety": {"human_primary_n": sum(r["true_type"] == "update" for r in current),
                          "human_primary_or_secondary_n": global_threshold_curves(current)[0]["update_human_primary_or_secondary_n"],
                          "missed_primary_or_secondary_n": global_threshold_curves(current)[0]["update_missed_all_n"],
                          "not_high_risk_n": sum((r["true_type"] == "update" or bool(set(r["human_secondary_types"]) & {"deadline_extension", "correction_notice", "rule_update"})) and r.get("risk_level") != "HIGH_RISK" for r in current),
                          "not_high_risk_source_ids": [r["source_id"] for r in current if (r["true_type"] == "update" or bool(set(r["human_secondary_types"]) & {"deadline_extension", "correction_notice", "rule_update"})) and r.get("risk_level") != "HIGH_RISK"],
                          "missed_rows": [r for r in current if (r["true_type"] == "update" or set(r["human_secondary_types"]) & {"deadline_extension", "correction_notice", "rule_update"}) and r["predicted_type"] != "update"],
                          "into_information_n": sum((r["true_type"] == "update" or bool(set(r["human_secondary_types"]) & {"deadline_extension", "correction_notice", "rule_update"})) and r["predicted_type"] == "information" for r in current)},
        "policy_relationship_n": len(proof["auto_relations"]), "formal_policy_relations_written": 0,
        "changes_from_mechanical_merge": changes,
        "limitations": ["This is the same purposively selected development set used in earlier rule fixes; no held-out validation or cross-validation is claimed.",
                        "Bootstrap does not undo previous access to all 100 labels; intervals are conditional descriptive stability only.",
                        "Classification confidence and policy confidence are rule scores, not calibrated probabilities.",
                        "Original fine labels and secondary labels are retained; no additional people, schools, events, labels, or sources were collected.",
                        "Candidate rows are not independent labeled examples; source-level performance remains N=100.",
                        "Missing factual-safety labels and conservative information routing cannot demonstrate safe queue removal."],
    }
    protected_after = {path: digest(ROOT / path) for path in INPUTS.values()}
    assert protected_before == protected_after, "Protected inputs changed during read-only replay"
    assert all(digest(ROOT / path) == value for path, value in runtime_code_sha256.items()), "Runtime code changed during replay; rerun after implementation stabilizes"
    result["protected_inputs"] = {path: {"before": value, "after": protected_after[path], "unchanged": True} for path, value in protected_before.items()}
    write("golden100-records.json", current)
    write("comparison-records.json", {"frozen20": frozen, "repaired20": repaired, "merged7": merged})
    write("source200-replay.json", current_sources)
    write("candidate254-replay.json", candidates)
    write("policy9-evidence-replay.json", policy9)
    write("evaluation-results.json", result)
    write("misclassifications.json", [{**r, "title": original_by_id[r["source_id"]]["title"], "source_input": original_by_id[r["source_id"]]} for r in current if r["true_type"] != r["predicted_type"]])
    print(json.dumps({"comparison": {name: {key: item[key] for key in ("accuracy", "macro_f1", "weighted_f1")} for name, item in comparison.items()},
                      "paired_bootstrap_accuracy": result["paired_bootstrap_new7_vs_mechanically_merged7"]["accuracy_delta"],
                      "policy_default_binary": {k: result["policy_default_binary"][k] for k in ("true_positive", "false_positive", "false_negative", "precision", "recall", "precision_wilson95", "precision_wilson99")},
                      "candidate254": candidate_summary, "protected_inputs_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
