"""Synthetic fixtures test arithmetic/isolation only, never count as human reviews."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re

import pytest


def predictor_module():
    from app.services import review_shadow_predictor
    return review_shadow_predictor


def metrics_module():
    from app.services import review_learning_metrics
    return review_learning_metrics


def example(identity, *, truth="participation", prediction="participation", version="v1", **extra):
    return {
        "id": str(identity),
        "created_at": (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=identity)).isoformat(),
        "learning_status": "active",
        "input_features": {"source": {"title": "竞赛报名通知", "source_url": f"https://example.test/{identity}"}},
        "shadow_prediction": {"shadow_primary_type": prediction, "shadow_model_version": version},
        "human_ground_truth": {"human_primary_type": truth},
        **extra,
    }


def test_shadow_reuses_source_rules_without_historical_human_label_leakage():
    module = predictor_module()
    features = {"source": {"title": "竞赛报名通知", "content_text": "请学生在指定时间报名参加比赛。"},
                "proposals": [{"field_name": "registration_deadline", "candidate_value": "2026-11-01"}]}
    poisoned = deepcopy(features)
    poisoned.update({"classification": {"primary_type": "policy"},
                     "human_ground_truth": {"human_primary_type": "policy"},
                     "decisions": {"registration_deadline": "approve"},
                     "verification": "verified", "human_note": "竞赛奖励管理办法 第一条"})
    poisoned["source"].update({"human_primary_type": "policy", "review_note": "竞赛奖励管理办法 第一条"})
    before = deepcopy(poisoned)
    baseline, result = module.predict_shadow(features), module.predict_shadow(poisoned)
    assert result["shadow_primary_type"] == "participation"
    assert result["shadow_policy_prediction"] is False
    assert result["shadow_suggested_action"] == "defer"
    assert result["shadow_field_decisions"] == {"registration_deadline": "defer"}
    assert {k: v for k, v in result.items() if k != "shadow_created_at"} == {
        k: v for k, v in baseline.items() if k != "shadow_created_at"}
    assert poisoned == before
    assert result["shadow_model_version"] == module.MODEL_VERSION
    assert re.search(r"sha256-[0-9a-f]{64}$", module.MODEL_VERSION)
    assert datetime.fromisoformat(result["shadow_created_at"]).tzinfo is not None


def test_shadow_policy_has_independent_evidence_and_never_approves_fields():
    prediction = predictor_module().predict_shadow({
        "source": {"title": "大学学科竞赛奖励管理办法", "publisher": "大学教务处",
                   "content_text": "第一条 本办法适用于学科竞赛奖励。第二条 遵照执行。"},
        "proposals": [{"field_name": "organizer"}, {"field_name": "organizer"}, {"id": 3}],
    })
    assert prediction["shadow_primary_type"] == "policy"
    assert prediction["shadow_policy_prediction"] is True
    assert prediction["shadow_suggested_action"] == "defer"
    assert prediction["shadow_field_decisions"] == {"organizer": "defer"}
    assert 0 <= prediction["shadow_confidence"] <= 1
    assert prediction["shadow_reason"]


def test_shadow_factual_conflicts_preserve_high_risk():
    result = predictor_module().predict_shadow({"source": {"title": "竞赛报名通知"},
                                               "flags": ["SOURCE_CONFLICT"], "proposals": []})
    assert result["shadow_risk_level"] == "HIGH_RISK"
    assert result["shadow_field_decisions"] == {}


def test_missing_human_dimensions_remain_null_and_do_not_infer_policy():
    result = metrics_module().compare_prediction(
        {"shadow_primary_type": "policy", "shadow_secondary_type": "policy_recognition",
         "shadow_policy_prediction": True, "shadow_risk_level": "NORMAL", "shadow_suggested_action": "defer"},
        {"human_primary_type": "policy", "human_field_decisions": {}})
    assert result["primary_match"] is True
    for key in ("secondary_match", "policy_match", "risk_match", "action_match", "field_match_rate"):
        assert result[key] is None
    assert result["field_denominator"] == 0
    assert result["correction"] is False
    assert result["training_weight"] == 1
    assert result["error_types"] == []


def test_missing_shadow_prediction_counts_as_abstention_against_human_label():
    result = metrics_module().compare_prediction({}, {
        "human_primary_type": "result", "human_policy": True,
        "human_field_decisions": {"deadline": "reject", "organizer": None}})
    assert result["primary_match"] is False
    assert result["policy_match"] is False
    assert result["field_match_rate"] == 0
    assert result["field_denominator"] == 1
    assert result["field_matches"] == {"deadline": False}
    assert result["correction"] is True
    assert result["training_weight"] == 2
    assert "POLICY_FALSE_NEGATIVE" not in result["error_types"]


@pytest.mark.parametrize(("shadow", "human", "error"), [
    ({"shadow_policy_prediction": True}, {"human_policy": False}, "POLICY_FALSE_POSITIVE"),
    ({"shadow_policy_prediction": False}, {"human_policy": True}, "POLICY_FALSE_NEGATIVE"),
    ({"shadow_primary_type": "participation"}, {"human_primary_type": "result"}, "SOURCE_TYPE_CONFUSION"),
    ({"shadow_secondary_type": "registration"}, {"human_secondary_type": "selection"}, "MULTI_LABEL_CONFUSION"),
    ({"shadow_risk_level": "LOW_RISK"}, {"human_risk_level": "HIGH_RISK"}, "UNKNOWN"),
])
def test_observed_errors_use_supported_categories(shadow, human, error):
    result = metrics_module().compare_prediction(shadow, human)
    assert result["error_types"] == [error]
    assert result["training_weight"] == 2


def test_notes_do_not_invent_title_edition_or_school_relation_causes():
    result = metrics_module().compare_prediction(
        {"shadow_primary_type": "participation", "shadow_suggested_action": "defer"},
        {"human_primary_type": "result", "human_action": "approve", "human_relation_decision": "reject",
         "human_note": "标题歧义、届次混淆和学校关系问题需要复核"})
    assert set(result["error_types"]) == {"SOURCE_TYPE_CONFUSION", "UNKNOWN"}
    assert result["relation_match"] is None


def test_field_agreement_uses_only_explicit_human_decisions_and_counts_missing_guesses():
    result = metrics_module().compare_prediction(
        {"shadow_field_decisions": {"deadline": "reject", "organizer": "approve", "unused": "approve"}},
        {"human_field_decisions": {"deadline": "reject", "organizer": "defer", "name": "approve", "empty": ""}})
    assert result["field_match_rate"] == pytest.approx(1 / 3)
    assert result["field_matched"] == 1
    assert result["field_denominator"] == 3
    assert result["field_matches"] == {"deadline": True, "organizer": False, "name": False}


def test_empty_performance_has_undefined_rates_and_explicit_zero_denominators():
    report = metrics_module().performance([])
    assert report["sample_count"] == 0
    assert report["by_model_version"] == {}
    for window in report["windows"].values():
        for rate in ("primary_accuracy", "secondary_accuracy", "policy_precision", "policy_recall",
                     "risk_agreement", "action_agreement", "field_agreement"):
            assert window[rate] is None
        assert window["policy_denominator"] == 0
        assert window["primary_denominator"] == 0
        assert window["field_denominator"] == 0
    json.dumps(report, allow_nan=False)


def test_policy_precision_recall_exclude_unknown_human_policy_and_report_abstentions():
    samples = []
    for identity, (predicted, actual) in enumerate([(True, True), (True, False), (False, True),
                                                  (False, False), (True, None), (None, True)]):
        samples.append(example(identity, shadow_prediction={"shadow_policy_prediction": predicted},
                               human_ground_truth={"human_policy": actual}))
    window = metrics_module().performance(samples)["windows"]["all"]
    assert window["policy_denominator"] == 5
    assert window["policy_precision"] == .5
    assert window["policy_precision_denominator"] == 2
    assert window["policy_recall"] == pytest.approx(1 / 3)
    assert window["policy_recall_denominator"] == 3
    assert window["policy_false_positives"] == 1
    assert window["policy_false_negatives"] == 1
    assert window["policy_abstentions"] == 1
    assert window["primary_denominator"] == 0


def test_no_positive_policy_support_does_not_look_perfect():
    sample = example(1, shadow_prediction={"shadow_policy_prediction": False},
                     human_ground_truth={"human_policy": False})
    window = metrics_module().performance([sample])["windows"]["all"]
    assert window["policy_precision"] is None
    assert window["policy_recall"] is None
    assert window["policy_agreement"] == 1


def test_missing_boolean_human_policy_does_not_accept_truthy_strings_or_numbers():
    for value in ("false", "true", 0, 1, "", None):
        result = metrics_module().compare_prediction({"shadow_policy_prediction": True}, {"human_policy": value})
        assert result["policy_match"] is None


def test_windows_sort_latest_effective_samples_and_group_model_versions():
    samples = [example(i, truth="result" if i < 50 else "participation", version="v1" if i < 60 else "v2")
               for i in range(120)]
    samples.extend([example(150, truth="result", learning_status="superseded"),
                    example(151, truth="result", learning_status="corrected")])
    before = deepcopy(samples)
    report = metrics_module().performance(list(reversed(samples)))
    assert report["sample_count"] == 121
    assert report["windows"]["all"]["primary_accuracy"] == pytest.approx(70 / 121)
    assert report["windows"]["recent_50"]["sample_count"] == 50
    assert report["windows"]["recent_50"]["primary_accuracy"] == pytest.approx(49 / 50)
    assert report["windows"]["recent_100"]["primary_accuracy"] == .7
    assert report["by_model_version"]["v1"]["sample_count"] == 61
    assert report["by_model_version"]["v2"]["windows"]["recent_50"]["primary_accuracy"] == 1
    assert samples == before


def test_metrics_use_field_micro_average_and_keep_each_human_dimension_denominator():
    samples = [example(0, shadow_prediction={"shadow_primary_type": "participation", "shadow_risk_level": "LOW_RISK",
                                           "shadow_suggested_action": "defer", "shadow_field_decisions": {"a": "defer"}},
                       human_ground_truth={"human_primary_type": "participation", "human_risk_level": "LOW_RISK",
                                           "human_action": "defer", "human_field_decisions": {"a": "defer"}}),
               example(1, shadow_prediction={"shadow_field_decisions": {"b": "defer"}},
                       human_ground_truth={"human_field_decisions": {"b": "approve", "c": "reject"}})]
    window = metrics_module().performance(samples)["windows"]["all"]
    assert window["field_agreement"] == pytest.approx(1 / 3)
    assert window["field_denominator"] == 3
    assert window["primary_denominator"] == window["risk_denominator"] == window["action_denominator"] == 1
    assert window["secondary_denominator"] == 0
    assert window["risk_agreement"] == window["action_agreement"] == 1
    assert window["correction_count"] == 1


def test_same_source_repetitions_are_disclosed_without_inventing_independent_sources():
    first, repeated, unknown = example(0), example(1), example(2, input_features={})
    first["input_features"]["source_id"] = 40
    repeated["input_features"]["source_id"] = 41
    repeated["input_features"]["source"]["source_url"] = first["input_features"]["source"]["source_url"]
    window = metrics_module().performance([first, repeated, unknown])["windows"]["all"]
    assert window["sample_count"] == 3
    assert window["identified_source_count"] == 2
    assert window["unique_source_count"] == 1
    assert window["repeated_source_count"] == 1


def test_replay_is_read_only_and_never_passes_human_answers_to_predictor():
    samples = [example(0, truth="result"), example(1, learning_status="superseded")]
    samples[0]["input_features"].update({"human_ground_truth": {"human_primary_type": "result"}, "decisions": {"x": "approve"}})
    samples[0]["input_features"]["source"]["review_note"] = "actual answer result"
    before = deepcopy(samples)

    def challenger(features):
        assert "human_ground_truth" not in features
        assert "decisions" not in features
        assert "review_note" not in features["source"]
        features["source"]["title"] = "local mutation"
        return {"shadow_primary_type": "result", "shadow_model_version": "challenger-test"}

    report = metrics_module().replay_examples(samples, predictor=challenger)
    assert samples == before
    assert report["sample_count"] == 1
    assert report["read_only"] is True
    assert report["model_updated"] is False
    assert report["independent_validation"] is False
    assert report["baseline_performance"]["windows"]["all"]["primary_accuracy"] == 0
    assert report["replay_performance"]["windows"]["all"]["primary_accuracy"] == 1
    assert report["predictions"][0]["comparison"]["primary_match"] is True
    assert report["predictions"][0]["original_shadow_prediction"] == before[0]["shadow_prediction"]
    assert report["predictions"][0]["replay_shadow_prediction"]["shadow_model_version"] == "challenger-test"


def test_replay_prediction_failure_keeps_labeled_denominator_and_does_not_change_examples():
    samples = [example(0)]
    before = deepcopy(samples)

    def unavailable(_features):
        raise RuntimeError("Prediction unavailable")

    report = metrics_module().replay_examples(samples, predictor=unavailable)
    assert report["failure_count"] == 1
    assert report["replay_performance"]["windows"]["all"]["primary_denominator"] == 1
    assert report["replay_performance"]["windows"]["all"]["primary_accuracy"] == 0
    assert samples == before


def test_replay_removes_nested_review_metadata_and_rejects_nontext_source_evidence():
    sample = example(0)
    sample["input_features"].update({
        "competition": {"name": "竞赛", "human_primary_type": "result", "classification": {"primary_type": "result"}},
        "proposals": [{"field_name": "organizer", "candidate_value": {"name": "教务处", "review_note": "人工答案"},
                       "source": {"title": {"human_note": "竞赛奖励管理办法 第一条"}}}],
    })
    sample["input_features"]["source"]["publisher"] = {"human_note": "人工答案"}

    def challenger(features):
        assert features["competition"] == {"name": "竞赛"}
        assert features["proposals"][0]["candidate_value"] == {"name": "教务处"}
        assert "title" not in features["proposals"][0]["source"]
        assert "publisher" not in features["source"]
        return {"shadow_primary_type": "participation"}

    report = metrics_module().replay_examples([sample], predictor=challenger)
    assert report["failure_count"] == 0
    assert report["replay_performance"]["windows"]["all"]["primary_accuracy"] == 1


def test_explicit_automation_synthetic_and_superseded_samples_never_enter_metrics_or_replay():
    samples = [example(0), example(1, provenance={"actor_mode": "automation", "origin": "real_candidate"}),
               example(2, provenance={"actor_mode": "human", "origin": "synthetic"}),
               example(3, learning_status="superseded")]
    assert metrics_module().performance(samples)["sample_count"] == 1
    report = metrics_module().replay_examples(samples)
    assert report["sample_count"] == 1
    assert report["replay_performance"]["sample_count"] == 1


def test_latest_windows_normalize_timezone_and_break_timestamp_ties_by_numeric_identity():
    samples = [example(i, created_at="2026-10-07T01:00:00+00:00") for i in range(51)]
    samples[0]["human_ground_truth"]["human_primary_type"] = "result"
    samples[0]["created_at"] = "2026-10-07T09:00:00+08:00"
    report = metrics_module().performance(list(reversed(samples)))
    assert report["windows"]["all"]["primary_accuracy"] == pytest.approx(50 / 51)
    assert report["windows"]["recent_50"]["primary_accuracy"] == 1
