"""Fixture-only tests: no live annotation store or production database writes."""

from copy import deepcopy
import json

import pytest

from app.services.golden_set_metrics import evaluate_golden_set
from app.services.source_document_classifier import DOCUMENT_TYPES


def item(source_id, predicted="registration_notice", confidence=0.9, **values):
    return {
        "source_id": source_id,
        "predicted_type": predicted,
        "predicted_confidence": confidence,
        "matched_rules": [],
        **values,
    }


def label(source_id, primary="registration_notice", **values):
    return {
        "source_id": source_id,
        "status": "annotated",
        "human_primary_type": primary,
        "human_secondary_types": [],
        "annotated_by": "fixture-admin",
        "annotated_at": "2026-10-01T10:00:00+08:00",
        "label_provenance": "human",
        "prediction_exposed": False,
        **values,
    }


POLICY_CHECKS = (
    "is_policy", "extraction_correct", "recognition_type_correct", "match_correct",
    "no_track_ambiguity", "validity_clear",
)
RELATION_CHECKS = (
    "school_correct", "competition_correct", "source_valid",
    "recognition_type_correct", "match_correct",
)


def audit(audit_id, kind="policy", **values):
    checks = POLICY_CHECKS if kind == "policy" else RELATION_CHECKS
    return {
        "audit_id": audit_id,
        "status": "annotated",
        "annotated_by": "fixture-admin",
        "annotated_at": "2026-10-01T02:00:00Z",
        "label_provenance": "human",
        "answers": dict.fromkeys(checks, "yes"),
        **values,
    }


def test_empty_human_set_reports_unavailable_accuracy_and_blocked_calibration():
    result = evaluate_golden_set([item("a")], [])
    assert result["total"] == 1
    assert result["human_n"] == 0
    assert result["accuracy"] is None
    assert result["blind_human"]["accuracy"] is None
    assert result["per_class"]["registration_notice"]["f1"] is None
    assert result["status"] == "BLOCKED"
    assert result["readiness"]["ready"] is False
    assert result["recommendation"] is None
    assert result["calibration_validated"] is False
    assert result["thresholds_applied"] is False
    assert all(row["auto_accuracy"] is None for row in result["threshold_curves"])
    assert json.loads(json.dumps(result, allow_nan=False))["accuracy"] is None


@pytest.mark.parametrize("invalid", [
    {"status": "draft"}, {"status": "skipped"}, {"skipped": True},
    {"label_provenance": "test_fixture"}, {"label_provenance": None},
    {"annotated_by": "  "}, {"annotated_by": None}, {"annotated_by": False},
    {"annotated_at": "not-a-date"}, {"annotated_at": "2026-10-01"},
    {"annotated_at": "2026-02-30T10:00:00Z"},
    {"human_primary_type": "invalid"}, {"human_primary_type": None},
    {"source_id": "outside-manifest"},
])
def test_invalid_or_nonhuman_records_never_count(invalid):
    result = evaluate_golden_set([item("a")], [{**label("a"), **invalid}])
    assert result["human_n"] == 0
    assert result["accuracy"] is None
    assert result["excluded_annotation_n"] == 1


def test_primary_confusion_precision_recall_f1_use_independent_denominators():
    items = [item("a"), item("b"), item("c", "completion_news")]
    annotations = [label("a"), label("b", "completion_news"), label("c", "completion_news")]
    result = evaluate_golden_set(items, annotations)
    assert result["human_n"] == 3
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert result["confusion_matrix"] == {
        "registration_notice": {"registration_notice": 1},
        "completion_news": {"registration_notice": 1, "completion_news": 1},
    }
    registration = result["per_class"]["registration_notice"]
    completion = result["per_class"]["completion_news"]
    assert (registration["support"], registration["predicted_n"]) == (1, 2)
    assert (registration["precision"], registration["recall"]) == (0.5, 1)
    assert registration["f1"] == pytest.approx(2 / 3)
    assert (completion["precision"], completion["recall"]) == (1, 0.5)
    assert completion["f1"] == pytest.approx(2 / 3)
    assert result["per_class"]["other"]["precision"] is None
    assert result["per_class"]["other"]["recall"] is None


def test_duplicates_never_inflate_sample_size_and_conflicting_labels_are_excluded():
    result = evaluate_golden_set(
        [item("a"), item("a"), item("b")],
        [label("a"), label("a"), label("b"), label("b", "event_news")],
    )
    assert result["total"] == 2
    assert result["human_n"] == 1
    assert result["conflicting_source_ids"] == ["b"]
    assert result["duplicate_annotation_n"] == 1
    with pytest.raises(ValueError, match="Conflicting.*source"):
        evaluate_golden_set([item("a"), item("a", "other")], [])


def test_saved_exposure_is_monotonic_but_later_reveal_does_not_rewrite_blind_label_history():
    result = evaluate_golden_set(
        [item("a"), item("b", prediction_exposed=True), item("c"), item("d")],
        [label("a"), label("a", prediction_exposed=True), label("b"),
         label("c", prediction_exposed=None), label("d")],
    )
    assert result["human_n"] == 4
    assert result["blind_human_n"] == 2
    assert result["exposed_human_n"] == 1
    assert result["unknown_exposure_human_n"] == 1
    assert result["blind_human"]["human_n"] == 2
    assert result["all_human"]["human_n"] == 4


def test_dangerous_errors_disclose_four_overlapping_definitions():
    pairs = [
        ("registration_notice", "postgraduate_policy_document"),
        ("organization_notice", "award_policy_document"),
        ("completion_news", "comprehensive_evaluation_policy_document"),
        ("event_news", "policy_recognition_document"),
        ("result_notice", "comprehensive_evaluation_policy_document"),
        ("registration_notice", "registration_notice"),
    ]
    result = evaluate_golden_set(
        [item(str(i), predicted) for i, (_, predicted) in enumerate(pairs)],
        [label(str(i), primary) for i, (primary, _) in enumerate(pairs)],
    )
    dangerous = result["dangerous_errors"]
    assert dangerous["notice_to_policy"]["count"] == 3
    assert dangerous["notice_to_policy"]["denominator"] == 4
    assert dangerous["news_to_policy"]["count"] == 2
    assert dangerous["registration_to_postgraduate"]["count"] == 1
    assert dangerous["registration_to_postgraduate"]["rate"] == 0.5
    assert dangerous["result_or_news_to_comprehensive"]["count"] == 2
    assert dangerous["result_or_news_to_comprehensive"]["denominator"] == 3
    assert all(row["definition"] for row in dangerous.values())


def test_threshold_simulation_uses_only_labeled_truth_and_separates_dataset_coverage():
    items = [item("a", confidence=0.7), item("b", "award_policy_document", 0.95),
             item("c", confidence=0.96), item("d", confidence=None),
             item("e", confidence=float("nan")), item("f", confidence=True)]
    annotations = [label("a"), label("b"), label("d")]
    result = evaluate_golden_set(items, annotations)
    curves = result["threshold_curves"]
    assert [row["threshold"] for row in curves] == [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    assert (curves[0]["labeled_n"], curves[0]["auto_n"], curves[0]["review_n"]) == (3, 2, 1)
    assert (curves[0]["wrong_auto_n"], curves[0]["policy_wrong_auto_n"]) == (1, 1)
    assert curves[0]["auto_accuracy"] == 0.5
    assert (curves[-1]["auto_n"], curves[-1]["review_n"], curves[-1]["auto_accuracy"]) == (1, 2, 0)
    assert (curves[0]["dataset_auto_n"], curves[0]["dataset_review_n"]) == (3, 3)
    assert result["recommendation"] is None


def test_per_class_threshold_curves_group_predicted_classes_and_blind_curves_exclude_exposed_labels():
    items = [item("a", confidence=0.7), item("b", "award_policy_document", 0.95),
             item("c", "award_policy_document", 0.8), item("d", confidence=0.9),
             item("unlabeled", "award_policy_document", 0.99)]
    annotations = [label("a"), label("b"), label("c", "award_policy_document"),
                   label("d", "event_news", prediction_exposed=True)]
    result = evaluate_golden_set(items, annotations)
    awards = result["per_class_threshold_curves"]["award_policy_document"]
    assert (awards[0]["actual_support"], awards[0]["predicted_labeled_n"]) == (1, 2)
    assert (awards[0]["auto_n"], awards[0]["wrong_auto_n"], awards[0]["dataset_auto_n"]) == (2, 1, 3)
    assert (awards[4]["auto_n"], awards[4]["wrong_auto_n"]) == (1, 1)
    assert result["per_class_threshold_curves"]["other"][0]["auto_accuracy"] is None
    assert result["threshold_curves"][4]["labeled_n"] == 4
    assert (result["threshold_curves"][4]["auto_n"], result["threshold_curves"][4]["wrong_auto_n"]) == (2, 2)
    assert result["blind_threshold_curves"][4]["labeled_n"] == 3
    assert (result["blind_threshold_curves"][4]["auto_n"], result["blind_threshold_curves"][4]["wrong_auto_n"]) == (1, 1)


def test_unrecognized_frozen_prediction_is_unscorable_and_never_automatic():
    result = evaluate_golden_set([item("a", "bad-type", 0.99)], [label("a")])
    assert result["human_n"] == 1
    assert result["all_human"]["scored_n"] == 0
    assert result["accuracy"] is None
    assert result["unscorable_source_ids"] == ["a"]
    assert all(row["auto_n"] == 0 for row in result["threshold_curves"])
    assert result["readiness"]["ready"] is False


def test_informational_type_correctness_does_not_imply_fact_or_deadline_safety():
    items = [item("a", "completion_news", classification_status="informational_only"),
             item("b", "event_news", classification_status="informational_only"),
             item("c", "competition_intro", classification_status="informational_only")]
    labels = [label("a", "completion_news"),
              label("b", "event_news", informational_safe="no"),
              label("c", "deadline_extension", informational_safe="unsure")]
    info = evaluate_golden_set(items, labels)["informational"]
    assert info["routed_n"] == 3
    assert info["type_accuracy"] == pytest.approx(2 / 3)
    assert info["high_risk_misroute_n"] == 1
    assert (info["safety_reviewed_n"], info["unsafe_n"], info["unsure_n"]) == (2, 1, 1)
    assert info["safety_accuracy"] is None
    assert info["safety_certified"] is False
    assert info["limitation"]


def test_policy_and_relation_audits_require_complete_real_human_answers():
    policy_no = audit("p2")
    policy_no["answers"]["validity_clear"] = "no"
    policy_unsure = audit("p3")
    policy_unsure["answers"]["is_policy"] = "unsure"
    policy_missing = audit("p4")
    del policy_missing["answers"]["is_policy"]
    relation_no = audit("r1", "relation")
    relation_no["answers"]["school_correct"] = "no"
    result = evaluate_golden_set([], [], [audit("p1"), policy_no, policy_unsure, policy_missing,
                                          audit("p5", label_provenance="test_fixture")], [relation_no])
    assert result["policy_audit"]["complete_n"] == 3
    assert result["policy_audit"]["accepted_n"] == 1
    assert result["policy_audit"]["rejected_n"] == 1
    assert result["policy_audit"]["unsure_n"] == 1
    assert result["policy_audit"]["incomplete_or_invalid_n"] == 2
    assert result["relation_audit"]["obvious_error_n"] == 1
    assert result["relation_audit"]["recommended_action"] == "SUSPEND_AUTO_CONFIRMATION_AND_USE_NEEDS_QUICK_CONFIRM"
    assert result["thresholds_applied"] is False


def test_audit_duplicates_and_conflicts_do_not_inflate_readiness():
    first = audit("p")
    conflicted = audit("q")
    conflict = deepcopy(conflicted)
    conflict["answers"]["is_policy"] = "no"
    result = evaluate_golden_set([], [], [first, deepcopy(first), conflicted, conflict], [])
    assert result["policy_audit"]["complete_n"] == 1
    assert result["policy_audit"]["conflicting_audit_ids"] == ["q"]
    assert result["policy_audit"]["duplicate_n"] == 1


def test_observed_relation_error_requires_attention_even_in_partial_or_conflicting_audit():
    partial = audit("partial", "relation")
    partial["answers"] = {"school_correct": "no"}
    no = audit("conflict", "relation")
    no["answers"]["competition_correct"] = "no"
    result = evaluate_golden_set([], [], [], [partial, no, audit("conflict", "relation")])
    assert result["relation_audit"]["complete_n"] == 0
    assert result["relation_audit"]["obvious_error_n"] == 2
    assert result["relation_audit"]["recommended_action"] == "SUSPEND_AUTO_CONFIRMATION_AND_USE_NEEDS_QUICK_CONFIRM"


def test_informational_secondary_risk_is_not_hidden_by_correct_primary_type():
    result = evaluate_golden_set(
        [item("a", "completion_news", classification_status="INFORMATIONAL_ONLY", risk_level="HIGH_RISK")],
        [label("a", "completion_news", human_secondary_types=["rule_update"])],
    )
    assert result["informational"]["type_accuracy"] == 1
    assert result["informational"]["high_risk_misroute_n"] == 1
    assert result["informational"]["safety_accuracy"] is None


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("inf"), float("nan"), "0.99", True, None])
def test_invalid_confidence_never_increases_simulated_automatic_coverage(confidence):
    result = evaluate_golden_set([item("a", confidence=confidence)], [label("a")])
    assert result["accuracy"] == 1
    assert all(row["auto_n"] == 0 and row["review_n"] == 1 for row in result["threshold_curves"])
    json.dumps(result, allow_nan=False)


def complete_fixture():
    items = [item(str(i), DOCUMENT_TYPES[i % 20], 0.95) for i in range(100)]
    labels = [label(str(i), DOCUMENT_TYPES[i % 20]) for i in range(100)]
    policies = [audit(f"p{i}") for i in range(20)]
    relations = [audit(f"r{i}", "relation") for i in range(20)]
    return items, labels, policies, relations


def test_readiness_requires_100_distinct_humans_and_20_each_accepted_audits():
    items, labels, policies, relations = complete_fixture()
    ready = evaluate_golden_set(items, labels, policies, relations)
    assert ready["readiness"]["ready"] is True
    assert ready["status"] == "EXPLORATORY"
    assert ready["calibration_validated"] is False
    assert ready["recommendation"]["status"] == "EXPLORATORY_ONLY"
    assert ready["recommendation"]["requires_independent_validation"] is True
    for partial in [(items, labels[:-1], policies, relations),
                    (items, labels, policies[:-1], relations),
                    (items, labels, policies, relations[:-1])]:
        result = evaluate_golden_set(*partial)
        assert result["readiness"]["ready"] is False
        assert result["recommendation"] is None
    relations[-1]["answers"]["source_valid"] = "unsure"
    result = evaluate_golden_set(items, labels, policies, relations)
    assert result["readiness"]["ready"] is False
    assert result["recommendation"] is None


def test_missing_class_support_blocks_recommendation_even_with_100_labels():
    items, labels, policies, relations = complete_fixture()
    for entry in items:
        entry["predicted_type"] = "registration_notice"
    for annotation in labels:
        annotation["human_primary_type"] = "registration_notice"
    result = evaluate_golden_set(items, labels, policies, relations)
    assert result["human_n"] == 100
    assert result["recommendation"] is None
    assert "postgraduate_policy_document" in result["readiness"]["missing_classes"]


@pytest.mark.parametrize("safety", [None, "unsure", "no"])
def test_unresolved_informational_safety_blocks_recommendation_even_with_complete_audits(safety):
    items, labels, policies, relations = complete_fixture()
    items[6]["classification_status"] = "INFORMATIONAL_ONLY"
    labels[6]["informational_safe"] = safety
    result = evaluate_golden_set(items, labels, policies, relations)
    assert result["informational"]["type_accuracy"] == 1
    assert result["readiness"]["ready"] is False
    assert any("Informational" in blocker for blocker in result["readiness"]["blockers"])
    assert result["recommendation"] is None


def test_informational_safety_yes_does_not_override_human_high_risk_secondary_label():
    items, labels, policies, relations = complete_fixture()
    items[6]["classification_status"] = "INFORMATIONAL_ONLY"
    labels[6]["informational_safe"] = "yes"
    assert evaluate_golden_set(items, labels, policies, relations)["readiness"]["ready"] is True
    labels[6]["human_secondary_types"] = ["rule_update"]
    result = evaluate_golden_set(items, labels, policies, relations)
    assert result["readiness"]["ready"] is False
    assert result["recommendation"] is None


def test_pure_evaluation_preserves_inputs_and_supports_nested_audit_annotations():
    inputs = ([item("a")], [label("a")], [{"audit_id": "p", "annotation": audit("p")}], [])
    before = deepcopy(inputs)
    result = evaluate_golden_set(*inputs)
    assert inputs == before
    assert result["policy_audit"]["accepted_n"] == 1
