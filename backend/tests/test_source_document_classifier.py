"""Behavioral tests for explainable classification of source documents."""

import pytest

from app.services.source_document_classifier import (
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPES,
    POLICY_TYPES,
    RECOGNITION_TYPES,
    classify_document,
)


@pytest.fixture(autouse=True)
def previously_authorized_routing_contract(monkeypatch):
    """Exercise legacy mechanisms under hypothetical authorization, not quality.

    Real default-deny calibration behavior is tested independently in
    test_document_calibration_safety.py. This scoped fixture cannot affect it.
    """
    from app.services import document_calibration_policy as calibration
    monkeypatch.setattr(calibration, "AUTO_THRESHOLDS", {kind: .90 for kind in DOCUMENT_TYPES})
    monkeypatch.setattr(calibration, "INFORMATIONAL_AUTO_ENABLED", True)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("关于蓝桥杯报名的通知", "registration_notice"),
        ("关于组织参加全国大学生数学建模竞赛的通知", "organization_notice"),
        ("关于举办电子设计竞赛校内选拔赛的通知", "selection_notice"),
        ("关于推荐参加挑战杯的名单", "recommendation_notice"),
        ("全国大学生英语竞赛获奖结果", "result_notice"),
        ("蓝桥杯获奖名单公示", "publicity_notice"),
        ("数学建模竞赛圆满落幕", "completion_news"),
        ("电子设计竞赛简介", "competition_intro"),
        ("我校举办大学生创新创业大赛活动", "event_news"),
        ("2026年大学生学科竞赛认定目录", "policy_recognition_document"),
        ("大学生学科竞赛奖励办法", "award_policy_document"),
        ("2026年推免竞赛认定目录", "postgraduate_policy_document"),
        ("综合测评竞赛加分目录", "comprehensive_evaluation_policy_document"),
        ("大学生创新学分认定目录", "innovation_credit_policy_document"),
        ("转发关于举办蓝桥杯的通知", "repost"),
        ("蓝桥杯报名截止时间延期通知", "deadline_extension"),
        ("关于蓝桥杯报名条件的更正通知", "correction_notice"),
        ("大学生竞赛管理办法修订说明", "rule_update"),
        ("历年数学建模竞赛资料汇编", "historical_material"),
        ("校园服务信息", "other"),
    ],
)
def test_title_categories_are_distinct(title, expected):
    result = classify_document({"title": title})
    assert result["document_type"] == expected
    assert result["primary_type"] == expected
    assert expected in DOCUMENT_TYPES
    assert DOCUMENT_TYPE_LABELS[expected]


def test_publicity_primary_keeps_result_and_selection_as_secondary():
    result = classify_document({"title": "校赛获奖名单公示"})
    assert result["primary_type"] == "publicity_notice"
    assert {"result_notice", "selection_notice"} <= set(result["secondary_types"])
    assert result["requires_human_confirmation"] is False


def test_quoted_policy_name_in_registration_body_does_not_make_policy():
    result = classify_document(
        {
            "title": "蓝桥杯报名通知",
            "content_text": "报名资格见《2026年推免竞赛认定目录》，请在周五前提交材料。",
            "publisher": "研究生院",
            "section": "政策文件",
            "attachment_titles": ["2026年推免竞赛认定目录.pdf"],
        }
    )
    assert result["primary_type"] == "registration_notice"
    assert not (set(result["secondary_types"]) & POLICY_TYPES)
    assert result["primary_type"] not in POLICY_TYPES


def test_postgraduate_results_publicity_is_not_policy():
    result = classify_document({"source_title": "学生推免结果公示"})
    assert result["primary_type"] == "publicity_notice"
    assert result["primary_type"] not in POLICY_TYPES


def test_repost_heading_with_about_prefix_never_crashes_or_becomes_other():
    result = classify_document(
        {"title": "关于转发《关于组织2025年全国大学生电子设计竞赛的通知》的通知"}
    )
    assert result["primary_type"] == "repost"
    assert "title:转发" in result["matched_rules"]


@pytest.mark.parametrize("title", ["校内选拔赛通知", "数学建模竞赛圆满落幕"])
def test_ordinary_documents_remain_ordinary_when_body_mentions_policy(title):
    result = classify_document(
        {"title": title, "content_preview": "参考《2026年推免竞赛认定目录》中的相关规定。"}
    )
    assert result["primary_type"] not in POLICY_TYPES
    assert not set(result["secondary_types"]) & POLICY_TYPES


def test_source_title_and_opening_body_can_supplement_weak_title():
    result = classify_document(
        {
            "source_title": "关于2026年大学生竞赛的通知",
            "content_preview": "现组织报名参加全国大学生数学建模竞赛，请于6月1日前提交报名表。",
            "section": "竞赛通知",
        }
    )
    assert result["primary_type"] == "registration_notice"
    assert result["classification_status"] == "NEEDS_QUICK_CONFIRM"
    assert any(rule.startswith("body:") for rule in result["matched_rules"])


def test_publisher_alone_cannot_determine_type():
    result = classify_document({"publisher": "教务处", "section": "政策文件"})
    assert result["primary_type"] == "other"
    assert result["classification_status"] == "NEEDS_MANUAL_CLASSIFICATION"


@pytest.mark.parametrize("title", ["蓝桥杯报名延期", "蓝桥杯成绩更正", "竞赛规则更新"])
def test_changes_are_high_risk_even_when_title_is_clear(title):
    result = classify_document({"title": title})
    assert result["risk_level"] == "HIGH_RISK"
    assert result["requires_human_confirmation"] is True
    assert result["informational_only"] is False


def test_secondary_correction_keeps_document_high_risk():
    result = classify_document({"title": "蓝桥杯获奖名单公示及成绩更正"})
    assert result["primary_type"] == "publicity_notice"
    assert "correction_notice" in result["secondary_types"]
    assert result["risk_level"] == "HIGH_RISK"
    assert result["requires_human_confirmation"] is True


@pytest.mark.parametrize("title", ["数学建模竞赛圆满结束", "大学生竞赛简介", "学校举办科技竞赛活动"])
def test_confident_news_is_informational_only_without_pending_effects(title):
    result = classify_document({"title": title})
    assert result["informational_only"] is True
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["requires_human_confirmation"] is False


@pytest.mark.parametrize("flag", ["has_fact_changes", "has_conflicts", "has_valuable_relation"])
def test_pending_effects_keep_news_in_review(flag):
    result = classify_document({"title": "数学建模竞赛圆满结束"}, **{flag: True})
    assert result["informational_only"] is False
    assert result["requires_human_confirmation"] is (flag == "has_conflicts")


def test_clear_formal_policy_type_does_not_require_type_confirmation():
    result = classify_document({"title": "2026年推免竞赛认定目录"})
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["requires_human_confirmation"] is False
    assert result["risk_level"] == "NORMAL"


def test_formal_policy_can_have_two_explicit_recognition_dimensions():
    result = classify_document({"title": "本科生推免与综合测评竞赛目录"})
    assert result["primary_type"] == "postgraduate_policy_document"
    assert result["secondary_types"] == ["comprehensive_evaluation_policy_document"]
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["requires_human_confirmation"] is False


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("武汉大学新闻与传播学院本科学生素质综合测评实施细则（2025年修订版）", "comprehensive_evaluation_policy_document"),
        ("国际教育学院推荐2027届优秀应届本科毕业生免试攻读硕士研究生工作实施细则", "postgraduate_policy_document"),
        ("附件2：河北大学大学生学术科技竞赛奖励方案（试行）.docx", "award_policy_document"),
        ("外国语学院本科人才培养方案（创新实践学分竞赛项目）", "innovation_credit_policy_document"),
    ],
)
def test_explicit_formal_benefit_policy_titles_need_no_competition_keyword(title, expected):
    result = classify_document({"title": title})
    assert result["primary_type"] == expected
    assert result["classification_status"] == "AUTO_CLASSIFIED"


@pytest.mark.parametrize(
    "title",
    [
        "关于开展2024-2025学年第一学期创新实践学分申报的通知",
        "创新实践学分认定结果公示",
        "关于推荐优秀应届本科毕业生免试报名的通知",
    ],
)
def test_benefit_terms_in_ordinary_notices_do_not_make_formal_policy(title):
    result = classify_document({"title": title})
    assert result["primary_type"] not in POLICY_TYPES


def test_formal_policy_types_map_to_distinct_recognition_dimensions():
    assert POLICY_TYPES == set(RECOGNITION_TYPES)
    assert RECOGNITION_TYPES == {
        "policy_recognition_document": "policy_recognition",
        "award_policy_document": "award_recognition",
        "postgraduate_policy_document": "postgraduate_recommendation_recognition",
        "comprehensive_evaluation_policy_document": "comprehensive_evaluation_recognition",
        "innovation_credit_policy_document": "innovation_credit_recognition",
    }


def test_explanation_and_uncalibrated_rule_score_are_returned():
    result = classify_document({"title": "关于蓝桥杯报名的通知"})
    assert 0.90 <= result["confidence"] <= 1.0
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["classification_reason"]
    assert "title:报名" in result["matched_rules"]
    assert result["rule_version"]
