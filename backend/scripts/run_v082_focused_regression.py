"""Bounded two-school V0.8.2 regression with an explicit title-level truth set.

External search is disabled here so the benchmark measures official entry/feed
discovery deterministically. Search engines remain a production fallback.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import Competition, University
from app.services.university_radar_discovery_service import CrawlBudget, UniversityRadarDiscoveryService


TRUTH = {
    "华中农业大学": (
        "商业精英挑战赛品牌策划竞赛",
        "全国大学生英语竞赛",
        "市场调查与分析大赛",
        "外研社·国才杯",
    ),
    "武汉理工大学": (
        "智能建造创新大赛",
        "研究生人工智能创新大赛",
        "华为软件精英挑战赛",
    ),
}
ACTIONABLE = {"registration_notice", "internal_selection", "submission_notice", "competition_notice", "competition_announcement", "team_recruitment"}
OUT = Path(__file__).resolve().parents[2] / "data" / "reports" / "v082_focused_regression.json"


def normalized(value: str) -> str:
    return "".join(char for char in value.lower().replace("•", "·") if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def hit(title: str, needle: str) -> bool:
    left, right = normalized(title), normalized(needle)
    return right in left or left in right


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", action="append", choices=tuple(TRUTH))
    args = parser.parse_args()
    selected = set(args.names or TRUTH)
    db = SessionLocal()
    service = UniversityRadarDiscoveryService()
    # Keep the official fetch path and filters; remove unstable search-engine
    # channels from the benchmark and cap work to public entries/feed pages.
    service._search_multi = lambda *args, **kwargs: ([], None)  # type: ignore[method-assign]
    service._search_sogou = lambda *args, **kwargs: ([], None)  # type: ignore[method-assign]
    service.budget = CrawlBudget(max_department_entries=12, max_department_feeds=10, max_list_pages_per_department=3, max_department_articles=70, max_candidate_urls=120, max_page_fetches=90, max_known_entry_probes=9, max_internal_search_pages=2)
    try:
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))).scalars())
        matcher = service._build_matcher(db, competitions)
        reverse_names = service._reverse_search_names(db)
        rows = list(db.execute(select(University).where(University.name.in_(selected))).scalars())
        results = []
        for index, university in enumerate(rows):
            result = service._discover_university(
                {"name": university.name, "short_name": university.short_name, "aliases": university.aliases or [], "official_domain": university.official_domain, "official_website": university.official_website},
                f"v082-focused-{index + 1:02d}", matcher, reverse_names, datetime.now(timezone.utc),
            )
            examined = result["report"].get("examined_pages", [])
            page_titles = [row.get("title") or "" for row in examined]
            lead_titles = [row.get("raw_title") or "" for row in result["leads"]]
            expected = TRUTH[university.name]
            page_hits = [name for name in expected if any(hit(title, name) for title in page_titles)]
            candidate_hits = [name for name in expected if any(hit(title, name) for title in lead_titles)]
            true_leads = [row for row in result["leads"] if any(hit(row.get("raw_title") or "", name) for name in expected)]
            false_positive = [row for row in result["leads"] if row not in true_leads]
            results.append({
                "university": university.name,
                "truth": list(expected),
                "page_tp": page_hits,
                "page_fn": [name for name in expected if name not in page_hits],
                "candidate_tp": candidate_hits,
                "candidate_fn": [name for name in expected if name not in candidate_hits],
                "lead_tp": len(candidate_hits),
                "lead_fp": len(false_positive),
                "trace": result["report"],
                "leads": result["leads"],
            })
        truth_total = sum(len(item["truth"]) for item in results)
        page_tp = sum(len(item["page_tp"]) for item in results)
        candidate_tp = sum(len(item["candidate_tp"]) for item in results)
        action_tp = sum(item["lead_tp"] for item in results)
        fp = sum(item["lead_fp"] for item in results)
        payload = {
            "version": "v0.8.2-focused",
            "scope": sorted(selected),
            "metrics": {
                "truth_total": truth_total,
                "page_tp": page_tp,
                "page_fn": truth_total - page_tp,
                "page_recall": round(page_tp / truth_total, 4),
                "candidate_tp": candidate_tp,
                "candidate_fn": truth_total - candidate_tp,
                "candidate_recall": round(candidate_tp / truth_total, 4),
                "lead_tp": action_tp,
                "lead_fp": fp,
                "lead_precision": round(action_tp / (action_tp + fp), 4) if action_tp + fp else None,
            },
            "schools": results,
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    finally:
        service.close()
        db.close()


if __name__ == "__main__":
    main()
