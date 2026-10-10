"""Synthetic fixtures only: no Golden Set annotation or database writes."""

from copy import deepcopy
import json

import pytest

from app.services.golden_calibration_analysis import analyze_calibration
from app.services.source_document_classifier import DOCUMENT_TYPES


def fixture(source_id, actual="registration_notice", predicted=None, confidence=0.9, **changes):
    predicted = predicted or actual
    item = {"source_id": source_id, "predicted_type": predicted,
            "predicted_confidence": confidence, "informational_only": False}
    annotation = {
        "source_id": source_id, "human_primary_type": actual,
        "human_secondary_types": [], "status": "annotated", "skipped": False,
        "label_provenance": "human", "annotated_by": "fixture-reviewer",
        "annotated_at": "2026-10-01T12:00:00+08:00", "prediction_exposed": False,
        "predicted_type": predicted, "predicted_confidence": confidence,
        "informational_safe": None,
        **changes,
    }
    return item, annotation


def analyze(*pairs):
    return analyze_calibration([pair[0] for pair in pairs], [pair[1] for pair in pairs])


def test_macro_weighted_and_complete_matrix_preserve_human_primary_labels():
    pairs = [fixture("a"), fixture("b", "completion_news", "registration_notice"),
             fixture("c", "completion_news", note="A note must never replace this primary label.")]
    before = deepcopy(pairs)
    result = analyze(*pairs)
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["macro_average_all20"] == {
        "class_n": 20, "zero_division": 0, "precision": 1.5 / 20,
        "recall": 1.5 / 20, "f1": pytest.approx((4 / 3) / 20),
    }
    assert result["macro_average_supported"]["class_n"] == 2
    assert result["macro_average_supported"]["f1"] == pytest.approx(2 / 3)
    assert result["weighted_f1"] == pytest.approx(2 / 3)
    matrix = result["full_confusion_matrix"]
    assert matrix["row_axis"] == "human_primary_type"
    assert matrix["column_axis"] == "predicted_type"
    assert matrix["class_order"] == list(DOCUMENT_TYPES)
    assert len(matrix["matrix"]) == 20
    assert all(len(row) == 20 for row in matrix["matrix"])
    assert matrix["matrix"][DOCUMENT_TYPES.index("completion_news")][0] == 1
    assert sum(map(sum, matrix["matrix"])) == 3
    assert result["misclassification_pairs"] == [{
        "human_primary_type": "completion_news", "predicted_type": "registration_notice",
        "count": 1, "source_ids": ["b"],
    }]
    assert pairs == before
    assert result["thresholds_applied"] is False
    assert result["calibration_validated"] is False


def test_strict_100_integrity_requires_unique_complete_human_records_and_frozen_match():
    result = analyze(*(fixture(str(i)) for i in range(100)))
    assert result["integrity"]["complete_100_human"] is True
    assert result["integrity"]["frozen_prediction_match"] is True
    assert result["integrity"]["issues"] == []
    changed = fixture("x")
    changed[0]["predicted_type"] = "other"
    replay = analyze(changed)
    assert replay["human_n"] == 1
    assert replay["accuracy"] == 0
    assert replay["integrity"]["prediction_mismatch_source_ids"] == ["x"]
    assert replay["integrity"]["frozen_prediction_match"] is False
    with pytest.raises(ValueError, match="Duplicate frozen source_id"):
        analyze_calibration([changed[0], changed[0]], [changed[1]])
    with pytest.raises(ValueError, match="Duplicate annotation source_id"):
        analyze_calibration([changed[0]], [changed[1], changed[1]])


@pytest.mark.parametrize("changes", [
    {"label_provenance": "machine"}, {"status": "draft"}, {"skipped": True},
    {"annotated_by": ""}, {"annotated_at": "not-a-date"},
    {"human_primary_type": "invalid"}, {"human_secondary_types": ["invalid"]},
])
def test_invalid_human_rows_are_identified_and_excluded(changes):
    result = analyze(fixture("invalid", **changes))
    assert result["human_n"] == 0
    assert result["integrity"]["invalid_annotation_source_ids"] == ["invalid"]
    assert result["integrity"]["missing_human_source_ids"] == ["invalid"]
    assert result["integrity"]["complete_100_human"] is False


def test_five_danger_groups_use_human_denominators_and_report_proxy_limits():
    pairs = [
        fixture("a", "registration_notice", "policy_recognition_document"),
        fixture("b", "organization_notice", "postgraduate_policy_document"),
        fixture("c", "completion_news", "award_policy_document"),
        fixture("d", "event_news", "comprehensive_evaluation_policy_document"),
        fixture("e", "publicity_notice", "innovation_credit_policy_document"),
        fixture("f", "selection_notice"), fixture("g", "registration_notice"),
        fixture("h", "result_notice"),
        fixture("i", "award_policy_document", "postgraduate_policy_document"),
        fixture("j", "completion_news", "unknown_type"),
    ]
    result = analyze(*pairs)
    groups = result["calibration_dangerous_errors"]
    assert len(groups) == 5
    assert groups["registration_to_recognition"]["count"] == 1
    assert groups["registration_to_recognition"]["denominator"] == 2
    assert groups["ordinary_notice_to_postgraduate"]["denominator"] == 6
    assert groups["award_result_news_to_award_policy"]["denominator"] == 4
    assert groups["ordinary_news_to_comprehensive"]["denominator"] == 3
    assert groups["publicity_selection_to_policy"]["denominator"] == 2
    assert groups["award_result_news_to_award_policy"]["proxy_limitation"]
    assert groups["publicity_selection_to_policy"]["proxy_limitation"]
    assert groups["award_result_news_to_award_policy"]["unscorable_n"] == 1
    assert result["policy_false_positive"]["count"] == 5
    assert result["policy_false_positive"]["denominator"] == 9
    assert result["policy_wrong_class"]["count"] == 6
    assert result["policy_subtype_confusion"]["count"] == 1


def test_thresholds_report_distinct_policy_and_informational_risks_and_small_sample_interval():
    pairs = [
        fixture("a", confidence=0.7),
        fixture("b", "registration_notice", "award_policy_document", 0.95),
        fixture("c", "award_policy_document", "postgraduate_policy_document", 0.9),
        fixture("d", "other", "competition_intro", 0.94),
        fixture("e", "completion_news", confidence=0.96, human_secondary_types=["rule_update"]),
    ]
    result = analyze(*pairs)
    curves = result["threshold_curves"]
    assert [row["threshold"] for row in curves] == [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    assert curves[0]["auto_n"] == 5
    assert curves[0]["auto_accuracy"] == 0.4
    assert curves[0]["policy_wrong_auto_n"] == 2
    assert curves[0]["policy_false_positive_auto_n"] == 1
    assert curves[0]["policy_subtype_confusion_auto_n"] == 1
    assert curves[0]["informational_wrong_placement_auto_n"] == 2
    assert curves[4]["auto_n"] == 4
    assert curves[5]["auto_n"] == 2
    assert curves[5]["review_n"] == 3
    assert curves[5]["informational_wrong_placement_auto_source_ids"] == ["e"]
    interval = curves[5]["auto_accuracy_wilson95"]
    assert 0 < interval["lower"] < 0.5 < interval["upper"] < 1
    assert interval["n"] == 2
    assert curves[5]["small_sample"] is True
    assert result["informational"]["predicted_informational_n"] == 2
    assert result["informational"]["wrong_placement_n"] == 2
    assert result["informational"]["factual_safety_missing_n"] == 2
    assert result["informational"]["factual_safety_status"] == "UNANSWERED"
    assert result["informational"]["safety_certified"] is False


def test_no_observed_type_risk_does_not_answer_factual_safety_and_empty_metrics_are_finite():
    result = analyze(fixture("a", "completion_news"))
    assert result["informational"]["wrong_placement_n"] == 0
    assert result["informational"]["observed_placement_risk_status"] == "NO_OBSERVED_PLACEMENT_ERROR"
    assert result["informational"]["factual_safety_status"] == "UNANSWERED"
    empty = analyze_calibration([], [])
    assert empty["macro_average_all20"]["f1"] == 0
    assert empty["macro_average_supported"]["class_n"] == 0
    assert empty["weighted_f1"] is None
    assert empty["threshold_curves"][0]["auto_accuracy_wilson95"] is None
    assert json.loads(json.dumps(empty, allow_nan=False))["accuracy"] is None


def test_missing_prediction_snapshots_and_invalid_confidence_are_explicit():
    pair = fixture("a")
    del pair[1]["predicted_confidence"]
    pair[0]["predicted_confidence"] = float("nan")
    result = analyze(pair)
    assert result["integrity"]["missing_prediction_snapshot_source_ids"] == ["a"]
    assert result["integrity"]["invalid_confidence_source_ids"] == ["a"]
    assert result["integrity"]["frozen_prediction_match"] is False
    assert all(row["auto_n"] == 0 for row in result["threshold_curves"])


def test_malformed_prediction_type_is_reported_without_crashing_or_claiming_accuracy():
    pair = fixture("a", "completion_news")
    pair[0]["predicted_type"] = ["completion_news"]
    result = analyze(pair)
    assert result["integrity"]["invalid_prediction_source_ids"] == ["a"]
    assert result["human_n"] == 1
    assert result["accuracy"] is None
    assert result["class_support"]["completion_news"] == 1
    assert result["calibration_dangerous_errors"]["ordinary_news_to_comprehensive"]["denominator"] == 1


def test_dangerous_threshold_union_does_not_double_count_overlapping_groups():
    result = analyze(fixture("a", "publicity_notice", "postgraduate_policy_document"))
    curve = result["threshold_curves"][0]
    assert curve["calibration_dangerous_errors"]["ordinary_notice_to_postgraduate"]["count"] == 1
    assert curve["calibration_dangerous_errors"]["publicity_selection_to_policy"]["count"] == 1
    assert curve["dangerous_error_auto_n"] == 1
    assert curve["dangerous_error_auto_source_ids"] == ["a"]


@pytest.mark.parametrize("answer,expected", [
    ("yes", "REVIEWED_NO_OBSERVED_UNSAFE"), ("no", "OBSERVED_UNSAFE"), ("unsure", "UNANSWERED"),
])
def test_explicit_factual_answers_are_reported_without_safety_certification(answer, expected):
    result = analyze(fixture("a", "competition_intro", informational_safe=answer))
    assert result["informational"]["factual_safety_status"] == expected
    assert result["informational"]["factual_safety_answers"][answer] == 1
    assert result["informational"]["safety_certified"] is False
