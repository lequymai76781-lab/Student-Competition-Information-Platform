"""Functional document classification with independent fact and policy safety.

All scores are transparent rule strengths. This module is pure and grants no
permission to change facts or create formal policy-recognition relations.
"""

from __future__ import annotations

import re

from app.services import document_calibration_policy as calibration
from app.services.document_taxonomy import HIERARCHY_VERSION, map_primary_type, map_secondary_type
from app.services.policy_safety_classifier import classify_policy
from app.services.source_document_classifier import POLICY_TYPES, classify_document


DEFAULT_AUTO_THRESHOLDS = {
    "participation": 0.90, "result": 0.90, "information": 0.90,
    "policy": None, "update": None, "repost": 0.90, "other": None,
}
_UPDATE_PATTERNS = (
    ("deadline_extension", re.compile(
        r"延期|延长报名|报名延长|(?:报名|提交|截止).{0,25}(?:延长|延后|推迟)|"
        r"(?:截止时间|截止日期).{0,35}(?:调整为|变更为|更改为)|"
        r"\bdeadline\s+extension\b|\b(?:registration|submission|entry|deadline)(?:\s+deadline)?\s+"
        r"(?:(?:has|have|is|was|been|now|will|be)\s+){0,4}(?:extended|postponed|delayed)\b", re.I)),
    ("correction_notice", re.compile(
        r"更正|勘误|修正|补充通知|(?:比赛地点|报名条件|报名资格|赛程|主办单位).{0,25}(?:调整为|变更为|更改为)|"
        r"\b(?:correction\s*(?:[:：]|notice\b)|corrigendum\b|erratum\b)", re.I)),
    ("rule_update", re.compile(
        r"规则(?:调整|更新|修订)|办法修订|政策修订|修订说明|"
        r"\brules?\s+(?:(?:have|has|been|are|were|will|be)\s+){0,4}(?:updated|changed|revised|amended)\b|"
        r"\brule\s+(?:change|update|amendment)s?\b", re.I)),
)
_PENDING_FACT = re.compile(
    r"报名(?:截止|条件|资格|时间)|截止(?:时间|日期)|提交.{0,8}(?:截止|期限)|比赛(?:地点|时间)|主办(?:单位|方)|"
    r"(?:赛程|规则).{0,8}(?:调整|变更)|\bdeadline\b|"
    r"\b(?:registration|submission|entry)\s+(?:closes?|eligibility|requirements?)\b", re.I
)


def _policy_fine(source: dict, fallback: str) -> str:
    if fallback in POLICY_TYPES:
        return fallback
    text = "\n".join(str(source.get(key) or "") for key in ("title", "source_title", "content_preview", "content_text", "body", "attachment_titles"))
    for fine, pattern in (
        ("innovation_credit_policy_document", r"创新.{0,4}学分|第二课堂学分"),
        ("postgraduate_policy_document", r"推免|推荐.{0,30}免试"),
        ("comprehensive_evaluation_policy_document", r"综合测评|综合素质测评|综测"),
        ("award_policy_document", r"奖励(?:办法|标准|方案|实施办法)"),
    ):
        if re.search(pattern, text):
            return fine
    return "policy_recognition_document"


def classify_source_document(source: dict, *, has_fact_changes=False, has_conflicts=False,
                             has_valuable_relation=False) -> dict:
    """Classify the saved source; automatic type decisions never approve facts."""
    legacy = classify_document(source, has_fact_changes=has_fact_changes,
                               has_conflicts=has_conflicts, has_valuable_relation=has_valuable_relation)
    assessment = classify_policy(source)
    title = str(source.get("title") or source.get("source_title") or "")
    bodies = [(key, str(source.get(key) or "")) for key in ("content_preview", "content_text", "body")]
    updates = [(fine, f"{location}:{match.group()}")
               for location, text in [("title", title), *bodies]
               for fine, pattern in _UPDATE_PATTERNS
               if (match := pattern.search(text))]
    fine = legacy["document_type"]
    secondary_types = list(legacy["secondary_types"])
    primary = map_primary_type(fine)
    confidence = legacy["confidence"]
    matched_rules = list(legacy["matched_rules"])
    reason = legacy["classification_reason"]
    referenced = None

    title_repost = bool(re.match(r"^[\s【\[（(]*(?:转发|转载)", title))
    publisher_repost = bool(re.search(r"转载|转发", str(source.get("publisher") or "")))
    if primary != "repost" and (title_repost or publisher_repost):
        secondary_types = list(dict.fromkeys([fine, *secondary_types]))
        fine, primary = "repost", "repost"
        matched_rules.append("title:明确转载前缀" if title_repost else "publisher:明确转载")

    if primary == "repost":
        referenced_types = [map_primary_type(kind) for kind in secondary_types if kind != "repost"]
        if updates:
            referenced = "update"
        elif referenced_types:
            referenced = referenced_types[0]
        elif assessment["policy_status"] == "NEEDS_POLICY_CONFIRM" and any(
            evidence.startswith("title:") for evidence in assessment["positive_evidence"]
        ):
            referenced = "policy"
        else:
            referenced = "other"
        confidence = max(confidence, 0.94)
    elif updates:
        if fine not in {kind for kind, _ in updates}:
            secondary_types = list(dict.fromkeys([*secondary_types, fine]))
        fine = updates[0][0]
        primary = "update"
        confidence = 0.94
        reason = "标题或正文存在实际延期、更正或规则变更信号，必须进入字段复核"
    elif assessment["is_policy"]:
        fine = _policy_fine(source, fine)
        primary = "policy"
        confidence = assessment["policy_confidence"]
        reason = assessment["policy_reason"]
    elif primary == "policy":
        # Retain the old semantic dimension for historical relations. A failed
        # evidence gate means "unconfirmed", not proof that an old policy was
        # invalid. Only the functional route and independent policy flag deny
        # authorization; the fine suggestion remains available for review.
        primary = "other"
        confidence = assessment["policy_confidence"]
        reason = "旧细分类的政策猜测未通过独立正向证据判定，保留人工确认"

    completion_report = bool(
        primary in {"participation", "information"}
        and re.search(r"[\d一二三四五六七八九十百千万].{0,16}(?:人|名|支|所|队).{0,10}报名", title)
        and re.search(r"(?:竞赛|比赛|大赛|赛事)[^，。]{0,20}(?:落幕|结束|完赛)[！!。]*$", title)
        and not re.search(r"通知|(?:将|即将|预计).{0,12}(?:结束|落幕)|报名(?:工作|通道)?.{0,6}(?:结束|截止)", title)
    )
    if completion_report:
        fine, primary, confidence = "completion_news", "information", 0.94
        matched_rules.append("title:报名人数与已结束赛事报道")
        reason = "标题报道已结束赛事，报名人数是回顾性统计，不是当前报名指令"

    matched_rules.extend(rule for _, rule in updates if rule not in matched_rules)
    route_types = {map_primary_type(kind) for kind in [fine, *secondary_types]}
    # A school round in a result title describes the completed event, not a
    # second participation action requiring administrators to choose a type.
    if primary == "result" and "selection_notice" in secondary_types and not re.search(r"报名|组织参加|推荐参加", title):
        route_types.discard("participation")
    ambiguous = bool(route_types - {primary, "other"}) and primary not in {"update", "repost", "policy"}
    if not ambiguous and primary in {"participation", "result", "information"} and any(
        rule.startswith("title:") for rule in matched_rules
    ):
        confidence = max(confidence, 0.94)
        if "；标题同时包含其他行为，需确认主类型" in reason:
            reason = reason.replace("；标题同时包含其他行为，需确认主类型",
                                    "；细标签虽有多个，一级功能一致，无需选择细分类型")

    high_risk = bool(primary == "update" or updates or has_conflicts or legacy.get("risk_level") == "HIGH_RISK")
    risk = "HIGH_RISK" if high_risk else "NORMAL" if primary == "policy" or assessment["policy_status"] == "NEEDS_POLICY_CONFIRM" else "LOW_RISK"
    thresholds = getattr(calibration, "HIERARCHICAL_AUTO_THRESHOLDS", DEFAULT_AUTO_THRESHOLDS)
    threshold = thresholds.get(primary)
    evidence = bool(matched_rules or assessment["is_policy"])
    if primary != "other" and evidence and not ambiguous and risk != "HIGH_RISK":
        status = "AUTO_CLASSIFIED" if threshold is not None and confidence >= threshold else "NEEDS_QUICK_CONFIRM"
    else:
        status = "NEEDS_MANUAL_CLASSIFICATION"

    full_body = str(source.get("content_text") or source.get("body") or "").strip()
    pending_fields = bool(_PENDING_FACT.search("\n".join([title, *(text for _, text in bodies)])))
    pending_effects = bool(has_fact_changes or has_conflicts or has_valuable_relation)
    information_safe = bool(
        getattr(calibration, "HIERARCHICAL_INFORMATIONAL_ENABLED", True)
        and primary == "information" and status == "AUTO_CLASSIFIED"
        and full_body and not source.get("content_truncated")
        and source.get("content_is_complete") is True
        and not updates and not pending_fields and not pending_effects
        and assessment["policy_status"] == "NON_POLICY"
    )
    if risk == "HIGH_RISK":
        routing_reason = "重要变更或来源冲突，必须保留字段复核；分类不批准事实"
    elif information_safe:
        routing_reason = "已检查可用正文，未见关键字段、政策线索或待处理影响，可作为普通赛事信息"
    elif primary == "information":
        routing_reason = "赛事信息类型已识别，但正文不足或存在关键字段、政策线索、待处理影响，保留事实审核"
    elif primary == "repost":
        routing_reason = "明确转发，保留原文功能；不得视作原始官方依据"
    elif primary == "policy" or assessment["policy_status"] == "NEEDS_POLICY_CONFIRM":
        routing_reason = "政策文档/线索、赛事抽取、匹配与关系决定分别审核，本分类不授予政策关系自动权限"
    else:
        routing_reason = "一级类型与细标签分开；自动分类只免除类型选择，字段事实仍独立审核"

    secondary = map_secondary_type(fine)
    if primary == "result":
        if re.search(r"推荐(?:结果|名单)|拟推荐", title):
            secondary = "recommendation_result"
        elif re.search(r"获奖|奖项", title):
            secondary = "award"
    return {
        **legacy,
        "document_type": fine, "primary_type": primary,
        "secondary_type": secondary, "secondary_types": secondary_types,
        "referenced_primary_type": referenced,
        "hierarchy_version": HIERARCHY_VERSION,
        "confidence": confidence, "classification_reason": reason,
        "matched_rules": matched_rules, "classification_status": status,
        "risk_level": risk, "informational_only": information_safe,
        "requires_human_confirmation": status != "AUTO_CLASSIFIED" or risk == "HIGH_RISK",
        "routing_reason": routing_reason, "policy_assessment": assessment,
        "is_policy": assessment["is_policy"],
        "policy_confidence": assessment["policy_confidence"],
        "policy_reason": assessment["policy_reason"],
        "policy_status": assessment["policy_status"],
        "auto_threshold": threshold,
    }
