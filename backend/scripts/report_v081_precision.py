"""V0.8.2 precision acceptance report generator."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionLead, University, UniversityCompetitionEditionRelation

ACTION_CLASSES = {
    "registration_notice",
    "competition_announcement",
    "competition_notice",
    "submission_notice",
    "internal_selection",
    "team_recruitment",
}


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").lower())


def _longest_common_substring(a: str, b: str) -> int:
    a = _norm(a)
    b = _norm(b)
    if not a or not b:
        return 0
    best = 0
    if len(a) > len(b):
        a, b = b, a
    for start in range(len(a)):
        low, high = 0, len(a) - start
        while low <= high:
            mid = (low + high) // 2
            if a[start : start + mid + 1] in b:
                best = max(best, mid + 1)
                low = mid + 1
            else:
                high = mid - 1
    return best


def main() -> None:
    with SessionLocal() as db:
        universities = {u.name: u for u in db.execute(select(University)).scalars()}
        universities_by_id = {u.id: u for u in db.execute(select(University)).scalars()}
        unis211_names = {u.name for u in universities.values() if u.is_211 and not u.is_985}
        unis211_ids = {u.id for u in universities.values() if u.is_211 and not u.is_985}
        leads = [
            lead
            for lead in db.execute(select(CompetitionLead)).scalars()
            if (lead.metadata_json or {}).get("university") in unis211_names
        ]
        competitions = {c.id: c for c in db.execute(select(Competition)).scalars()}
        rels = [
            rel
            for rel in db.execute(select(UniversityCompetitionEditionRelation)).scalars()
            if rel.university_id in unis211_ids
        ]
        editions = {e.id: e for e in db.execute(select(CompetitionEdition)).scalars()}

    # ---------------- lead audit ---------------- #
    lead_classes = Counter(lead.classification for lead in leads)
    action_leads = [lead for lead in leads if lead.classification in ACTION_CLASSES]
    evidence_leads = [
        lead for lead in leads if lead.classification in {"award_news", "result_notice"}
    ]
    noise_leads = [
        lead for lead in leads
        if lead.classification in {"activity", "training_notice", "irrelevant", "column_page", "unknown"}
    ]
    dup_keys: Counter = Counter()
    for lead in leads:
        key = ((lead.metadata_json or {}).get("university"), _norm(lead.raw_title))
        dup_keys[key] += 1
    duplicate_leads = sum(count - 1 for count in dup_keys.values() if count > 1)

    # ---------------- top school layers ---------------- #
    by_school: dict[str, list] = defaultdict(list)
    for lead in leads:
        by_school[(lead.metadata_json or {}).get("university")].append(lead)
    top_schools = sorted(by_school.items(), key=lambda item: len(item[1]), reverse=True)[:10]
    school_rows = []
    for name, school_leads in top_schools:
        action = sum(1 for l in school_leads if l.classification in ACTION_CLASSES)
        evidence = sum(1 for l in school_leads if l.classification in {"award_news", "result_notice"})
        noise = sum(1 for l in school_leads if l.classification in {"activity", "training_notice", "irrelevant", "column_page", "unknown"})
        school_dups = sum(
            count - 1
            for count in Counter(_norm(l.raw_title) for l in school_leads).values()
            if count > 1
        )
        school_rows.append(
            {
                "university": name,
                "total": len(school_leads),
                "actionable": action,
                "result_award_evidence": evidence,
                "noise": noise,
                "duplicates": school_dups,
                "precision": round(action / len(school_leads), 3),
            }
        )

    # ---------------- match audit ---------------- #
    matched_leads = [lead for lead in leads if lead.matched_competition_id]
    match_rows = []
    suspicious_matches = []
    for lead in matched_leads:
        comp = competitions.get(lead.matched_competition_id)
        if comp is None:
            suspicious_matches.append({"title": lead.raw_title, "matched": None, "reason": "missing_competition"})
            continue
        lcs = _longest_common_substring(lead.raw_title or "", comp.name)
        title = lead.raw_title or ""
        ok = lcs >= 6
        reason = ""
        if "研究生电子设计" in title and "研究生" not in comp.name:
            ok = False
            reason = "graduate_contest_matched_to_undergraduate"
        if "创业计划" in title and "创业计划" not in comp.name and "挑战杯" in title:
            ok = False
            reason = "xiao_tiao_vs_da_tiao"
        if "课外学术科技" in title and "课外学术科技" not in comp.name and "挑战杯" in title:
            ok = False
            reason = "da_tiao_vs_xiao_tiao"
        match_rows.append(
            {
                "title": (title or "")[:120],
                "detected": lead.detected_competition_name,
                "matched": comp.name,
                "lcs": lcs,
                "ok": ok,
                "reason": reason,
            }
        )
        if not ok:
            suspicious_matches.append(match_rows[-1])

    # ---------------- relation & deadline audit ---------------- #
    rel_by_type = Counter(rel.notice_type for rel in rels)
    deadline_rels = [rel for rel in rels if rel.internal_registration_deadline]
    deadline_problems = []
    for rel in deadline_rels:
        edition = editions.get(rel.competition_edition_id)
        problems = []
        if not rel.internal_notice_url:
            problems.append("no_source_url")
        if not rel.notice_title:
            problems.append("no_notice_title")
        if rel.published_at and rel.internal_registration_deadline < rel.published_at:
            problems.append("deadline_before_publish")
        if edition and edition.official_registration_deadline:
            if (
                edition.official_registration_deadline is not None
                and rel.internal_registration_deadline
                and rel.internal_registration_deadline > edition.official_registration_deadline
            ):
                problems.append("internal_after_official(ok_if_college)")
        if problems:
            deadline_problems.append(
                {
                    "university": universities_by_id.get(rel.university_id).name
                    if rel.university_id in universities_by_id
                    else str(rel.university_id),
                    "title": (rel.notice_title or "")[:80],
                    "problems": problems,
                }
            )

    stats = {
        "leads_total": len(leads),
        "lead_classification": dict(lead_classes),
        "actionable_leads": len(action_leads),
        "result_award_evidence_leads": len(evidence_leads),
        "noise_leads": len(noise_leads),
        "duplicate_leads": duplicate_leads,
        "matched_leads": len(matched_leads),
        "suspicious_matches": len(suspicious_matches),
        "relation_count_211": len(rels),
        "relation_notice_types": dict(rel_by_type),
        "deadline_relation_count": len(deadline_rels),
        "deadline_problem_count": len(deadline_problems),
    }
    root = ROOT / "data" / "reports"
    (root / "v081_precision_report.json").write_text(
        json.dumps(
            {
                "stats": stats,
                "top_schools": school_rows,
                "suspicious_matches": suspicious_matches,
                "deadline_problems": deadline_problems,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("top schools:")
    for row in school_rows:
        print(" ", row["university"], row["total"], "action", row["actionable"], "evidence", row["result_award_evidence"], "noise", row["noise"], "dup", row["duplicates"])
    print("suspicious matches:", len(suspicious_matches))
    for item in suspicious_matches[:20]:
        print("  !", (item.get("title") or "")[:90], "->", item.get("matched"), item.get("reason"))
    print("deadline problems:", len(deadline_problems))
    for item in deadline_problems[:10]:
        print("  !", item.get("university"), (item.get("title") or "")[:80], item.get("problems"))


if __name__ == "__main__":
    main()
