"""Pure descriptive calibration; recorded human labels are never inferred or edited.

This layer augments the original evaluator without changing its API or behavior.
It performs no classification, I/O, database writes, or production configuration.
"""

from __future__ import annotations

from collections import defaultdict
import math

from app.services.golden_set_metrics import (
    HIGH_RISK_TYPES, INFORMATIONAL_TYPES, NEWS_TYPES, NOTICE_TYPES,
    _automatic_candidate, _confidence, _identity, _recorded_human,
    evaluate_golden_set,
)
from app.services.source_document_classifier import DOCUMENT_TYPES, POLICY_TYPES


DANGER_GROUPS = (
    ("registration_to_recognition", {"registration_notice"}, {"policy_recognition_document"},
     "Human registration_notice predicted as policy_recognition_document.", None),
    ("ordinary_notice_to_postgraduate", NOTICE_TYPES, {"postgraduate_policy_document"},
     "Human registration, organization, selection, recommendation, result or publicity notice predicted as postgraduate_policy_document.", None),
    ("award_result_news_to_award_policy", {"result_notice", *NEWS_TYPES}, {"award_policy_document"},
     "Human result_notice, completion_news or event_news predicted as award_policy_document.",
     "The 20-class human taxonomy has no separate award-news label. Result/completion/event labels are an explicit proxy; titles and notes are not reinterpreted."),
    ("ordinary_news_to_comprehensive", NEWS_TYPES, {"comprehensive_evaluation_policy_document"},
     "Human completion_news or event_news predicted as comprehensive_evaluation_policy_document.", None),
    ("publicity_selection_to_policy", {"publicity_notice", "selection_notice"}, POLICY_TYPES,
     "Human publicity_notice or selection_notice predicted as any policy type.",
     "Publicity/selection labels proxy publicity and school-selection pages. School scope is not separately human-annotated, so no narrower claim is made."),
)


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _known_type(value, kinds):
    return isinstance(value, str) and value in kinds


def _validated_records(items, annotations):
    frozen = {}
    for item in items:
        identity = _identity(item.get("source_id")) if isinstance(item, dict) else None
        if identity is None:
            raise ValueError("Frozen source requires a source_id")
        if identity in frozen:
            raise ValueError(f"Duplicate frozen source_id: {identity}")
        frozen[identity] = item
    records, accepted, invalid_ids, unknown_ids, missing_snapshot, mismatch = [], [], [], [], [], []
    seen = set()
    invalid_n = 0
    for annotation in annotations:
        identity = _identity(annotation.get("source_id")) if isinstance(annotation, dict) else None
        if identity is not None:
            if identity in seen:
                raise ValueError(f"Duplicate annotation source_id: {identity}")
            seen.add(identity)
        secondary = annotation.get("human_secondary_types") if isinstance(annotation, dict) else None
        valid = (isinstance(annotation, dict) and identity in frozen
                 and _recorded_human(annotation)
                 and annotation.get("human_primary_type") in DOCUMENT_TYPES
                 and isinstance(secondary, list)
                 and all(kind in DOCUMENT_TYPES for kind in secondary))
        if not valid:
            invalid_n += 1
            if identity is not None:
                invalid_ids.append(identity)
                if identity not in frozen:
                    unknown_ids.append(identity)
            continue
        item = frozen[identity]
        if "predicted_type" not in annotation or "predicted_confidence" not in annotation:
            missing_snapshot.append(identity)
        elif (annotation["predicted_type"] != item.get("predicted_type")
              or _confidence(annotation) is None
              or _confidence(annotation) != _confidence(item)):
            mismatch.append(identity)
        accepted.append(annotation)
        records.append({"source_id": identity, "item": item, "annotation": annotation})
    missing_human = sorted(set(frozen) - {row["source_id"] for row in records})
    invalid_predictions = sorted(identity for identity, item in frozen.items()
                                 if item.get("predicted_type") not in DOCUMENT_TYPES)
    invalid_confidence = sorted(identity for identity, item in frozen.items() if _confidence(item) is None)
    complete = len(frozen) == len(records) == 100 and not invalid_n
    issues = []
    if not complete:
        issues.append(f"Exactly 100 unique frozen sources and recorded human labels required; sources={len(frozen)}, human={len(records)}, invalid={invalid_n}.")
    for name, identities in (
        ("Missing human labels", missing_human), ("Invalid annotation rows", invalid_ids),
        ("Unknown prediction types", invalid_predictions), ("Invalid prediction confidence", invalid_confidence),
        ("Missing saved prediction snapshot", missing_snapshot), ("Saved prediction differs from supplied prediction", mismatch),
    ):
        if identities:
            issues.append(f"{name}: {len(identities)}.")
    integrity = {
        "required_human_n": 100, "source_n": len(frozen), "human_n": len(records),
        "unique_source_ids": True, "unique_annotation_ids": True,
        "complete_100_human": complete, "invalid_annotation_n": invalid_n,
        "invalid_annotation_source_ids": sorted(invalid_ids),
        "unknown_annotation_source_ids": sorted(unknown_ids),
        "missing_human_source_ids": missing_human,
        "invalid_prediction_source_ids": invalid_predictions,
        "invalid_confidence_source_ids": invalid_confidence,
        "missing_prediction_snapshot_source_ids": sorted(missing_snapshot),
        "prediction_mismatch_source_ids": sorted(mismatch),
        "frozen_prediction_match": not (missing_snapshot or mismatch or missing_human or invalid_n),
        "issues": issues,
        "ground_truth": "Unchanged recorded human_primary_type; neither model predictions, secondary labels, titles nor notes replace primary truth.",
        "snapshot_note": "Prediction mismatches are surfaced and never change human truth. A caller doing replay must identify the replay context separately from original snapshot integrity.",
    }
    return records, accepted, integrity


def _error_rate(records, actual_types, predicted_types, definition, proxy=None):
    eligible = [row for row in records if row["annotation"]["human_primary_type"] in actual_types]
    errors = sorted(row["source_id"] for row in eligible if _known_type(row["item"].get("predicted_type"), predicted_types))
    return {
        "count": len(errors), "denominator": len(eligible),
        "rate": _ratio(len(errors), len(eligible)), "source_ids": errors,
        "unscorable_n": sum(row["item"].get("predicted_type") not in DOCUMENT_TYPES for row in eligible),
        "definition": definition,
        "denominator_definition": "All accepted human primary labels in the actual-type group, including unknown predictions; groups may overlap.",
        "proxy_limitation": proxy,
    }


def _danger_groups(records):
    return {name: _error_rate(records, actual, predicted, definition, proxy)
            for name, actual, predicted, definition, proxy in DANGER_GROUPS}


def _placement_wrong(row):
    annotation = row["annotation"]
    return (_known_type(row["item"].get("predicted_type"), INFORMATIONAL_TYPES)
            and (annotation["human_primary_type"] not in INFORMATIONAL_TYPES
                 or bool(set(annotation["human_secondary_types"]) & HIGH_RISK_TYPES)))


def _wilson95(correct, count):
    if not count:
        return None
    z = 1.959963984540054
    proportion = correct / count
    scale = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / scale
    radius = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / scale
    return {"lower": max(0, center - radius), "upper": min(1, center + radius), "n": count,
            "method": "Wilson score interval, nominal 95%; selected-set uncertainty only, not population validation."}


def _extend_curves(curves, records):
    for curve in curves:
        automatic = [row for row in records if _automatic_candidate(row["item"], curve["threshold"])]
        groups = _danger_groups(automatic)
        dangerous_ids = sorted({identity for group in groups.values() for identity in group["source_ids"]})
        misplaced = sorted(row["source_id"] for row in automatic if _placement_wrong(row))
        subtype = sorted(row["source_id"] for row in automatic
                         if row["annotation"]["human_primary_type"] in POLICY_TYPES
                         and row["item"]["predicted_type"] in POLICY_TYPES
                         and row["annotation"]["human_primary_type"] != row["item"]["predicted_type"])
        curve.update({
            "policy_subtype_confusion_auto_n": len(subtype),
            "policy_subtype_confusion_auto_source_ids": subtype,
            "dangerous_error_auto_n": len(dangerous_ids),
            "dangerous_error_auto_source_ids": dangerous_ids,
            "calibration_dangerous_errors": groups,
            "informational_wrong_placement_auto_n": len(misplaced),
            "informational_wrong_placement_auto_source_ids": misplaced,
            "auto_accuracy_wilson95": _wilson95(curve["auto_n"] - curve["wrong_auto_n"], curve["auto_n"]),
            "small_sample": curve["auto_n"] < 30,
        })


def analyze_calibration(items, annotations) -> dict:
    """Return descriptive evidence from immutable inputs; never choose a threshold.

    Duplicate identities fail closed. Invalid human records are excluded and
    named; missing/invalid prediction snapshots are exposed in integrity. A
    snapshot mismatch is expected for explicitly identified offline replay and
    does not alter the underlying human primary label.
    """
    items, annotations = list(items), list(annotations)
    records, accepted, integrity = _validated_records(items, annotations)
    result = evaluate_golden_set(items, accepted)
    result["excluded_annotation_n"] = integrity["invalid_annotation_n"]
    classes = result["per_class"]
    supported = [kind for kind in DOCUMENT_TYPES if classes[kind]["support"]]

    def macro(kinds):
        return {"class_n": len(kinds), "zero_division": 0,
                **{metric: sum(classes[kind][metric] or 0 for kind in kinds) / len(kinds) if kinds else None
                   for metric in ("precision", "recall", "f1")}}

    matrix = result["confusion_matrix"]
    pairs = defaultdict(list)
    for row in records:
        actual, predicted = row["annotation"]["human_primary_type"], row["item"].get("predicted_type")
        if predicted in DOCUMENT_TYPES and actual != predicted:
            pairs[actual, predicted].append(row["source_id"])
    non_policy = set(DOCUMENT_TYPES) - POLICY_TYPES
    policy_predicted = [row for row in records if _known_type(row["item"].get("predicted_type"), POLICY_TYPES)]
    policy_wrong = sorted(row["source_id"] for row in policy_predicted
                          if row["annotation"]["human_primary_type"] != row["item"]["predicted_type"])
    policy_subtype = sorted(row["source_id"] for row in policy_predicted
                            if row["annotation"]["human_primary_type"] in POLICY_TYPES
                            and row["source_id"] in policy_wrong)
    policy_human_n = sum(row["annotation"]["human_primary_type"] in POLICY_TYPES for row in records)
    result.update({
        "analysis_version": "golden-calibration-1", "integrity": integrity,
        "macro_average_all20": macro(list(DOCUMENT_TYPES)),
        "macro_average_supported": macro(supported),
        "weighted_f1": _ratio(sum(classes[kind]["support"] * (classes[kind]["f1"] or 0)
                                   for kind in DOCUMENT_TYPES), result["all_human"]["scored_n"]),
        "class_support": {kind: sum(row["annotation"]["human_primary_type"] == kind for row in records)
                          for kind in DOCUMENT_TYPES},
        "unsupported_classes": [kind for kind in DOCUMENT_TYPES if kind not in supported],
        "aggregate_metric_scope": "Known prediction types only, matching the base evaluator; unsupported class metrics use zero_division=0 for macro/weighted aggregation. Full primary human counts are in class_support; invalid predictions are listed in integrity.",
        "full_confusion_matrix": {"class_order": list(DOCUMENT_TYPES),
                                  "row_axis": "human_primary_type", "column_axis": "predicted_type",
                                  "matrix": [[matrix.get(actual, {}).get(predicted, 0)
                                              for predicted in DOCUMENT_TYPES] for actual in DOCUMENT_TYPES]},
        "misclassification_pairs": sorted(
            [{"human_primary_type": actual, "predicted_type": predicted, "count": len(identities),
              "source_ids": sorted(identities)} for (actual, predicted), identities in pairs.items()],
            key=lambda row: (-row["count"], row["human_primary_type"], row["predicted_type"])),
        "calibration_dangerous_errors": _danger_groups(records),
        "policy_false_positive": _error_rate(records, non_policy, POLICY_TYPES,
                                               "Any human non-policy primary type predicted as any policy type."),
        "policy_wrong_class": {"count": len(policy_wrong), "denominator": len(policy_predicted),
                               "rate": _ratio(len(policy_wrong), len(policy_predicted)), "source_ids": policy_wrong,
                               "definition": "Wrong exact class among all policy predictions; includes non-policy false positives and policy-subtype confusion."},
        "policy_subtype_confusion": {"count": len(policy_subtype), "denominator": policy_human_n,
                                     "rate": _ratio(len(policy_subtype), policy_human_n), "source_ids": policy_subtype},
        "small_sample_note": "Fewer than 30 selected examples is flagged descriptively, not used as a sufficient calibration criterion. This selected Golden Set and rule scores cannot establish population probabilities or safe automation.",
    })
    _extend_curves(result["threshold_curves"], records)
    blind = [row for row in records if row["annotation"].get("prediction_exposed") is False]
    _extend_curves(result["blind_threshold_curves"], blind)
    for kind, curves in result["per_class_threshold_curves"].items():
        _extend_curves(curves, [row for row in records if row["item"].get("predicted_type") == kind])

    informational = [row for row in records if _known_type(row["item"].get("predicted_type"), INFORMATIONAL_TYPES)]
    misplaced = sorted(row["source_id"] for row in informational if _placement_wrong(row))
    answers = {answer: sum(row["annotation"].get("informational_safe") == answer for row in informational)
               for answer in ("yes", "no", "unsure")}
    missing = len(informational) - sum(answers.values())
    if not informational:
        factual_status = "NO_ELIGIBLE_SAMPLES"
    elif answers["no"]:
        factual_status = "OBSERVED_UNSAFE"
    elif missing or answers["unsure"]:
        factual_status = "UNANSWERED"
    else:
        factual_status = "REVIEWED_NO_OBSERVED_UNSAFE"
    result["informational"].update({
        "predicted_informational_n": len(informational),
        "wrong_placement_n": len(misplaced), "wrong_placement_source_ids": misplaced,
        "wrong_placement_rate": _ratio(len(misplaced), len(informational)),
        "wrong_placement_definition": "Predicted informational class with human primary outside informational classes OR a human secondary deadline_extension/correction_notice/rule_update label. This evaluates proposed classification placement, independently of current routing status.",
        "observed_placement_risk_status": "OBSERVED_PLACEMENT_ERROR" if misplaced else (
            "NO_OBSERVED_PLACEMENT_ERROR" if informational else "NO_ELIGIBLE_SAMPLES"),
        "factual_safety_scope": "All human-labeled predicted informational classes, independent of current routing status.",
        "factual_safety_answers": answers, "factual_safety_missing_n": missing,
        "factual_safety_status": factual_status,
    })
    if integrity["issues"]:
        result["readiness"]["blockers"].extend(integrity["issues"])
        result["readiness"]["ready"] = False
        result["status"] = "BLOCKED"
        result["recommendation"] = None
    return result
