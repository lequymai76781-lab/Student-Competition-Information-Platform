"""Pure, explainable source-document classification.

Scores are rule strengths, not calibrated probabilities. This module never
grants policy recognition or changes competition facts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


RULE_VERSION = "document-rules-1.1"

DOCUMENT_TYPES = (
    "registration_notice", "organization_notice", "selection_notice",
    "recommendation_notice", "result_notice", "publicity_notice",
    "completion_news", "competition_intro", "event_news",
    "policy_recognition_document", "award_policy_document",
    "postgraduate_policy_document", "comprehensive_evaluation_policy_document",
    "innovation_credit_policy_document", "repost", "deadline_extension",
    "correction_notice", "rule_update", "historical_material", "other",
)
RECOGNITION_TYPES = {
    "policy_recognition_document": "policy_recognition",
    "award_policy_document": "award_recognition",
    "postgraduate_policy_document": "postgraduate_recommendation_recognition",
    "comprehensive_evaluation_policy_document": "comprehensive_evaluation_recognition",
    "innovation_credit_policy_document": "innovation_credit_recognition",
}
POLICY_TYPES = set(RECOGNITION_TYPES)
DOCUMENT_TYPE_LABELS = dict(zip(DOCUMENT_TYPES, (
    "报名通知", "组织通知", "校赛/选拔通知", "推荐通知", "结果通知", "公示",
    "完赛新闻", "赛事介绍", "活动新闻", "竞赛认定政策", "竞赛奖励政策",
    "推免政策", "综合测评政策", "创新学分政策", "转载/转发", "延期通知",
    "更正通知", "规则更新", "历史资料", "其他",
)))

_RISK_TYPES = {"deadline_extension", "correction_notice", "rule_update"}
_INFORMATION_TYPES = {"completion_news", "competition_intro", "event_news"}
_FORMAL_MARKERS = ("目录", "清单", "办法", "细则", "规定", "标准", "政策", "认定", "加分方案", "奖励方案", "培养方案", "管理制度")
_COMPETITION_MARKERS = ("竞赛", "大赛", "赛事", "比赛", "学科竞赛", "校赛")

# Rules are ordered by specificity. A marker is emitted in matched_rules so
# reviewers can trace the decision to the actual title or opening paragraph.
_TITLE_RULES = (
    ("repost", ("转发", "转载")),
    ("deadline_extension", ("延期", "延长报名", "报名延长", "截止时间延长")),
    ("correction_notice", ("更正", "修正", "补充通知", "勘误")),
    ("rule_update", ("规则调整", "办法修订", "规则更新", "规则修订", "政策修订", "修订说明")),
    ("publicity_notice", ("公示",)),
    ("selection_notice", ("校内选拔", "校级选拔", "选拔赛", "校赛", "选拔", "校内初赛", "校内赛")),
    ("result_notice", ("获奖名单", "获奖结果", "成绩公布", "比赛结果", "竞赛结果", "评审结果")),
    ("recommendation_notice", ("推荐名单", "推荐参加", "推选", "拟推荐")),
    ("registration_notice", ("报名", "征集作品", "参赛报名")),
    ("organization_notice", ("组织参加", "组织开展", "关于举办", "关于组织", "承办", "组织参赛")),
    ("completion_news", ("圆满结束", "圆满落幕", "成功举办", "顺利完赛", "完赛", "顺利结束")),
    ("competition_intro", ("赛事介绍", "竞赛简介", "大赛简介", "比赛简介")),
    ("historical_material", ("历年", "历史资料", "资料汇编", "往届回顾")),
)


def _first_match(value: str, markers: Iterable[str]) -> str | None:
    return next((marker for marker in markers if marker in value), None)


def _policy_title_matches(title: str) -> list[tuple[str, str]]:
    """Require a formal title shape; policy words in a notice are not enough."""
    formal = _first_match(title, _FORMAL_MARKERS)
    if not formal:
        return []
    matches = []
    for kind, markers in (
        ("innovation_credit_policy_document", ("创新学分", "第二课堂学分", "创新创业学分", "创新实践学分")),
        ("postgraduate_policy_document", ("推免", "保研", "推荐免试")),
        ("comprehensive_evaluation_policy_document", ("综合测评", "综测", "综合素质测评")),
        ("award_policy_document", ("奖励办法", "奖励标准", "奖励方案", "奖金", "竞赛奖励", "获奖奖励")),
    ):
        marker = _first_match(title, markers)
        if marker:
            matches.append((kind, marker))
    if not any(kind == "postgraduate_policy_document" for kind, _ in matches):
        recommendation = re.search(r"推荐.{0,40}免试", title)
        if recommendation:
            matches.append(("postgraduate_policy_document", recommendation.group()))
    if matches:
        return matches
    if _first_match(title, _COMPETITION_MARKERS) and _first_match(
        title, ("认定", "分类", "目录", "清单", "管理办法", "管理规定")
    ):
        return [("policy_recognition_document", formal)]
    return []


def _title_hits(title: str) -> list[tuple[str, str]]:
    hits = []
    for kind, markers in _TITLE_RULES:
        marker = _first_match(title, markers)
        if marker:
            hits.append((kind, marker))

    # A specific, formal policy title can classify a document, while a policy
    # name quoted in a regular notice cannot. Ordinary action words win.
    policies = _policy_title_matches(title)
    if policies and not any(kind in {
        "registration_notice", "recommendation_notice", "result_notice",
        "publicity_notice", "selection_notice", "deadline_extension",
        "correction_notice", "repost",
    } for kind, _ in hits):
        hits.extend(policies)

    # "关于举办..." is an organization notice. "举办...活动" is news.
    if not hits and _first_match(title, ("举办", "举行", "开展")) and _first_match(title, ("竞赛", "大赛", "赛事")):
        hits.append(("event_news", _first_match(title, ("活动", "举办", "举行", "开展"))))
    if not hits and re.search(r"\b(?:contest|competition|championship|icpc)\b", title, re.I):
        marker = re.search(r"\b(?:about|fact\s+sheet)\b", title, re.I)
        if marker:
            hits.append(("competition_intro", marker.group()))
    return hits


def _choose_primary(hits: list[tuple[str, str]], title: str) -> str:
    kinds = {kind for kind, _ in hits}
    if title.lstrip().startswith(("转发", "转载", "关于转发", "关于转载")):
        return "repost"
    if "publicity_notice" in kinds:
        return "publicity_notice"
    for kind in ("deadline_extension", "correction_notice", "rule_update"):
        if kind in kinds:
            return kind
    for kind in (
        "innovation_credit_policy_document", "postgraduate_policy_document",
        "comprehensive_evaluation_policy_document", "award_policy_document",
        "policy_recognition_document", "selection_notice", "result_notice",
        "recommendation_notice", "registration_notice", "organization_notice",
        "completion_news", "competition_intro", "event_news", "historical_material",
    ):
        if kind in kinds:
            return kind
    return hits[0][0] if hits else "other"


def _opening_text(source: dict) -> str:
    # Only the beginning is useful for classifying what a document *is*.
    preview = source.get("content_preview") or source.get("content_text") or ""
    return str(preview)[:800]


def _auxiliary_hit(source: dict) -> tuple[str, str, str] | None:
    body = _opening_text(source)
    for kind, markers in (
        ("deadline_extension", ("报名截止时间延期", "报名截止时间延长")),
        ("correction_notice", ("现更正", "更正如下")),
        ("rule_update", ("规则调整如下", "规则更新如下")),
        ("registration_notice", ("组织报名", "报名参加", "提交报名表", "开始报名")),
        ("selection_notice", ("校内选拔", "校级选拔")),
        ("organization_notice", ("组织参加", "组织开展")),
        ("result_notice", ("获奖名单", "获奖结果", "成绩公布")),
        ("completion_news", ("圆满结束", "圆满落幕", "顺利完赛")),
    ):
        marker = _first_match(body, markers)
        if marker:
            return kind, "body", marker

    # A formal document attached to a generic page is a useful lead but still
    # needs confirmation; the classifier does not inspect the attachment.
    attachments = source.get("attachment_titles") or []
    if isinstance(attachments, str):
        attachments = [attachments]
    for attachment in attachments:
        policies = _policy_title_matches(str(attachment))
        if policies:
            return policies[0][0], "attachment", policies[0][1]
    return None


def classify_document(source: dict, *, has_fact_changes=False, has_conflicts=False,
                      has_valuable_relation=False) -> dict:
    """Classify a saved source without I/O, model calls, or state changes."""
    title = str(source.get("title") or source.get("source_title") or "").strip()
    from app.services import document_calibration_policy as calibration
    body = str(source.get("content_preview") or source.get("content_text") or "")
    # A navigation page is not one of the documents linked in its body. Both a
    # generic heading and list/navigation evidence are required; never discard
    # an article merely because its URL contains 'list'.
    is_listing = (len(title) <= 12 and title in {"学科竞赛", "竞赛通知", "通知公告", "学科竞赛通知", "竞赛信息"}
                  and bool(re.search(r"下一页|每页|总共|当前位置", body))
                  and bool(re.search(r"(?:/list\d*\.(?:htm|html)|/list/)", str(source.get("source_url") or source.get("url") or ""))))
    training = bool(re.search(r"集训|培训班|实验班|训练营", title)) and not re.search(r"获奖|获佳绩|夺冠|斩获|管理办法|政策", title)
    excluded_context = is_listing or training
    hits = [] if excluded_context else _title_hits(title)
    publisher_repost = not excluded_context and bool(re.search(r"转载|转发", str(source.get("publisher") or "")))
    ambiguous = False
    if hits:
        primary = "repost" if publisher_repost else _choose_primary(hits, title)
        if publisher_repost and not any(kind == "repost" for kind, _ in hits):
            hits.append(("repost", "发布者明确标记转载"))
        secondary = [kind for kind, _ in hits if kind != primary]
        secondary = list(dict.fromkeys(secondary))
        matched_rules = [f"title:{marker}" for _, marker in hits]
        primary_marker = next(marker for kind, marker in hits if kind == primary)
        reason = f"标题包含“{primary_marker}”，按规则归为{DOCUMENT_TYPE_LABELS[primary]}"
        if publisher_repost:
            matched_rules = [rule for rule in matched_rules if rule != "title:发布者明确标记转载"] + ["publisher:明确转载"]
            reason = "发布机构元数据明确标记转载；保留原文行为作为次要类型"
        confidence = 0.97 if primary == "publicity_notice" else 0.94
        if primary in POLICY_TYPES:
            confidence = 0.92
        # Different operative actions in one title are genuinely ambiguous.
        paired = set(secondary) - {"result_notice", "selection_notice"} if primary == "publicity_notice" else set(secondary)
        if paired and not (
            (primary in POLICY_TYPES and paired <= POLICY_TYPES)
            or (primary in _RISK_TYPES and paired <= {"registration_notice", "result_notice"})
        ):
            ambiguous = True
            confidence = 0.82
            reason += "；标题同时包含其他行为，需确认主类型"
    else:
        auxiliary = None if excluded_context else _auxiliary_hit(source)
        if auxiliary:
            primary, location, marker = auxiliary
            secondary = []
            matched_rules = [f"{location}:{marker}"]
            reason = f"标题未明确，{location}包含“{marker}”"
            confidence = 0.76 if location == "body" else 0.69
            if source.get("section") or source.get("publisher"):
                confidence = min(confidence + 0.02, 0.89)
        else:
            primary, secondary = "other", []
            matched_rules = []
            reason = "标题及正文开头没有足够的类型证据"
            confidence = 0.35
            if excluded_context:
                reason = "栏目导航页，不能用链接文章代替文档分类" if is_listing else "培训或集训事项，不能据活动词认定竞赛通知或完赛新闻"
                matched_rules = ["context:list_page" if is_listing else "context:training"]
    # A clear news title must not mask an operative correction in its opening.
    auxiliary = None if excluded_context else _auxiliary_hit(source)
    if auxiliary and auxiliary[0] in _RISK_TYPES and auxiliary[0] != primary:
        kind, location, marker = auxiliary
        secondary = list(dict.fromkeys([*secondary, kind]))
        matched_rules.append(f"{location}:{marker}")
        reason += "；正文含重要变更，必须人工复核"
    risk_types = {primary, *secondary} & _RISK_TYPES
    risk = "HIGH_RISK" if risk_types or has_conflicts else "NORMAL" if primary in POLICY_TYPES else "LOW_RISK"
    status = calibration.review_status(primary, confidence, has_evidence=bool(matched_rules),
                                       ambiguous=ambiguous, high_risk=risk == "HIGH_RISK")
    pending_effects = has_fact_changes or has_conflicts or has_valuable_relation
    informational_only = (
        calibration.INFORMATIONAL_AUTO_ENABLED and primary in _INFORMATION_TYPES and status == "AUTO_CLASSIFIED"
        and not pending_effects and not risk_types
    )
    # This flag concerns the *document type*. Pending field changes and policy
    # relations have their own review gates in the integration service.
    requires_confirmation = bool(status != "AUTO_CLASSIFIED" or risk_types)
    return {
        "document_type": primary, "primary_type": primary, "secondary_types": secondary,
        "confidence": confidence, "classification_reason": reason,
        "matched_rules": matched_rules,
        "requires_human_confirmation": requires_confirmation,
        "informational_only": informational_only, "risk_level": risk,
        "classification_status": status, "rule_version": RULE_VERSION,
        "calibration_policy_version": calibration.VERSION,
        "auto_threshold": calibration.AUTO_THRESHOLDS.get(primary),
    }
