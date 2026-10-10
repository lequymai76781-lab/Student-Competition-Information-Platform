"""Small synthetic fixtures below test arithmetic only, never performance claims."""
from copy import deepcopy
import json
import math
import sqlite3

import pytest


def metrics_module():
    from app.services import hierarchical_classification_metrics
    return hierarchical_classification_metrics


def row(identity, truth="participation", predicted="participation", confidence=.9, **values):
    return {"source_id": identity, "true_type": truth, "predicted_type": predicted,
            "confidence": confidence, "human_secondary_types": [], **values}


def test_fixed_seven_macro_denominator_and_complete_confusion_matrix():
    m = metrics_module()
    rows = [row("a"), row("b", "information", "participation"), row("c", "information", "information")]
    before = deepcopy(rows)
    result = m.classification_metrics(rows)
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["macro_precision"] == pytest.approx(1.5 / 7)
    assert result["macro_recall"] == pytest.approx(1.5 / 7)
    assert result["macro_f1"] == pytest.approx((4 / 3) / 7)
    assert result["weighted_f1"] == pytest.approx(2 / 3)
    assert result["per_class"]["information"]["support"] == 2
    assert len(result["confusion_matrix"]["matrix"]) == 7
    assert all(len(r) == 7 for r in result["confusion_matrix"]["matrix"])
    assert sum(map(sum, result["confusion_matrix"]["matrix"])) == 3
    assert result["wrong_pairs"] == [{"true_type": "information", "predicted_type": "participation", "count": 1, "source_ids": ["b"]}]
    assert rows == before


def test_abstentions_stay_in_support_and_accuracy_denominators():
    m = metrics_module()
    result = m.classification_metrics([row("a"), row("b", predicted=None), row("c", "policy", "unrecognized")])
    assert result["accuracy"] == pytest.approx(1 / 3)
    assert result["abstention_n"] == 2
    assert result["per_class"]["participation"]["recall"] == .5
    assert result["abstention_source_ids"] == ["b", "c"]
    assert sum(map(sum, result["confusion_matrix"]["matrix"])) + result["abstention_n"] == 3


def test_empty_ratios_are_json_safe_and_undefined_precision_not_perfect():
    m = metrics_module()
    result = m.classification_metrics([])
    assert result["accuracy"] is None
    assert result["weighted_f1"] is None
    assert result["macro_f1"] == 0
    assert all(c["precision"] == 0 for c in result["per_class"].values())
    curves = m.global_threshold_curves([])
    assert len(curves) == 6 and all(c["auto_accuracy"] is None for c in curves)
    assert m.policy_threshold_curves([])[0]["precision"] is None
    json.dumps([result, curves], allow_nan=False)


def test_thresholds_include_secondary_update_safety_without_replacing_primary_truth():
    m = metrics_module()
    rows = [row("a", "information", "information", .95, human_secondary_types=["rule_update"], informational_only=True),
            row("b", "policy", "information", .9),
            row("c", "participation", "policy", .85),
            row("d", "update", "participation", .8)]
    curve = m.global_threshold_curves(rows)[0]
    assert curve["auto_n"] == 4 and curve["auto_correct_n"] == 1
    assert curve["policy_false_positive_auto_n"] == 1
    assert curve["update_missed_auto_n"] == 2
    assert curve["update_human_primary_or_secondary_n"] == 2
    assert curve["information_misplacement_auto_source_ids"] == ["a", "b"]
    curve95 = m.global_threshold_curves(rows)[-1]
    assert curve95["auto_n"] == 1 and curve95["manual_n"] == 3
    assert curve95["update_missed_auto_n"] == 1
    assert m.classification_metrics(rows)["accuracy"] == .25


def test_invalid_confidence_does_not_become_hypothetical_auto():
    m = metrics_module()
    rows = [row("a", confidence=math.nan), row("b", confidence=1.1), row("c", confidence=True), row("d", predicted=None)]
    assert all(c["auto_n"] == 0 for c in m.global_threshold_curves(rows))


def test_policy_thresholds_use_separate_score_and_positive_evidence_gate():
    m = metrics_module()
    rows = [row("a", "policy", confidence=.2, policy_confidence=.95, is_policy=True),
            row("b", "information", confidence=.99, policy_confidence=.4, is_policy=False),
            row("c", "information", confidence=.1, policy_confidence=.85, is_policy=True),
            row("d", "policy", confidence=.99, policy_confidence=.99, is_policy=False)]
    curves = m.policy_threshold_curves(rows)
    assert [c["threshold"] for c in curves] == [.7, .75, .8, .85, .9, .95]
    assert curves[0]["true_positive"] == 1
    assert curves[0]["false_positive"] == 1
    assert curves[0]["false_negative"] == 1
    assert curves[0]["precision"] == .5
    assert curves[-1]["precision"] == 1 and curves[-1]["recall"] == .5
    assert curves[-1]["predicted_positive_source_ids"] == ["a"]
    assert curves[-1]["precision_wilson95"]["lower"] < 1
    assert curves[-1]["precision_wilson99"]["lower"] < curves[-1]["precision_wilson95"]["lower"]


def test_actual_routing_is_independent_of_hypothetical_confidence():
    m = metrics_module()
    rows = [row("a", confidence=.99, classification_status="NEEDS_QUICK_CONFIRM"),
            row("b", "update", "update", .99, classification_status="NEEDS_MANUAL_CLASSIFICATION"),
            row("c", "information", "information", .99, classification_status="AUTO_CLASSIFIED", informational_only=True)]
    result = m.routing_metrics(rows)
    assert result["auto_n"] == 1 and result["quick_confirm_n"] == 1 and result["manual_n"] == 1
    assert result["auto_by_primary_type"]["update"] == 0
    assert result["informational_only_n"] == 1
    assert result["informational_factual_safety_unanswered_n"] == 1
    assert result["informational_safety_certified"] is False
    assert m.global_threshold_curves(rows)[0]["auto_n"] == 3


def test_paired_bootstrap_reproducible_and_pair_order_does_not_matter():
    m = metrics_module()
    before = [row("a"), row("b", "result", "participation"), row("c", "policy", "information")]
    after = [row("c", "policy", "policy"), row("b", "result", "result"), row("a")]
    result = m.paired_bootstrap(before, after, iterations=200, seed=42)
    assert result == m.paired_bootstrap(before, list(reversed(after)), iterations=200, seed=42)
    assert result["paired_n"] == 3
    assert result["accuracy_delta"]["estimate"] == pytest.approx(2 / 3)
    assert result["accuracy_delta"]["lower"] >= 0
    assert result["independent_validation"] is False
    identical = m.paired_bootstrap(before, before, iterations=100, seed=4)
    assert identical["accuracy_delta"]["lower"] == identical["accuracy_delta"]["upper"] == 0


def test_paired_bootstrap_rejects_different_samples_or_truth():
    m = metrics_module()
    with pytest.raises(ValueError, match="same source"):
        m.paired_bootstrap([row("a")], [row("b")])
    with pytest.raises(ValueError, match="ground truth"):
        m.paired_bootstrap([row("a")], [row("a", "policy")])
    with pytest.raises(ValueError, match="Duplicate"):
        m.classification_metrics([row("a"), row("a")])


def test_readonly_connection_cannot_change_input_database(tmp_path):
    from scripts.evaluate_hierarchical_classification import open_readonly_database
    path = tmp_path / "fixture-only.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE fixture (value INTEGER)")
        db.execute("INSERT INTO fixture VALUES (1)")
    before = path.read_bytes()
    with open_readonly_database(path) as db:
        assert db.execute("SELECT value FROM fixture").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("UPDATE fixture SET value=2")
    assert path.read_bytes() == before


def test_original_fine_truth_and_secondary_labels_are_preserved_during_mapping():
    m = metrics_module()
    annotations = [{"source_id": "a", "human_primary_type": "completion_news", "human_secondary_types": ["rule_update"], "informational_safe": None, "annotated_by": "unit-fixture", "label_provenance": "human"}]
    before = deepcopy(annotations)
    rows = m.build_evaluation_records(annotations, {"a": {"predicted_type": "information", "confidence": .99}}, {"completion_news": "information"})
    assert rows[0]["true_type"] == "information"
    assert rows[0]["human_primary_type"] == "completion_news"
    assert rows[0]["human_secondary_types"] == ["rule_update"]
    assert rows[0]["human_annotation"] == before[0]
    assert annotations == before
    assert m.global_threshold_curves(rows)[0]["information_misplacement_auto_n"] == 1


def test_mapping_rejects_unknown_human_truth_but_keeps_missing_predictions():
    m = metrics_module()
    annotations = [{"source_id": "a", "human_primary_type": "completion_news", "human_secondary_types": []}]
    with pytest.raises(ValueError, match="human label"):
        m.build_evaluation_records(annotations, {}, {"result_notice": "result"})
    result = m.build_evaluation_records(annotations, {}, {"completion_news": "information"})
    assert len(result) == 1 and result[0]["predicted_type"] is None
    assert m.classification_metrics(result)["accuracy"] == 0


def test_policy_paired_error_test_uses_nonpolicy_discordant_pairs_and_excludes_coarsening():
    m = metrics_module()
    baseline = [row(str(i), "information", "policy") for i in range(3)] + [row("p", "policy", "policy")]
    current = [row(str(i), "information", "information") for i in range(3)] + [row("p", "policy", "information")]
    result = m.paired_policy_error_test(baseline, current)
    assert result["human_nonpolicy_n"] == 3
    assert result["old_false_positive_n"] == 3 and result["new_false_positive_n"] == 0
    assert result["improved_pairs"] == 3 and result["regressed_pairs"] == 0
    assert result["exact_two_sided_p"] == .25
    assert result["significant_at_05"] is False
    assert m.paired_policy_error_test(current, current)["exact_two_sided_p"] == 1


def test_update_semantic_miss_and_unsafe_routing_are_reported_separately():
    m = metrics_module()
    rows = [row("a", "update", "repost", .95, risk_level="HIGH_RISK"),
            row("b", "information", "information", .95, human_secondary_types=["correction_notice"], risk_level="LOW_RISK")]
    result = m.global_threshold_curves(rows)[0]
    assert result["update_missed_auto_n"] == 2
    assert result["update_without_high_risk_auto_n"] == 1
    assert result["update_without_high_risk_auto_source_ids"] == ["b"]
