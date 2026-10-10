"""Read-only evaluation of frozen predictions against recorded human decisions.

This module does not classify documents, trust caller-supplied identities as
authentication, or change thresholds. The annotation service is responsible for
server-owned actor, timestamp, provenance and monotonic exposure records.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from numbers import Real

from app.services.source_document_classifier import DOCUMENT_TYPES, POLICY_TYPES


THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
POLICY_CHECKS = (
    "is_policy", "extraction_correct", "recognition_type_correct", "match_correct",
    "no_track_ambiguity", "validity_clear",
)
RELATION_CHECKS = (
    "school_correct", "competition_correct", "source_valid",
    "recognition_type_correct", "match_correct",
)
INFORMATIONAL_TYPES = {"completion_news", "event_news", "competition_intro"}
HIGH_RISK_TYPES = {"deadline_extension", "correction_notice", "rule_update"}
NOTICE_TYPES = {
    "registration_notice", "organization_notice", "selection_notice",
    "recommendation_notice", "result_notice", "publicity_notice",
}
NEWS_TYPES = {"completion_news", "event_news"}


def _identity(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip() or None


def _recorded_human(row):
    actor = row.get("annotated_by")
    if not _identity(actor):
        return False
    timestamp = row.get("annotated_at")
    if not isinstance(timestamp, str) or not ("T" in timestamp or " " in timestamp):
        return False
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        row.get("status") == "annotated"
        and row.get("skipped") is not True
        and row.get("label_provenance") == "human"
    )


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _confidence(item):
    value = item.get("predicted_confidence")
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def _classification_metrics(records):
    confusion = {}
    scored = [row for row in records if row["item"].get("predicted_type") in DOCUMENT_TYPES]
    for row in scored:
        actual = row["annotation"]["human_primary_type"]
        predicted = row["item"]["predicted_type"]
        counts = confusion.setdefault(actual, {})
        counts[predicted] = counts.get(predicted, 0) + 1
    per_class = {}
    correct = 0
    for kind in DOCUMENT_TYPES:
        tp = confusion.get(kind, {}).get(kind, 0)
        actual = sum(confusion.get(kind, {}).values())
        predicted = sum(counts.get(kind, 0) for counts in confusion.values())
        correct += tp
        per_class[kind] = {
            "support": actual, "predicted_n": predicted,
            "tp": tp, "fp": predicted - tp, "fn": actual - tp,
            "precision": _ratio(tp, predicted), "recall": _ratio(tp, actual),
            "f1": _ratio(2 * tp, actual + predicted),
        }
    return {
        "human_n": len(records), "scored_n": len(scored), "correct_n": correct,
        "accuracy": _ratio(correct, len(scored)),
        "per_class": per_class, "confusion_matrix": confusion,
    }


def _dangerous_errors(records):
    definitions = (
        ("notice_to_policy", NOTICE_TYPES, POLICY_TYPES,
         "Primary registration/organization/selection/recommendation/result/publicity notice predicted as any of the five policy types."),
        ("news_to_policy", NEWS_TYPES, POLICY_TYPES,
         "Primary completion_news or event_news predicted as any of the five policy types."),
        ("registration_to_postgraduate", {"registration_notice"}, {"postgraduate_policy_document"},
         "Primary registration_notice predicted as postgraduate_policy_document."),
        ("result_or_news_to_comprehensive", {"result_notice", *NEWS_TYPES},
         {"comprehensive_evaluation_policy_document"},
         "Primary result_notice, completion_news or event_news predicted as comprehensive_evaluation_policy_document."),
    )
    result = {}
    for name, actual_types, predicted_types, definition in definitions:
        eligible = [row for row in records
                    if row["annotation"]["human_primary_type"] in actual_types
                    and row["item"].get("predicted_type") in DOCUMENT_TYPES]
        errors = [row["source_id"] for row in eligible
                  if row["item"]["predicted_type"] in predicted_types]
        result[name] = {
            "count": len(errors), "denominator": len(eligible),
            "rate": _ratio(len(errors), len(eligible)), "source_ids": errors,
            "definition": definition + " Rate denominator: eligible human primary labels with a known prediction; groups may overlap.",
        }
    return result


def _automatic_candidate(item, threshold):
    confidence = _confidence(item)
    return (
        item.get("predicted_type") in DOCUMENT_TYPES
        and confidence is not None and confidence >= threshold
    )


def _threshold_curves(items, records):
    curves = []
    for threshold in THRESHOLDS:
        automatic = [row for row in records if _automatic_candidate(row["item"], threshold)]
        wrong = [row for row in automatic
                 if row["item"]["predicted_type"] != row["annotation"]["human_primary_type"]]
        policy_wrong = [row for row in wrong if row["item"]["predicted_type"] in POLICY_TYPES]
        policy_false_positive = [row for row in policy_wrong
                                 if row["annotation"]["human_primary_type"] not in POLICY_TYPES]
        dataset_auto = sum(_automatic_candidate(item, threshold) for item in items)
        curves.append({
            "threshold": threshold, "labeled_n": len(records),
            "auto_n": len(automatic), "review_n": len(records) - len(automatic),
            "wrong_auto_n": len(wrong), "policy_wrong_auto_n": len(policy_wrong),
            "policy_false_positive_auto_n": len(policy_false_positive),
            "auto_accuracy": _ratio(len(automatic) - len(wrong), len(automatic)),
            "auto_coverage": _ratio(len(automatic), len(records)),
            "dataset_auto_n": dataset_auto, "dataset_review_n": len(items) - dataset_auto,
            "dataset_auto_coverage": _ratio(dataset_auto, len(items)),
        })
    return curves


def _per_class_threshold_curves(items, records):
    result = {}
    for kind in DOCUMENT_TYPES:
        predicted_items = [item for item in items if item.get("predicted_type") == kind]
        predicted_records = [row for row in records if row["item"].get("predicted_type") == kind]
        actual_support = sum(row["annotation"]["human_primary_type"] == kind for row in records)
        result[kind] = [
            {**curve, "actual_support": actual_support, "predicted_labeled_n": len(predicted_records)}
            for curve in _threshold_curves(predicted_items, predicted_records)
        ]
    return result


def _audit_metrics(rows, checks, kind):
    grouped = defaultdict(list)
    invalid = 0
    observed_errors = set()
    for value in rows or []:
        if not isinstance(value, dict):
            invalid += 1
            continue
        row = value.get("annotation") if "annotation" in value else value
        identity = _identity(value.get("audit_id"))
        if not isinstance(row, dict) or not identity or not _recorded_human(row):
            invalid += 1
            continue
        # A nested annotation cannot attribute its answers to a different item.
        if row.get("audit_id") is not None and _identity(row["audit_id"]) != identity:
            invalid += 1
            continue
        answers = row.get("answers")
        if isinstance(answers, dict) and any(answers.get(key) == "no" for key in checks):
            observed_errors.add(identity)
        if not isinstance(answers, dict) or any(answers.get(key) not in {"yes", "no", "unsure"} for key in checks):
            invalid += 1
            continue
        grouped[identity].append(row)
    accepted, rejected, unsure, conflicts = [], [], [], []
    duplicates = 0
    per_check = {key: {"yes": 0, "no": 0, "unsure": 0} for key in checks}
    for identity, group in grouped.items():
        signatures = {tuple(row["answers"][key] for key in checks) for row in group}
        if len(signatures) > 1:
            conflicts.append(identity)
            continue
        duplicates += len(group) - 1
        answers = group[0]["answers"]
        for key in checks:
            per_check[key][answers[key]] += 1
        if any(answers[key] == "no" for key in checks):
            rejected.append(identity)
        elif any(answers[key] == "unsure" for key in checks):
            unsure.append(identity)
        else:
            accepted.append(identity)
    complete = len(accepted) + len(rejected) + len(unsure)
    action = None
    if kind == "relations" and observed_errors:
        action = "SUSPEND_AUTO_CONFIRMATION_AND_USE_NEEDS_QUICK_CONFIRM"
    return {
        "complete_n": complete, "accepted_n": len(accepted),
        "rejected_n": len(rejected), "unsure_n": len(unsure),
        "acceptance_rate": _ratio(len(accepted), complete),
        "incomplete_or_invalid_n": invalid, "duplicate_n": duplicates,
        "conflicting_audit_ids": sorted(conflicts), "per_check": per_check,
        "accepted_audit_ids": accepted, "rejected_audit_ids": rejected,
        "unsure_audit_ids": unsure, "obvious_error_n": len(observed_errors),
        "observed_error_audit_ids": sorted(observed_errors),
        "recommended_action": action, "action_applied": False,
    }


def _informational_metrics(items, records):
    routed = {identity for identity, item in items.items()
              if str(item.get("classification_status", "")).lower() == "informational_only"
              or item.get("informational_only") is True}
    labels = [row for row in records if row["source_id"] in routed]
    scored = [row for row in labels if row["item"].get("predicted_type") in DOCUMENT_TYPES]
    correct = sum(row["annotation"]["human_primary_type"] == row["item"]["predicted_type"] for row in scored)
    high_risk = [row["source_id"] for row in labels
                 if row["annotation"]["human_primary_type"] in HIGH_RISK_TYPES
                 or bool(set(row["annotation"].get("human_secondary_types") or []) & HIGH_RISK_TYPES)]
    safety_counts = {answer: sum(row["annotation"].get("informational_safe") == answer for row in labels)
                     for answer in ("yes", "no", "unsure")}
    reviewed = sum(safety_counts.values())
    fully_decided = bool(labels) and reviewed == len(labels) and not safety_counts["unsure"]
    return {
        "routed_n": len(routed), "labeled_n": len(labels), "scored_n": len(scored),
        "type_accuracy": _ratio(correct, len(scored)),
        "high_risk_misroute_n": len(high_risk), "high_risk_source_ids": high_risk,
        "safety_reviewed_n": reviewed, "safe_n": safety_counts["yes"],
        "unsafe_n": safety_counts["no"], "unsure_n": safety_counts["unsure"],
        "safety_missing_n": len(labels) - reviewed,
        "safety_accuracy": _ratio(safety_counts["yes"], len(labels)) if fully_decided else None,
        "safety_certified": False,
        "limitation": "Primary type agreement cannot establish absence of hidden deadline, rule or official-fact changes. Explicit informational_safe review is separate; no production safety certification is issued.",
    }


def evaluate_golden_set(items, annotations, policy_audits=None, relation_audits=None) -> dict:
    """Describe evidence without mutating inputs or applying automation settings.

    Ratios use 0..1 and are None where their denominator is absent. The six
    curves are confidence-only simulations, not actual routing decisions; risk
    gates and automation permissions remain owned by the existing application.
    """
    frozen = {}
    for item in items:
        identity = _identity(item.get("source_id"))
        if identity is None:
            raise ValueError("Frozen source requires a source_id")
        if identity in frozen and frozen[identity] != item:
            raise ValueError(f"Conflicting frozen source: {identity}")
        frozen[identity] = item
    grouped = defaultdict(list)
    invalid = 0
    for row in annotations:
        if not isinstance(row, dict):
            invalid += 1
            continue
        identity = _identity(row.get("source_id"))
        if identity not in frozen or not _recorded_human(row) or row.get("human_primary_type") not in DOCUMENT_TYPES:
            invalid += 1
            continue
        grouped[identity].append(row)
    records, conflicts = [], []
    duplicates = 0
    for identity, group in grouped.items():
        signatures = {(row["human_primary_type"], row.get("informational_safe"),
                       tuple(sorted(row.get("human_secondary_types") or []))) for row in group}
        if len(signatures) > 1:
            conflicts.append(identity)
            continue
        duplicates += len(group) - 1
        # Saved exposure describes the moment of this human label. Revealing a
        # prediction later must not rewrite an already-blind label's history.
        exposed = any(row.get("prediction_exposed") is True for row in group)
        blind = not exposed and all(row.get("prediction_exposed") is False for row in group)
        records.append({"source_id": identity, "item": frozen[identity],
                        "annotation": group[0], "exposed": exposed, "blind": blind})
    blind = [row for row in records if row["blind"]]
    all_metrics = _classification_metrics(records)
    blind_metrics = _classification_metrics(blind)
    policies = _audit_metrics(policy_audits, POLICY_CHECKS, "policies")
    relations = _audit_metrics(relation_audits, RELATION_CHECKS, "relations")
    informational = _informational_metrics(frozen, records)
    unscorable = [row["source_id"] for row in records if row["item"].get("predicted_type") not in DOCUMENT_TYPES]
    missing_classes = [kind for kind, stats in all_metrics["per_class"].items() if not stats["support"]]
    blockers = []
    if len(records) < 100:
        blockers.append(f"Human primary labels incomplete: {len(records)}/100.")
    for name, stats in (("Policy", policies), ("Relation", relations)):
        if stats["complete_n"] < 20:
            blockers.append(f"{name} human audits incomplete: {stats['complete_n']}/20.")
        if stats["obvious_error_n"] or stats["unsure_n"] or stats["conflicting_audit_ids"]:
            blockers.append(f"{name} audits contain rejected, unsure or conflicting decisions.")
    if missing_classes:
        blockers.append("Some primary classes lack human support; class calibration is unavailable.")
    if conflicts or unscorable:
        blockers.append("Conflicting labels or unknown frozen prediction types require review.")
    if informational["safety_reviewed_n"] < informational["routed_n"]:
        blockers.append("Informational safety reviews are missing for routed samples; primary labels alone are insufficient.")
    if informational["unsafe_n"] or informational["unsure_n"] or informational["high_risk_misroute_n"]:
        blockers.append("Informational routing has unsafe, unsure or human-confirmed high-risk cases requiring review.")
    ready = not blockers
    recommendation = None
    if ready:
        recommendation = {
            "status": "EXPLORATORY_ONLY", "requires_independent_validation": True,
            "message": "Review the six descriptive confidence curves and collect an independent blinded validation set before selecting any production or per-class threshold. No best threshold is inferred from the evaluation set itself.",
            "suggested_threshold": None,
            "per_class_thresholds": {kind: None for kind in DOCUMENT_TYPES},
        }
    return {
        "status": "EXPLORATORY" if ready else "BLOCKED", "total": len(frozen),
        "human_n": len(records), "blind_human_n": len(blind),
        "exposed_human_n": sum(row["exposed"] for row in records),
        "unknown_exposure_human_n": sum(not row["exposed"] and not row["blind"] for row in records),
        "human_coverage": _ratio(len(records), len(frozen)),
        "excluded_annotation_n": invalid, "duplicate_annotation_n": duplicates,
        "conflicting_source_ids": sorted(conflicts), "unscorable_source_ids": unscorable,
        "accuracy": all_metrics["accuracy"], "per_class": all_metrics["per_class"],
        "confusion_matrix": all_metrics["confusion_matrix"],
        "all_human": all_metrics, "blind_human": blind_metrics,
        "dangerous_errors": _dangerous_errors(records),
        "threshold_curves": _threshold_curves(list(frozen.values()), records),
        "blind_threshold_curves": _threshold_curves(list(frozen.values()), blind),
        "per_class_threshold_curves": _per_class_threshold_curves(list(frozen.values()), records),
        "threshold_curve_scope": "Exploratory confidence-only simulation; labeled_n is the error denominator and dataset coverage is not accuracy. Existing risk gates are not simulated or changed.",
        "informational": informational,
        "policy_audit": policies, "relation_audit": relations,
        "readiness": {
            "ready": ready, "required_human_n": 100, "required_policy_n": 20,
            "required_relation_n": 20, "missing_classes": missing_classes, "blockers": blockers,
        },
        "recommendation": recommendation,
        "calibration_validated": False, "thresholds_applied": False,
    }
