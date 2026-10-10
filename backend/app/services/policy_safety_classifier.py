"""Independent, conservative POLICY evidence assessment, without I/O.

Scores express rule strength, not a calibrated probability. Even POLICY does
not verify the source, a competition match, an effective date, or a relation.
"""

from __future__ import annotations

import re


POLICY_RULE_VERSION = "policy-safety-1.0"
POLICY_DECISION_THRESHOLD = 0.90

_FORMAL = re.compile(
    r"管理办法|认定目录|认定名录|竞赛目录|竞赛名录|实施办法|实施细则|奖励办法|管理规定|认定标准|认定办法|"
    r"竞赛清单|竞赛分类|加分目录|加分办法|加分方案|奖励标准|奖励方案|培养方案|管理制度"
)
_COMPETITION = re.compile(r"竞赛|大赛|赛事|比赛|\b(?:competition|contest|championship)\b", re.I)
_BENEFIT = re.compile(r"推免|推荐.{0,30}免试|综合测评|综合素质测评|综测|创新.{0,4}学分|第二课堂学分")
_BODY_STRUCTURE = re.compile(
    r"第[一二三四五六七八九十\d]+[条章]|现印发|遵照执行|"
    r"本(?:办法|细则|规定|(?:竞赛)?目录|(?:竞赛)?名录)|自.{0,20}(?:施行|实施|执行)"
)
_CATALOGUE_STRUCTURE = re.compile(
    r"(?:序号|编号)[^\n]{0,40}(?:竞赛名称|赛事名称|比赛名称)|"
    r"(?:竞赛|赛事|比赛)名称[^\n]{0,40}(?:级别|类别|等级)|"
    r"(?:奖项|获奖等级)[^\n]{0,40}(?:奖励标准|奖励金额|分值)"
)
_INSTITUTION = re.compile(r"教务|学院|大学|学校|研究生院|学生工作|教育|委员会|办公室|教学管理")
_SECTION = re.compile(r"政策|规章|制度|管理文件|文件发布")
_ORDINARY = re.compile(r"报名|校赛|选拔|获奖名单|获奖结果|公示|结果|圆满结束|圆满落幕|赛事介绍|竞赛简介|新闻|报道|举办|组织参加|组织开展|申报|申请|征求意见|草案")
_REPOST = re.compile(r"转发|转载")


def _evidence(pattern: re.Pattern, value: str, location: str) -> list[str]:
    return [f"{location}:{match}" for match in dict.fromkeys(pattern.findall(value))]


def classify_policy(source: dict) -> dict:
    """Require normative structure, competition relevance, and corroboration.

    Quoted or attached policies are leads rather than certification that their
    parent notice is a policy. An explicit repost is never original evidence.
    """
    title = str(source.get("title") or source.get("source_title") or "").strip()
    publisher = str(source.get("publisher") or "")
    section = str(source.get("section") or "")
    body = "\n".join(str(source.get(key) or "") for key in ("content_preview", "content_text", "body"))
    attachment_titles = source.get("attachment_titles") or []
    if isinstance(attachment_titles, str):
        attachment_titles = [attachment_titles]
    attachments = "\n".join(str(item) for item in attachment_titles)

    title_formal = _evidence(_FORMAL, title, "title")
    body_formal = _evidence(_FORMAL, body, "body")
    attachment_formal = _evidence(_FORMAL, attachments, "attachment")
    normative = _evidence(_BODY_STRUCTURE, body, "body_structure")
    catalogue = _evidence(_CATALOGUE_STRUCTURE, body, "body_catalogue")
    competition = _evidence(_COMPETITION, title + "\n" + body + "\n" + attachments, "competition")
    institution = _evidence(_INSTITUTION, publisher, "publisher")
    section_evidence = _evidence(_SECTION, section, "section")
    benefit = _evidence(_BENEFIT, title + "\n" + body, "benefit")
    positive = [*title_formal, *body_formal, *attachment_formal, *normative, *catalogue,
                *competition, *institution, *section_evidence, *benefit]
    negative = _evidence(_ORDINARY, title, "title_action")
    repost = bool(_REPOST.search(title + "\n" + publisher))
    if repost:
        negative.append("provenance:explicit_repost")

    formal_end = bool(re.search(r"(?:" + _FORMAL.pattern + r")(?:[》」）)]|[（(][^）)]*[）)]|\s|[.a-zA-Z\d])*?$", title))
    issuance = bool(title_formal and re.search(r"(?:印发|发布|公布).*(?:办法|细则|规定|标准|目录|方案)", title))
    direct_title = bool(title_formal and (formal_end or issuance))
    # A genuinely normative title can contain an operative word, e.g.
    # "竞赛选拔管理办法". A quoted title in "报名通知" cannot override it.
    ordinary_veto = bool(negative and not direct_title)
    has_formal = bool(title_formal or body_formal or attachment_formal)
    # Issuer/section metadata and a formal-looking heading cannot certify that
    # an extracted page actually contains the operative policy. Require text
    # from clauses or a structured competition/award catalogue as well.
    title_supported = direct_title and bool(normative or catalogue)
    attached_supported = bool(attachment_formal and normative and (institution or section_evidence))
    body_supported = bool(body_formal and (normative or catalogue) and (institution or section_evidence))
    strong = bool(competition and (title_supported or attached_supported or body_supported))

    if strong and not ordinary_veto and not repost:
        score = 0.94 if normative else 0.92
        status = "POLICY"
        reason = "规范文件结构、赛事相关内容和独立发布/正文证据同时成立；仍须单独验证来源、有效期与赛事匹配"
    elif has_formal or benefit:
        score = 0.68 if competition and not ordinary_veto else 0.42
        status = "NEEDS_POLICY_CONFIRM"
        reason = "存在政策线索，但正文、发布结构或赛事相关性证据不足"
        if ordinary_veto:
            reason = "页面以报名、结果或新闻等普通事项为主；所引政策和附件仅作为待核实线索"
        if repost:
            reason = "明确转载仅提供政策线索，不能作为原始官方政策依据"
    else:
        score = 0.12 if negative else 0.20
        status = "NON_POLICY"
        reason = "没有足够的规范政策正向证据；普通赛事或学校奖励词不能确认为政策"
    return {
        "is_policy": status == "POLICY" and score >= POLICY_DECISION_THRESHOLD,
        "policy_confidence": score,
        "policy_reason": reason,
        "policy_status": status,
        "positive_evidence": positive,
        "negative_evidence": negative,
        "policy_rule_version": POLICY_RULE_VERSION,
        "policy_decision_threshold": POLICY_DECISION_THRESHOLD,
    }
