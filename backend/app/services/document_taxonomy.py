"""Lossless mapping of existing fine labels to seven functional routes."""

HIERARCHY_VERSION = "document-hierarchy-1.0"
PRIMARY_TYPES = ("participation", "result", "information", "policy", "update", "repost", "other")
PRIMARY_TYPE_LABELS = {
    "participation": "参赛相关", "result": "结果/公示", "information": "赛事信息",
    "policy": "政策/认定", "update": "更新/更正", "repost": "转发", "other": "其他",
}

FINE_TO_PRIMARY = {
    "registration_notice": "participation", "organization_notice": "participation",
    "selection_notice": "participation", "recommendation_notice": "participation",
    "result_notice": "result", "publicity_notice": "result",
    "completion_news": "information", "competition_intro": "information",
    "event_news": "information", "historical_material": "information",
    "policy_recognition_document": "policy", "award_policy_document": "policy",
    "postgraduate_policy_document": "policy", "comprehensive_evaluation_policy_document": "policy",
    "innovation_credit_policy_document": "policy",
    "deadline_extension": "update", "correction_notice": "update", "rule_update": "update",
    "repost": "repost", "other": "other",
}
FINE_TO_SECONDARY = {
    "registration_notice": "registration", "organization_notice": "organization",
    "selection_notice": "selection", "recommendation_notice": "recommendation",
    "result_notice": "result", "publicity_notice": "publicity",
    "completion_news": "completion", "competition_intro": "intro",
    "event_news": "news", "historical_material": "history",
    "policy_recognition_document": "recognition", "award_policy_document": "award",
    "postgraduate_policy_document": "postgraduate",
    "comprehensive_evaluation_policy_document": "comprehensive_evaluation",
    "innovation_credit_policy_document": "innovation_credit",
    "deadline_extension": "deadline_extension", "correction_notice": "correction",
    "rule_update": "rule_update", "repost": "repost", "other": "other",
}


def map_primary_type(value: str | None) -> str:
    """Accept historical fine labels or an already-normalized primary label."""
    return value if value in PRIMARY_TYPES else FINE_TO_PRIMARY.get(value, "other")


def map_secondary_type(value: str | None) -> str:
    """Keep fine ground truth intact; unknown input has no invented fine label."""
    return FINE_TO_SECONDARY.get(value, "other")
