"""Behavioral safety tests for the functional taxonomy and independent policy gate."""

import importlib

import pytest


@pytest.fixture(autouse=True)
def functional_routing_contract(monkeypatch):
    """Test routing mechanisms separately from permissions frozen after replay."""
    from app.services import document_calibration_policy as calibration
    monkeypatch.setattr(calibration, "HIERARCHICAL_AUTO_THRESHOLDS", {
        "participation": .90, "result": .90, "information": .90,
        "repost": .90, "policy": None, "update": None, "other": None,
    }, raising=False)
    monkeypatch.setattr(calibration, "HIERARCHICAL_INFORMATIONAL_ENABLED", True, raising=False)


def classify(source, **flags):
    module = importlib.import_module("app.services.hierarchical_source_classifier")
    return module.classify_source_document(source, **flags)


def policy(source):
    module = importlib.import_module("app.services.policy_safety_classifier")
    return module.classify_policy(source)


@pytest.mark.parametrize("fine,primary,secondary", [
    ("registration_notice", "participation", "registration"),
    ("organization_notice", "participation", "organization"),
    ("selection_notice", "participation", "selection"),
    ("recommendation_notice", "participation", "recommendation"),
    ("result_notice", "result", "result"),
    ("publicity_notice", "result", "publicity"),
    ("completion_news", "information", "completion"),
    ("competition_intro", "information", "intro"),
    ("event_news", "information", "news"),
    ("historical_material", "information", "history"),
    ("policy_recognition_document", "policy", "recognition"),
    ("award_policy_document", "policy", "award"),
    ("postgraduate_policy_document", "policy", "postgraduate"),
    ("comprehensive_evaluation_policy_document", "policy", "comprehensive_evaluation"),
    ("innovation_credit_policy_document", "policy", "innovation_credit"),
    ("deadline_extension", "update", "deadline_extension"),
    ("correction_notice", "update", "correction"),
    ("rule_update", "update", "rule_update"),
    ("repost", "repost", "repost"),
    ("other", "other", "other"),
])
def test_existing_human_fine_types_map_without_relabeling(fine, primary, secondary):
    taxonomy = importlib.import_module("app.services.document_taxonomy")
    assert taxonomy.map_primary_type(fine) == primary
    assert taxonomy.map_secondary_type(fine) == secondary
    assert taxonomy.map_primary_type(primary) == primary


def test_unknown_type_does_not_force_a_functional_guess():
    taxonomy = importlib.import_module("app.services.document_taxonomy")
    assert taxonomy.map_primary_type("unexpected") == "other"
    result = classify({"publisher": "教务处", "section": "通知公告"})
    assert result["primary_type"] == "other"
    assert result["classification_status"] == "NEEDS_MANUAL_CLASSIFICATION"
    assert result["requires_human_confirmation"] is True


@pytest.mark.parametrize("title,primary,secondary", [
    ("关于组织参加算法竞赛校内选拔及报名的通知", "participation", "selection"),
    ("算法竞赛校赛获奖名单公示", "result", "award"),
    ("算法竞赛推荐结果公示", "result", "recommendation_result"),
])
def test_same_functional_action_does_not_require_fine_type_confirmation(title, primary, secondary):
    result = classify({"title": title})
    assert result["primary_type"] == primary
    assert result["secondary_type"] == secondary
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["requires_human_confirmation"] is False
    assert result["hierarchy_version"]
    assert result["document_type"] not in {"participation", "result"}


def test_different_functional_actions_remain_ambiguous():
    result = classify({"title": "算法竞赛获奖名单及下一届比赛报名通知"})
    assert result["classification_status"] != "AUTO_CLASSIFIED"
    assert result["requires_human_confirmation"] is True


@pytest.mark.parametrize("source", [
    {"title": "大学生学科竞赛管理办法", "publisher": "教务处", "content_text": "第一条 学科竞赛实行分类认定，本办法适用于在校学生。"},
    {"title": "关于印发学科竞赛认定目录的通知", "section": "规章制度", "content_text": "序号 竞赛名称 竞赛级别\n1 计算思维竞赛 国家级"},
    {"title": "学科竞赛奖励实施办法", "publisher": "学生工作部", "content_text": "第一条 竞赛奖励按获奖级别执行。"},
    {"title": "本科生综合测评实施细则", "content_text": "第一条 学科竞赛获奖按本办法认定。第二条 本细则自公布之日起施行。"},
    {"title": "推荐优秀本科毕业生免试攻读研究生实施办法", "publisher": "研究生院", "content_preview": "第一条 学科竞赛获奖作为推荐依据。"},
    {"title": "创新实践学分认定管理规定", "publisher": "教务处", "content_text": "第一条 竞赛项目依照附件目录认定学分。"},
    {"title": "有关文件", "publisher": "教务处", "content_text": "现印发学科竞赛管理办法，请遵照执行。第一条 对竞赛实行分类管理。", "attachment_titles": ["学科竞赛认定目录.pdf"]},
])
def test_policy_requires_positive_normative_and_competition_evidence(source):
    result = policy(source)
    assert result["is_policy"] is True
    assert result["policy_status"] == "POLICY"
    assert result["policy_confidence"] >= 0.90
    assert result["positive_evidence"]
    assert result["policy_reason"]


@pytest.mark.parametrize("title", [
    "学生奖励办法", "关于组织参加学科竞赛的报名通知", "推免结果公示",
    "创新学分认定结果公示", "竞赛获奖名单", "大学生竞赛圆满结束",
    "学科竞赛赛事介绍", "校内选拔通知", "学科竞赛获奖奖励申报通知",
])
def test_ordinary_actions_and_generic_rewards_are_not_policy(title):
    result = policy({"title": title, "publisher": "学校教务处", "section": "政策文件"})
    assert result["is_policy"] is False
    assert result["policy_confidence"] < 0.90


def test_quoted_policy_and_formal_attachment_do_not_convert_registration_to_policy():
    source = {
        "title": "算法竞赛报名通知", "publisher": "教务处", "section": "政策文件",
        "content_text": "依据《学科竞赛奖励办法》开展报名，请提交申请表。",
        "attachment_titles": ["学科竞赛奖励办法.pdf"],
    }
    result = classify(source)
    assert result["primary_type"] == "participation"
    assert result["is_policy"] is False
    assert result["policy_assessment"]["negative_evidence"]


def test_attachment_only_policy_lead_requires_confirmation():
    result = policy({"title": "有关通知", "attachment_titles": ["学科竞赛认定目录.pdf"]})
    assert result["is_policy"] is False
    assert result["policy_status"] == "NEEDS_POLICY_CONFIRM"


def test_standalone_unsupported_policy_title_is_not_certified_by_metadata_absence():
    result = policy({"title": "大学生学科竞赛管理办法"})
    assert result["is_policy"] is False
    assert result["policy_status"] == "NEEDS_POLICY_CONFIRM"


def test_policy_primary_is_independent_of_legacy_title_guess_and_cannot_approve_relations():
    result = classify({"title": "学生奖励办法", "publisher": "教务处"})
    assert result["primary_type"] != "policy"
    result = classify({"title": "学科竞赛奖励办法", "publisher": "教务处", "content_text": "第一条 学科竞赛按获奖等级给予奖励。"})
    assert result["primary_type"] == "policy"
    assert result["secondary_type"] == "award"
    assert result["is_policy"] is True
    assert result["classification_status"] == "NEEDS_QUICK_CONFIRM"
    assert result["informational_only"] is False


@pytest.mark.parametrize("source", [
    {"title": "竞赛报名延期通知"},
    {"title": "算法竞赛获奖名单公示及成绩更正"},
    {"title": "算法竞赛圆满结束", "body": "赛事精彩报道。" * 300 + "报名截止时间由6月1日调整为6月8日。"},
    {"title": "竞赛简介", "content_preview": "现更正比赛地点为报告厅。"},
    {"title": "转发算法竞赛新闻", "content_text": "现将报名截止时间延长至六月十日。"},
])
def test_update_in_any_available_body_never_becomes_low_risk_information(source):
    result = classify(source)
    assert result["risk_level"] == "HIGH_RISK"
    assert result["informational_only"] is False
    assert result["requires_human_confirmation"] is True
    assert result["classification_status"] != "AUTO_CLASSIFIED"
    assert result["routing_reason"]


def test_repost_retains_reference_function_but_not_original_policy_evidence():
    result = classify({"title": "转发关于组织参加算法竞赛的通知"})
    assert result["primary_type"] == "repost"
    assert result["referenced_primary_type"] == "participation"
    result = classify({"title": "转发学科竞赛认定目录", "publisher": "教务处"})
    assert result["primary_type"] == "repost"
    assert result["referenced_primary_type"] == "policy"
    assert result["is_policy"] is False
    assert result["informational_only"] is False


@pytest.mark.parametrize("extra", [{}, {"content_preview": "比赛顺利结束，同学们分享学习心得。"}])
def test_information_needs_body_before_being_removed_from_fact_review(extra):
    result = classify({"title": "算法竞赛圆满结束", **extra})
    assert result["primary_type"] == "information"
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["informational_only"] is False


def test_complete_plain_news_can_be_informational_without_type_work():
    result = classify({"title": "算法竞赛圆满结束", "content_text": "比赛顺利结束，同学们分享学习心得。", "content_is_complete": True})
    assert result["primary_type"] == "information"
    assert result["informational_only"] is True
    assert result["requires_human_confirmation"] is False


@pytest.mark.parametrize("flag", ["has_fact_changes", "has_conflicts", "has_valuable_relation"])
def test_pending_effects_keep_information_visible_independently_of_type(flag):
    result = classify({"title": "算法竞赛圆满结束", "content_text": "比赛顺利结束。", "content_is_complete": True}, **{flag: True})
    assert result["informational_only"] is False
    assert result["requires_human_confirmation"] is (flag == "has_conflicts")


@pytest.mark.parametrize("body", [
    "下一届赛事报名截止时间为6月20日，请及时报名。",
    "参赛获奖可依照学科竞赛管理办法计入创新学分。",
])
def test_unextracted_facts_or_policy_leads_cannot_be_hidden_as_information(body):
    result = classify({"title": "算法竞赛圆满结束", "content_text": body, "content_is_complete": True})
    assert result["informational_only"] is False


def test_source_is_not_mutated_by_classification():
    source = {"title": "算法竞赛报名通知", "attachment_titles": ["报名表.docx"]}
    classify(source)
    assert source == {"title": "算法竞赛报名通知", "attachment_titles": ["报名表.docx"]}


@pytest.mark.parametrize("title", [
    "依据学科竞赛管理办法开展报名的通知",
    "学科竞赛奖励办法新闻报道",
    "解读学科竞赛认定目录并组织参加报名活动",
])
def test_policy_name_inside_ordinary_title_is_not_a_normative_document(title):
    result = policy({"title": title, "publisher": "教务处", "section": "规章制度"})
    assert result["is_policy"] is False
    assert result["negative_evidence"]


def test_actual_normative_body_can_support_generic_title_without_an_attachment():
    result = policy({
        "title": "有关文件", "publisher": "教务处",
        "body": "大学生学科竞赛管理办法。第一条 为规范学科竞赛认定。第二条 本办法自发布之日起施行。",
    })
    assert result["is_policy"] is True


def test_publisher_marked_repost_with_weak_title_still_preserves_provenance():
    result = classify({"title": "阅读原文", "publisher": "转载", "content_text": "请报名参加算法竞赛。"})
    assert result["primary_type"] == "repost"
    assert result["referenced_primary_type"] == "participation"


def test_explicitly_incomplete_body_never_enables_information_suppression():
    result = classify({"title": "算法竞赛圆满结束", "content_text": "比赛结束。", "content_is_complete": False})
    assert result["informational_only"] is False


@pytest.mark.parametrize("extra", [{}, {"content_preview": "本年度学科竞赛认定工作安排。"}])
def test_formal_title_and_publisher_need_independent_normative_body_evidence(extra):
    result = policy({"title": "学科竞赛奖励办法", "publisher": "教务处", "section": "规章制度", **extra})
    assert result["is_policy"] is False
    assert result["policy_status"] == "NEEDS_POLICY_CONFIRM"


def test_unverified_body_completeness_keeps_news_in_fact_review():
    result = classify({"title": "算法竞赛圆满结束", "content_text": "比赛顺利结束。"})
    assert result["classification_status"] == "AUTO_CLASSIFIED"
    assert result["informational_only"] is False


@pytest.mark.parametrize("title", [
    "逾千名选手报名 城市算法大赛在本地落幕",
    "三百名学生报名参加的创新竞赛昨日结束",
])
def test_completed_event_reporting_does_not_turn_registration_counts_into_actions(title):
    result = classify({"title": title})
    assert result["primary_type"] == "information"
    assert result["secondary_type"] == "completion"
    assert result["classification_status"] == "AUTO_CLASSIFIED"


@pytest.mark.parametrize("title", [
    "关于算法竞赛报名结束前组织校内选拔的通知",
    "已有三百名学生报名，算法大赛报名将于明日结束",
])
def test_ending_registration_is_still_a_participation_action(title):
    result = classify({"title": title})
    assert result["primary_type"] == "participation"


def test_policy_abstention_retains_legacy_semantic_dimension_without_certifying_it():
    result = classify({"title": "学科竞赛奖励办法", "publisher": "教务处"})
    assert result["primary_type"] == "other"
    assert result["document_type"] == "award_policy_document"
    assert result["secondary_type"] == "award"
    assert result["is_policy"] is False
    assert result["policy_status"] == "NEEDS_POLICY_CONFIRM"
    assert result["requires_human_confirmation"] is True


def test_structured_competition_catalogue_usage_note_is_not_an_application_notice():
    result = policy({
        "title": "大学生竞赛名录（申报时使用）", "publisher": "教学管理部门",
        "content_text": "序号 竞赛名称 竞赛级别\n1 城市计算竞赛 省级",
    })
    assert result["is_policy"] is True
    assert result["policy_status"] == "POLICY"


@pytest.mark.parametrize("body", [
    "The registration deadline has been extended to December 20.",
    "Deadline extension: teams may submit until November 15.",
    "The submission deadline was postponed until Friday.",
    "Correction: the competition venue is now Hall B.",
    "The competition rules have been updated for the final round.",
])
def test_english_operative_updates_cannot_be_archived_as_completed_information(body):
    result = classify({"title": "About the robotics competition", "content_text": body, "content_is_complete": True})
    assert result["risk_level"] == "HIGH_RISK"
    assert result["primary_type"] == "update"
    assert result["informational_only"] is False
    assert result["requires_human_confirmation"] is True


@pytest.mark.parametrize("title", ["【转发】算法竞赛报名通知", "[转载] 关于组织参加算法竞赛的通知"])
def test_wrapped_repost_prefix_cannot_become_original_participation(title):
    result = classify({"title": title})
    assert result["primary_type"] == "repost"
    assert result["referenced_primary_type"] == "participation"


@pytest.mark.parametrize("body", [
    "Registration closes on December 20.",
    "The submission deadline is November 15.",
])
def test_english_pending_dates_do_not_disappear_from_fact_review(body):
    result = classify({"title": "About the robotics competition", "content_text": body, "content_is_complete": True})
    assert result["informational_only"] is False


@pytest.mark.parametrize("body", [
    "本目录中列出的竞赛适用于所有本科学生。",
    "本名录中的竞赛按照相应级别予以认定。",
    "本竞赛目录用于学科竞赛成果认定。",
    "竞赛成果认定自2027年1月1日起实施。",
])
def test_normative_catalogue_references_and_implementation_clauses_are_evidence(body):
    result = policy({"title": "学科竞赛认定目录", "publisher": "教务处", "content_text": body})
    assert result["is_policy"] is True


def test_future_legacy_update_marker_keeps_high_risk_without_duplicate_pattern(monkeypatch):
    from app.services import source_document_classifier as legacy
    # Exercise the real legacy classifier with an additional legacy rule. The
    # functional safety invariant must not rely on duplicating all its rules.
    monkeypatch.setattr(legacy, "_TITLE_RULES", (
        *legacy._TITLE_RULES, ("deadline_extension", ("registration window prolonged",)),
    ))
    result = classify({"title": "The registration window prolonged"})
    assert result["primary_type"] == "update"
    assert result["risk_level"] == "HIGH_RISK"
    assert result["classification_status"] == "NEEDS_MANUAL_CLASSIFICATION"
