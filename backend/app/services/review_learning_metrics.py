"""Pure comparison and replay arithmetic; never persist samples or update models.

Every agreement denominator contains only explicitly supplied human labels.
Missing predictions remain abstentions in those denominators. Field agreement
is a micro average over human-labeled fields, not an average of row averages.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone

from app.services.review_shadow_predictor import predict_shadow, prediction_features


ERROR_TYPES = (
    "TITLE_AMBIGUOUS", "POLICY_FALSE_POSITIVE", "POLICY_FALSE_NEGATIVE",
    "EDITION_CONFUSION", "SCHOOL_RELATION_CONFUSION", "SOURCE_TYPE_CONFUSION",
    "MULTI_LABEL_CONFUSION", "UNKNOWN",
)
_DIMENSIONS = {
    "primary": ("shadow_primary_type", "human_primary_type"),
    "secondary": ("shadow_secondary_type", "human_secondary_type"),
    "risk": ("shadow_risk_level", "human_risk_level"),
    "action": ("shadow_suggested_action", "human_action"),
}


def _label(value):
    return value if isinstance(value, str) and value.strip() else None


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def compare_prediction(shadow: dict, human: dict) -> dict:
    """Record observable disagreements, without guessing their causal origin."""
    result = {}
    for dimension, (predicted_key, human_key) in _DIMENSIONS.items():
        actual = _label(human.get(human_key))
        result[dimension + "_match"] = shadow.get(predicted_key) == actual if actual is not None else None
    actual_policy, predicted_policy = human.get("human_policy"), shadow.get("shadow_policy_prediction")
    result["policy_match"] = (
        type(predicted_policy) is bool and predicted_policy == actual_policy
        if type(actual_policy) is bool else None
    )
    human_fields = human.get("human_field_decisions")
    shadow_fields = shadow.get("shadow_field_decisions")
    shadow_fields = shadow_fields if isinstance(shadow_fields, dict) else {}
    field_matches = {field: shadow_fields.get(field) == action for field, action in human_fields.items()
                     if _label(action) is not None} if isinstance(human_fields, dict) else {}
    result.update({
        "field_matches": field_matches, "field_denominator": len(field_matches),
        "field_matched": sum(field_matches.values()),
        "field_match_rate": _ratio(sum(field_matches.values()), len(field_matches)),
    })
    # Baseline has no relation prediction. A recorded human relation decision
    # alone supplies no evidence of a model relation error.
    relation_truth = _label(human.get("human_relation_decision"))
    relation_guess = _label(shadow.get("shadow_relation_decision"))
    result["relation_match"] = (relation_truth == relation_guess
                                if relation_truth is not None and relation_guess is not None else None)
    errors = []
    if result["primary_match"] is False and _label(shadow.get("shadow_primary_type")) is not None:
        errors.append("SOURCE_TYPE_CONFUSION")
    if result["secondary_match"] is False and _label(shadow.get("shadow_secondary_type")) is not None:
        errors.append("MULTI_LABEL_CONFUSION")
    if result["policy_match"] is False and type(predicted_policy) is bool:
        errors.append("POLICY_FALSE_POSITIVE" if predicted_policy else "POLICY_FALSE_NEGATIVE")
    if result["relation_match"] is False:
        errors.append("SCHOOL_RELATION_CONFUSION")
    unknown = any(result[key] is False for key in ("risk_match", "action_match")) or any(
        not match for match in field_matches.values())
    unknown = unknown or any(result[dimension + "_match"] is False and _label(shadow.get(predicted_key)) is None
                             for dimension, (predicted_key, _) in _DIMENSIONS.items())
    unknown = unknown or (result["policy_match"] is False and type(predicted_policy) is not bool)
    if unknown:
        errors.append("UNKNOWN")
    result["error_types"] = [kind for kind in ERROR_TYPES if kind in errors]
    result["correction"] = bool(errors)
    result["training_weight"] = 2 if result["correction"] else 1
    return result


def _effective(examples):
    # Persistence authenticates real reviews; these guards additionally prevent
    # explicitly marked synthetic/automation/superseded rows entering reports.
    rows = []
    for row in examples:
        if row.get("learning_status", "active") not in {"active", "corrected"}:
            continue
        provenance = row.get("provenance") or {}
        if provenance.get("actor_mode", "human") != "human":
            continue
        if provenance.get("origin", "real_candidate") != "real_candidate":
            continue
        rows.append(row)
    return rows


def _sort_key(row):
    value = row.get("timestamp") or row.get("created_at")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        stamp = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        stamp = float("-inf")
    identity = str(row.get("id", row.get("example_id", "")))
    return stamp, (0, int(identity)) if identity.isdigit() else (1, identity)


def _version(row):
    return str(row.get("model_version") or (row.get("shadow_prediction") or {}).get("shadow_model_version") or "unknown")


def _source_identity(row):
    features = row.get("input_features") or {}
    source = features.get("source") or {}
    # Reimporting one URL can create distinct internal source records.
    for value in (features.get("source_url"), source.get("source_url"), source.get("url"), features.get("source_id")):
        if value is not None and str(value).strip():
            return str(value)
    return None


def _window(rows):
    comparisons = [compare_prediction(row.get("shadow_prediction") or {}, row.get("human_ground_truth") or {})
                   for row in rows]
    report = {"sample_count": len(rows), "model_versions": sorted({_version(row) for row in rows})}
    for dimension, metric in (("primary", "primary_accuracy"), ("secondary", "secondary_accuracy"),
                              ("risk", "risk_agreement"), ("action", "action_agreement")):
        labels = [result[dimension + "_match"] for result in comparisons if result[dimension + "_match"] is not None]
        report[dimension + "_denominator"] = len(labels)
        report[dimension + "_matched"] = sum(labels)
        report[metric] = _ratio(sum(labels), len(labels))
    policy = Counter()
    for row in rows:
        human = (row.get("human_ground_truth") or {}).get("human_policy")
        if type(human) is not bool:
            continue
        predicted = (row.get("shadow_prediction") or {}).get("shadow_policy_prediction")
        policy["denominator"] += 1
        policy["actual_positive"] += human
        if type(predicted) is not bool:
            policy["abstentions"] += 1
            continue
        policy["predicted_positive"] += predicted
        policy["matched"] += predicted == human
        policy["true_positives"] += predicted and human
        policy["false_positives"] += predicted and not human
        policy["false_negatives"] += not predicted and human
        policy["true_negatives"] += not predicted and not human
    for key in ("denominator", "matched", "true_positives", "false_positives", "false_negatives", "true_negatives", "abstentions"):
        report["policy_" + key] = policy[key]
    report.update({
        "policy_precision": _ratio(policy["true_positives"], policy["predicted_positive"]),
        "policy_precision_denominator": policy["predicted_positive"],
        "policy_recall": _ratio(policy["true_positives"], policy["actual_positive"]),
        "policy_recall_denominator": policy["actual_positive"],
        "policy_agreement": _ratio(policy["matched"], policy["denominator"]),
        "field_denominator": sum(result["field_denominator"] for result in comparisons),
        "field_matched": sum(result["field_matched"] for result in comparisons),
        "correction_count": sum(result["correction"] for result in comparisons),
        "error_types": {kind: sum(kind in result["error_types"] for result in comparisons) for kind in ERROR_TYPES},
    })
    report["field_agreement"] = _ratio(report["field_matched"], report["field_denominator"])
    sources = Counter(identity for row in rows if (identity := _source_identity(row)) is not None)
    report.update({
        "identified_source_count": sum(sources.values()), "unique_source_count": len(sources),
        "repeated_source_count": sum(count - 1 for count in sources.values()),
        "source_repeat_groups": {identity: count for identity, count in sorted(sources.items()) if count > 1},
    })
    return report


def _windows(rows):
    ordered = sorted(rows, key=_sort_key)
    return {"all": _window(ordered), "recent_50": _window(ordered[-50:]), "recent_100": _window(ordered[-100:])}


def performance(examples: list[dict]) -> dict:
    """Report effective examples by time window and recorded prediction version."""
    rows = _effective(examples)
    versions = defaultdict(list)
    for row in rows:
        versions[_version(row)].append(row)
    return {
        "sample_count": len(rows), "windows": _windows(rows),
        "by_model_version": {version: {"sample_count": len(group), "windows": _windows(group)}
                             for version, group in sorted(versions.items())},
        "denominator_note": "Only explicit human labels enter each dimension; missing predictions remain abstentions. "
                            "Field agreement counts labeled fields. Repeated sources are not independent validation.",
    }


def replay_examples(examples, predictor=predict_shadow) -> dict:
    """Evaluate frozen inputs in memory, preserving originals and human answers.

    Injected predictors receive only allowlisted deep copies. A failure remains
    an abstention rather than selectively dropping a labeled difficult sample.
    """
    rows = _effective(examples)
    predictions, replayed = [], []
    failure_count = 0
    for row in sorted(rows, key=_sort_key):
        error = None
        try:
            prediction = predictor(prediction_features(row.get("input_features") or {}))
            if not isinstance(prediction, dict):
                raise ValueError("Predictor must return a prediction object")
            prediction = deepcopy(prediction)
        except Exception as exc:
            prediction, error = {}, f"{type(exc).__name__}: {exc}"
            failure_count += 1
        human = row.get("human_ground_truth") or {}
        predictions.append({
            "example_id": row.get("id", row.get("example_id")),
            "original_shadow_prediction": deepcopy(row.get("shadow_prediction") or {}),
            "replay_shadow_prediction": prediction,
            "comparison": compare_prediction(prediction, human), "error": error,
        })
        replayed.append({**deepcopy(row), "shadow_prediction": prediction,
                         "model_version": prediction.get("shadow_model_version") or "unknown"})
    return {
        "sample_count": len(rows), "failure_count": failure_count,
        "read_only": True, "model_updated": False, "independent_validation": False,
        "evaluation_mode": "historical_replay", "predictions": predictions,
        "baseline_performance": performance(rows), "replay_performance": performance(replayed),
    }
