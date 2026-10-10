"""Pure arithmetic for the fixed seven-class replay; no classifiers or I/O.

Undefined rates are None, unsupported class metrics are zero, and abstentions
remain in all human denominators. Threshold curves are hypothetical score
filters, never authorization to classify or approve field facts automatically.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import random
from statistics import NormalDist

PRIMARY_TYPES = ("participation", "result", "information", "policy", "update", "repost", "other")
THRESHOLDS = (.70, .75, .80, .85, .90, .95)
UPDATE_TYPES = frozenset(("update", "deadline_extension", "correction_notice", "rule_update"))
POLICY_TYPES = frozenset(("policy", "policy_recognition_document", "award_policy_document", "postgraduate_policy_document", "comprehensive_evaluation_policy_document", "innovation_credit_policy_document"))


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _confidence(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def _known(value, classes):
    return isinstance(value, str) and value in classes


def _validated(rows, classes=PRIMARY_TYPES):
    rows = list(rows)
    seen = set()
    for row in rows:
        identity = str(row["source_id"])
        if identity in seen:
            raise ValueError(f"Duplicate source_id: {identity}")
        seen.add(identity)
        if not _known(row["true_type"], classes):
            raise ValueError(f"Invalid human ground truth for {identity}")
    return rows


def wilson_interval(correct, count, confidence=.95):
    """Nominal binomial interval, not a generalization or calibration guarantee."""
    if not count:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = correct / count
    scale = 1 + z * z / count
    center = (p + z * z / (2 * count)) / scale
    radius = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / scale
    return {"lower": max(0., center - radius), "upper": min(1., center + radius),
            "n": count, "confidence_level": confidence,
            "method": "Wilson score; selected development sample only"}


def _scores(rows, classes):
    support, predicted, tp = Counter(), Counter(), Counter()
    for row in rows:
        actual, guess = row["true_type"], row.get("predicted_type")
        support[actual] += 1
        if _known(guess, classes):
            predicted[guess] += 1
            tp[actual] += actual == guess
    per_class = {}
    for label in classes:
        precision = _ratio(tp[label], predicted[label]) or 0.
        recall = _ratio(tp[label], support[label]) or 0.
        f1 = _ratio(2 * precision * recall, precision + recall) or 0.
        per_class[label] = {"support": support[label], "predicted_n": predicted[label],
                            "true_positive": tp[label], "precision": precision, "recall": recall, "f1": f1}
    return {"accuracy": _ratio(sum(tp.values()), len(rows)),
            "macro_precision": sum(c["precision"] for c in per_class.values()) / len(classes),
            "macro_recall": sum(c["recall"] for c in per_class.values()) / len(classes),
            "macro_f1": sum(c["f1"] for c in per_class.values()) / len(classes),
            "weighted_f1": _ratio(sum(c["f1"] * c["support"] for c in per_class.values()), len(rows)),
            "per_class": per_class}


def classification_metrics(rows, classes=PRIMARY_TYPES):
    """Fixed-class macro metrics; unknown predictions are explicit abstentions."""
    classes = tuple(classes)
    if not classes or len(set(classes)) != len(classes):
        raise ValueError("Classes must be nonempty and unique")
    rows = _validated(rows, classes)
    matrix = [[0 for _ in classes] for _ in classes]
    index = {kind: i for i, kind in enumerate(classes)}
    wrong, abstentions, abstention_support = defaultdict(list), [], Counter()
    for row in rows:
        actual, predicted, identity = row["true_type"], row.get("predicted_type"), str(row["source_id"])
        if _known(predicted, classes):
            matrix[index[actual]][index[predicted]] += 1
        else:
            abstentions.append(identity)
            abstention_support[actual] += 1
            predicted = "ABSTAIN"
        if predicted != actual:
            wrong[(actual, predicted)].append(identity)
    return {"human_n": len(rows), **_scores(rows, classes), "fixed_class_n": len(classes),
            "zero_division": 0, "abstention_n": len(abstentions), "abstention_source_ids": sorted(abstentions),
            "abstention_by_true_type": {kind: abstention_support[kind] for kind in classes},
            "confusion_matrix": {"row_axis": "human_primary_type", "column_axis": "predicted_type",
                                 "class_order": list(classes), "matrix": matrix},
            "wrong_pairs": [{"true_type": actual, "predicted_type": predicted, "count": len(ids), "source_ids": sorted(ids)}
                            for (actual, predicted), ids in sorted(wrong.items())],
            "denominator_note": "All recorded human primary labels; unknown predictions count as errors and abstentions, never exclusions."}


def _human_update(row):
    return row["true_type"] == "update" or bool(set(row.get("human_secondary_types", [])) & UPDATE_TYPES)


def _information_wrong(row):
    return row["true_type"] != "information" or bool(set(row.get("human_secondary_types", [])) & (UPDATE_TYPES | POLICY_TYPES))


def global_threshold_curves(rows, thresholds=THRESHOLDS):
    """Confidence-only hypothetical filters, intentionally distinct from routing.

    Other/update/policy predictions can appear here at sufficient confidence;
    they do not thereby acquire permission to bypass real safety gates.
    """
    rows = _validated(rows)
    update_rows = [r for r in rows if _human_update(r)]
    all_update_misses = [r for r in update_rows if r.get("predicted_type") != "update"]
    curves = []
    for threshold in thresholds:
        selected = [r for r in rows if _confidence(r.get("confidence")) and r["confidence"] >= threshold
                    and _known(r.get("predicted_type"), PRIMARY_TYPES)]
        correct = sum(r["true_type"] == r["predicted_type"] for r in selected)
        policy_fp = [r for r in selected if r["predicted_type"] == "policy" and r["true_type"] != "policy"]
        update_missed = [r for r in selected if _human_update(r) and r["predicted_type"] != "update"]
        information_wrong = [r for r in selected if r["predicted_type"] == "information" and _information_wrong(r)]
        update_unsafe = [r for r in selected if _human_update(r) and r.get("risk_level") != "HIGH_RISK"]
        curves.append({"threshold": threshold, "hypothetical_only": True, "human_n": len(rows),
                       "auto_n": len(selected), "auto_correct_n": correct, "auto_accuracy": _ratio(correct, len(selected)),
                       "auto_accuracy_wilson95": wilson_interval(correct, len(selected)),
                       "auto_fraction": _ratio(len(selected), len(rows)), "manual_n": len(rows) - len(selected),
                       "policy_false_positive_auto_n": len(policy_fp),
                       "policy_false_positive_auto_source_ids": sorted(str(r["source_id"]) for r in policy_fp),
                       "update_human_primary_or_secondary_n": len(update_rows), "update_missed_all_n": len(all_update_misses),
                       "update_missed_auto_n": len(update_missed), "update_missed_auto_source_ids": sorted(str(r["source_id"]) for r in update_missed),
                       "update_without_high_risk_auto_n": len(update_unsafe),
                       "update_without_high_risk_auto_source_ids": sorted(str(r["source_id"]) for r in update_unsafe),
                       "information_misplacement_auto_n": len(information_wrong),
                       "information_misplacement_auto_source_ids": sorted(str(r["source_id"]) for r in information_wrong),
                       "auto_by_primary_type": {kind: sum(r["predicted_type"] == kind for r in selected) for kind in PRIMARY_TYPES},
                       "automatic_permission_granted": False})
    return curves


def policy_threshold_curves(rows, thresholds=THRESHOLDS):
    """Independent policy evidence gate + policy score, never class confidence."""
    rows = _validated(rows)
    curves = []
    positive_n = sum(r["true_type"] == "policy" for r in rows)
    for threshold in thresholds:
        positive = [r for r in rows if r.get("is_policy") is True and _confidence(r.get("policy_confidence"))
                    and r["policy_confidence"] >= threshold]
        positive_ids = {str(r["source_id"]) for r in positive}
        tp = sum(r["true_type"] == "policy" for r in positive)
        fp = [r for r in positive if r["true_type"] != "policy"]
        fn = [r for r in rows if r["true_type"] == "policy" and str(r["source_id"]) not in positive_ids]
        curves.append({"threshold": threshold, "positive_evidence_required": True, "score_field": "policy_confidence",
                       "human_positive_n": positive_n, "human_negative_n": len(rows) - positive_n,
                       "predicted_positive_n": len(positive), "predicted_positive_source_ids": sorted(positive_ids),
                       "true_positive": tp, "false_positive": len(fp), "false_negative": len(fn),
                       "true_negative": len(rows) - positive_n - len(fp), "precision": _ratio(tp, len(positive)),
                       "recall": _ratio(tp, positive_n), "false_positive_rate": _ratio(len(fp), len(rows) - positive_n),
                       "false_positive_source_ids": sorted(str(r["source_id"]) for r in fp),
                       "false_negative_source_ids": sorted(str(r["source_id"]) for r in fn),
                       "precision_wilson95": wilson_interval(tp, len(positive)), "precision_wilson99": wilson_interval(tp, len(positive), .99),
                       "automatic_relations_authorized": False})
    return curves


def routing_metrics(rows):
    """Actual classification status; factual-safety answers are separate evidence."""
    rows = list(rows)
    auto = [r for r in rows if r.get("classification_status") == "AUTO_CLASSIFIED"]
    quick = [r for r in rows if r.get("classification_status") == "NEEDS_QUICK_CONFIRM"]
    manual = [r for r in rows if r.get("classification_status") == "NEEDS_MANUAL_CLASSIFICATION"]
    info = [r for r in rows if r.get("informational_only") is True]
    known_info = [r for r in info if r.get("true_type") in PRIMARY_TYPES]
    wrong_info = [r for r in known_info if _information_wrong(r)]
    known_auto = [r for r in auto if r.get("true_type") in PRIMARY_TYPES]
    correct_auto = sum(r["predicted_type"] == r["true_type"] for r in known_auto)
    return {"total": len(rows), "auto_n": len(auto), "quick_confirm_n": len(quick), "manual_n": len(manual),
            "unknown_status_n": len(rows) - len(auto) - len(quick) - len(manual),
            "auto_fraction": _ratio(len(auto), len(rows)), "quick_confirm_fraction": _ratio(len(quick), len(rows)),
            "manual_fraction": _ratio(len(manual), len(rows)), "human_type_task_n": len(quick) + len(manual),
            "auto_by_primary_type": {kind: sum(r.get("predicted_type") == kind for r in auto) for kind in PRIMARY_TYPES},
            "manual_other_n": sum(r.get("predicted_type") == "other" for r in manual),
            "auto_labeled_n": len(known_auto), "auto_correct_n": correct_auto, "auto_accuracy": _ratio(correct_auto, len(known_auto)),
            "auto_accuracy_wilson95": wilson_interval(correct_auto, len(known_auto)),
            "auto_source_ids": sorted(str(r["source_id"]) for r in auto),
            "informational_only_n": len(info), "informational_labeled_n": len(known_info),
            "informational_unlabeled_n": len(info) - len(known_info), "informational_wrong_placement_n": len(wrong_info),
            "informational_wrong_source_ids": sorted(str(r["source_id"]) for r in wrong_info),
            "informational_placement_accuracy": _ratio(len(known_info) - len(wrong_info), len(known_info)),
            "informational_factual_safety_unanswered_n": sum(r.get("informational_safe") not in ("yes", "no") for r in info),
            "informational_factual_safety_answers": dict(Counter(r.get("informational_safe") or "unanswered" for r in info)),
            "informational_safety_certified": False, "field_facts_automatically_approved_n": 0,
            "note": "Classification routing never approves facts. Missing human factual-safety answers do not certify information removal."}


def _percentile(values, quantile):
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def paired_bootstrap(before, after, iterations=2000, seed=20261001):
    """Paired source bootstrap after development on these labels, not held out."""
    before, after = _validated(before), _validated(after)
    baseline = {str(r["source_id"]): r for r in before}
    current = {str(r["source_id"]): r for r in after}
    if baseline.keys() != current.keys():
        raise ValueError("Paired bootstrap requires the same source IDs")
    ids = sorted(baseline)
    if any(baseline[i]["true_type"] != current[i]["true_type"] for i in ids):
        raise ValueError("Paired bootstrap requires identical ground truth")
    if iterations < 1:
        raise ValueError("Bootstrap iterations must be positive")
    keys = ("accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")
    base_scores, new_scores = _scores(before, PRIMARY_TYPES), _scores(after, PRIMARY_TYPES)
    result = {"paired_n": len(ids), "iterations": iterations, "seed": seed,
              "confidence_level": .95, "independent_validation": False,
              "method": "Paired source-level percentile bootstrap, fixed seven-class macro denominator",
              "limitation": "Both rule versions were developed using this same purposive 100-label set. Resampling estimates conditional stability; it does not remove selection/development bias, is not cross-validation, and is not independent generalization evidence."}
    if not ids:
        return {**result, **{key + "_delta": {"estimate": None, "lower": None, "upper": None} for key in keys}}
    draws = {key: [] for key in keys}
    randomizer = random.Random(seed)
    for _ in range(iterations):
        sample = randomizer.choices(ids, k=len(ids))
        b = _scores([baseline[i] for i in sample], PRIMARY_TYPES)
        a = _scores([current[i] for i in sample], PRIMARY_TYPES)
        for key in keys:
            draws[key].append(a[key] - b[key])
    for key in keys:
        result[key + "_delta"] = {"estimate": new_scores[key] - base_scores[key],
                                   "lower": _percentile(draws[key], .025), "upper": _percentile(draws[key], .975)}
    result["improved_source_ids"] = [i for i in ids if baseline[i].get("predicted_type") != baseline[i]["true_type"] and current[i].get("predicted_type") == current[i]["true_type"]]
    result["regressed_source_ids"] = [i for i in ids if baseline[i].get("predicted_type") == baseline[i]["true_type"] and current[i].get("predicted_type") != current[i]["true_type"]]
    return result


def build_evaluation_records(annotations, predictions, human_mapping):
    """Join saved human truth without interpreting titles, notes, or model output."""
    from copy import deepcopy
    records, seen = [], set()
    for annotation in annotations:
        identity = str(annotation["source_id"])
        if identity in seen:
            raise ValueError(f"Duplicate human source_id: {identity}")
        seen.add(identity)
        fine = annotation["human_primary_type"]
        if fine not in human_mapping:
            raise ValueError(f"Unknown human label: {fine}")
        prediction = deepcopy(predictions.get(identity, {}))
        records.append({**prediction, "source_id": identity,
                        "predicted_type": prediction.get("predicted_type"),
                        "true_type": human_mapping[fine], "human_primary_type": fine,
                        "human_secondary_types": deepcopy(annotation.get("human_secondary_types", [])),
                        "informational_safe": annotation.get("informational_safe"),
                        "human_annotation": deepcopy(annotation)})
    return records


def paired_policy_error_test(before, after):
    """Exact paired sign/McNemar test on non-policy source false positives.

    New independent is_policy evidence decisions take precedence over seven-way
    labels when supplied; the old baseline only has its mapped policy label.
    """
    before, after = _validated(before), _validated(after)
    baseline = {str(r["source_id"]): r for r in before}
    current = {str(r["source_id"]): r for r in after}
    if baseline.keys() != current.keys():
        raise ValueError("Paired policy test requires the same source IDs")
    if any(baseline[i]["true_type"] != current[i]["true_type"] for i in baseline):
        raise ValueError("Paired policy test requires identical ground truth")
    ids = sorted(i for i in baseline if baseline[i]["true_type"] != "policy")
    def predicts_policy(row):
        return row["is_policy"] is True if "is_policy" in row else row.get("predicted_type") == "policy"
    old_errors = {i for i in ids if predicts_policy(baseline[i])}
    new_errors = {i for i in ids if predicts_policy(current[i])}
    improved, regressed = old_errors - new_errors, new_errors - old_errors
    discordant = len(improved) + len(regressed)
    tail = sum(math.comb(discordant, k) for k in range(min(len(improved), len(regressed)) + 1))
    p = min(1., 2 * tail / 2 ** discordant)
    return {"human_nonpolicy_n": len(ids), "old_false_positive_n": len(old_errors), "new_false_positive_n": len(new_errors),
            "improved_pairs": len(improved), "regressed_pairs": len(regressed),
            "improved_source_ids": sorted(improved), "regressed_source_ids": sorted(regressed),
            "exact_two_sided_p": p, "significant_at_05": p < .05,
            "method": "Exact two-sided paired McNemar/sign test restricted to unchanged human nonpolicy sources",
            "limitation": "Exploratory same-development-set comparison; nominal p-value does not remove rule tuning or sample-selection bias."}
