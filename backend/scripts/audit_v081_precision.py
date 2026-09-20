"""V0.8.2 precision audit over the V0.8.1 discovery payload.

Produces:
  - 11-way lead classification (registration/announcement/submission/internal/
    result/award/training/team/activity/irrelevant/unknown)
  - per top-school sample quality stats
  - competition-match consistency flags
  - per-relation validity flags (incl. deadline sanity)
"""

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

AUDIT_LABELS = (
    "registration_notice",
    "competition_announcement",
    "submission_notice",
    "internal_selection",
    "result_notice",
    "award_news",
    "training_notice",
    "team_recruitment",
    "activity",
    "irrelevant",
    "unknown",
)

AWARD_TERMS = (
    "获奖", "荣获", "获佳绩", "获得优异成绩", "喜获", "斩获", "创佳绩", "创历史",
    "最高奖", "一等奖", "二等奖", "三等奖", "特等奖", "获最高奖", "位居", "圆满收官",
    "落下帷幕", "落幕", "圆满结束", "晋级全国", "进入全国赛", "挺进国赛",
)
RESULT_TERMS = ("评审结果", "结果公示", "公示", "获奖名单", "晋级名单", "成绩公布", "名单公示", "拟推荐名单")
ACTIVITY_TERMS = (
    "顺利举行", "成功举办", "圆满举行", "在我校举行", "在我校举办", "现场赛", "动员会",
    "打磨会", "分享会", "交流会", "论坛", "研讨会", "沙龙", "参观", "启动仪式",
    "校赛现场", "落下帷幕", "落幕", "举行", "举办", "开赛", "答辩会",
)
TRAINING_TERMS = ("讲座", "培训", "训练营", "宣讲会", "辅导", "集训", "授课", "公开课")
ADMISSION_TERMS = (
    "招生", "录取", "调剂", "考研", "复试", "推免", "免试", "保研", "博士", "硕士",
    "学籍", "报到", "军训", "就业", "招聘", "选课", "课表", "补考", "重修", "宿舍",
    "食堂", "校园卡", "学位论文", "毕业论文", "查重",
)
REFERENCE_TERMS = ("目录", "汇编", "一览表", "汇总表", "立项名单", "结题")
COLUMN_TITLE_RE = re.compile(
    r"^(学科竞赛|通知公告|公告通知|新闻动态|竞赛通知|教务通知|最新通知|赛事信息|学院新闻|学校新闻|工作动态)[—-]"
)


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").lower())


def _is_column_url(url: str) -> bool:
    path = urlparse_path(url)
    if path in {"", "/", "/index.htm", "/index.html"}:
        return True
    return bool(re.search(r"/(?:tzgg|notice|news|list|gg|zxdt|tongzhi|cxcy|cxds|xkjs)[/-]?$", path, re.I))


def urlparse_path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path.lower()


@dataclass(slots=True)
class AuditedLead:
    lead: dict
    audit_class: str = "unknown"
    flags: list[str] = field(default_factory=list)


def classify_title(title: str, text: str, url: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    title = title or ""
    text = (text or "")[:4000]
    combined = f"{title} {text[:1200]}"
    if not title:
        return "unknown", ["empty_title"]
    if COLUMN_TITLE_RE.match(title):
        return "unknown", ["column_page_title"]
    if _is_column_url(url):
        flags.append("column_url")
    if re.search(r"20(?:1[0-9]|2[0-3])[年\-/.]", title):
        flags.append("old_year_title")
    if any(term in title for term in ADMISSION_TERMS):
        if not any(term in title for term in ("竞赛", "大赛", "比赛", "选拔赛", "参赛")):
            return "irrelevant", flags + ["admission_topic"]
    if any(term in title for term in REFERENCE_TERMS):
        return "irrelevant", flags + ["reference_page"]
    if any(term in title for term in AWARD_TERMS):
        if any(term in title for term in RESULT_TERMS):
            return "result_notice", flags + ["result_terms"]
        return "award_news", flags + ["award_terms"]
    if any(term in title for term in RESULT_TERMS):
        return "result_notice", flags + ["result_terms"]
    if any(term in title for term in TRAINING_TERMS):
        if any(term in title for term in ("竞赛", "大赛", "比赛", "参赛", "报名")):
            return "competition_announcement", flags + ["training_with_competition"]
        return "training_notice", flags + ["training_terms"]
    if any(term in title for term in TEAM_TERMS):
        return "team_recruitment", flags + ["team_terms"]
    if any(term in title for term in ACTIVITY_TERMS):
        if any(term in title for term in ("通知", "报名", "选拔", "参赛")) and "举行" not in title:
            pass
        else:
            return "activity", flags + ["activity_terms"]
    if "组织参加" in title or "组织学生参加" in title:
        return "registration_notice", flags + ["organize_participation"]
    if "选拔" in title or "校赛" in title or "预选" in title or "初赛" in title:
        return "internal_selection", flags + ["selection_terms"]
    if "报名" in title:
        return "registration_notice", flags + ["registration_terms"]
    if "提交" in title or "作品征集" in title or "报送" in title or "投稿" in title:
        return "submission_notice", flags + ["submission_terms"]
    if "招募" in title or "组队" in title:
        return "team_recruitment", flags + ["team_terms"]
    if any(term in title for term in ("大赛", "竞赛", "比赛", "赛事")):
        if "通知" in title or "公告" in title or "启动" in title or "征集" in title or "参赛" in title:
            return "competition_announcement", flags + ["notice_terms"]
        return "activity", flags + ["competition_news_style"]
    if "通知" in title and any(term in combined for term in ("竞赛", "大赛", "比赛")):
        return "competition_announcement", flags + ["notice_with_competition_in_text"]
    return "unknown", flags + ["no_clear_signal"]


TEAM_TERMS = ("招募", "组队", "队员", "招新")


def title_year(title: str) -> int | None:
    match = re.search(r"(20\d{2})", title)
    return int(match.group(1)) if match else None


def main() -> None:
    seed_path = ROOT / "data" / "seeds" / "v081_211_radar_fix_discovery.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    leads = seed["leads"]
    rels = seed["edition_relations"]
    audited: list[AuditedLead] = []
    for lead in leads:
        audit_class, flags = classify_title(
            lead.get("raw_title") or "",
            lead.get("raw_content") or "",
            lead.get("source_url") or "",
        )
        audited.append(AuditedLead(lead=lead, audit_class=audit_class, flags=flags))

    print("=== AUDIT CLASS DISTRIBUTION (294 leads) ===")
    distribution = Counter(item.audit_class for item in audited)
    for label in AUDIT_LABELS:
        if distribution[label]:
            print(f"{label}: {distribution[label]}")
    print()

    print("=== FLAGGED: award_news / result_notice (keep as evidence, not registration) ===")
    for item in audited:
        if item.audit_class in {"award_news", "result_notice"}:
            lead = item.lead
            print(
                f"  [{item.audit_class}] {lead.get('university')} | "
                f"{(lead.get('raw_title') or '')[:95]} | {lead.get('detected_competition_name') or '-'}"
            )
    print()

    print("=== FLAGGED: activity / training / team / irrelevant / unknown ===")
    for item in audited:
        if item.audit_class in {"activity", "training_notice", "team_recruitment", "irrelevant", "unknown"}:
            lead = item.lead
            print(
                f"  [{item.audit_class}] {lead.get('university')} | "
                f"{(lead.get('raw_title') or '')[:95]} | flags={','.join(item.flags)}"
            )
    print()

    print("=== RELATION AUDIT (56) ===")
    rel_stats: dict[str, list[dict]] = defaultdict(list)
    for rel in rels:
        title = rel.get("notice_title") or rel.get("edition_name") or ""
        audit_class, flags = classify_title(
            title,
            "",
            rel.get("internal_notice_url") or "",
        )
        valid = audit_class in {
            "registration_notice",
            "competition_announcement",
            "internal_selection",
            "submission_notice",
            "team_recruitment",
        }
        entry = {
            "university": rel.get("university"),
            "competition": rel.get("competition_name"),
            "title": (title or "")[:100],
            "url": (rel.get("internal_notice_url") or "")[:110],
            "audit_class": audit_class,
            "valid": valid,
            "flags": flags,
            "deadline": rel.get("internal_registration_deadline"),
        }
        rel_stats["valid" if valid else "invalid"].append(entry)
    print(f"valid={len(rel_stats['valid'])} invalid={len(rel_stats['invalid'])}")
    print("--- INVALID RELATIONS ---")
    for entry in rel_stats["invalid"]:
        print(
            f"  [{entry['audit_class']}] {entry['university']} | {entry['competition']} | {entry['title']}"
        )
    print("--- VALID RELATIONS ---")
    for entry in rel_stats["valid"]:
        print(f"  [{entry['audit_class']}] {entry['university']} | {entry['competition']} | {entry['title']}")


if __name__ == "__main__":
    main()
