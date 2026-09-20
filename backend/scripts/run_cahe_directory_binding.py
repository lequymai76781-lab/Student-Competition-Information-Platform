"""Bind CAHE 2023 official competition directory (A-level evidence).

Evidence chain:
    CAHE official news page (www.cahe.edu.cn/site/content/17082.html)
    -> names rank.moocollege.com as an official publication channel
    -> rank.moocollege.com/newsdetail?id=3243 (《2023…》竞赛目录)
    -> official PDF (oss.moocollege.com .../2023_competition_directory.pdf)

The PDF is image-only; data/raw/authority/cahe2023 contains the OCR text and
the curated structured JSON (2023_competition_directory.json). Only exact /
high-confidence matches are bound automatically; ambiguous rows go to a
review list and no Competition row is created for unmatched directory items.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import CompetitionSource
from app.services.authority_match_service import AuthorityMatchService
from app.services.fact_intelligence_service import FactIntelligenceService


DIRECTORY_JSON = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "authority"
    / "cahe2023"
    / "2023_competition_directory.json"
)
PDF_URL = "https://oss.moocollege.com/unknow/webFile/KN1IBAlY_1725601223721.pdf"
NEWS_PAGE = "https://rank.moocollege.com/newsdetail?id=3243"
ANCHOR_CAHE = "https://www.cahe.edu.cn/site/content/17082.html"

# Directory sub-items that exactly correspond to existing DB child rows.
SUBITEM_COMPETITION_MAP: dict[tuple[int, str], int] = {
    (19, "RoboMaster"): 100,
    (19, "RoboCon"): 111,
    (15, "英语演讲"): 103,
    (15, "英语辩论"): 106,
    (15, "英语写作"): 104,
    (15, "英语阅读"): 105,
    (26, "大数据挑战赛"): 115,
    (26, "团体程序设计天梯赛"): 112,
    (26, "移动应用创新赛"): 116,
    (26, "网络技术挑战赛"): 114,
    (26, "人工智能创意赛"): 113,
    (47, "品牌策划竞赛"): 117,
    (47, "国际贸易竞赛"): 119,
    (47, "创新创业竞赛"): 120,
    (47, "文旅与会展创新创业实践竞赛"): 121,
}


def _status_counts(db) -> dict[str, int]:
    rows = db.execute(
        text(
            "SELECT verification_status, COUNT(*) FROM competitions "
            "GROUP BY verification_status"
        )
    ).fetchall()
    return {status: count for status, count in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bind CAHE 2023 directory A-level sources")
    parser.add_argument("--apply", action="store_true", help="write bindings (default dry-run)")
    parser.add_argument(
        "--report-out",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "v10_cahe_directory_binding_report.json",
    )
    args = parser.parse_args()
    dry_run = not args.apply
    directory = json.loads(DIRECTORY_JSON.read_text(encoding="utf-8"))
    matcher = AuthorityMatchService()

    with SessionLocal() as db:
        before = _status_counts(db)
        source_before = db.execute(text("SELECT COUNT(*) FROM competition_sources")).scalar()
        plan: list[dict] = []
        review: list[dict] = []
        unmatched: list[dict] = []
        for item in directory["items"]:
            match = matcher.match(db, item["name"])
            targets: list[tuple[int, str]] = []
            if match.competition is not None and not match.needs_manual_review:
                targets.append((match.competition.id, "top_level"))
            sub_items = item.get("sub_items") or []
            for sub in sub_items:
                comp_id = SUBITEM_COMPETITION_MAP.get((item["rank"], sub))
                if comp_id is not None:
                    targets.append((comp_id, f"sub_item:{sub}"))
            for comp_id, level in targets:
                existing = db.execute(
                    select(CompetitionSource).where(
                        CompetitionSource.competition_id == comp_id,
                        CompetitionSource.source_url == PDF_URL,
                    )
                ).scalars().first()
                plan.append(
                    {
                        "directory_rank": item["rank"],
                        "directory_name": item["name"],
                        "level": level,
                        "competition_id": comp_id,
                        "source_exists": existing is not None,
                    }
                )
            if not targets and match.competition is not None and match.needs_manual_review:
                review.append(
                    {
                        "directory_rank": item["rank"],
                        "directory_name": item["name"],
                        "suggested_competition_id": match.competition.id,
                        "suggested_competition_name": match.competition.name,
                        "confidence": match.confidence,
                        "reason": "中置信匹配，需人工确认是否同一赛事",
                    }
                )
            if match.competition is None:
                unmatched.append(
                    {
                        "directory_rank": item["rank"],
                        "directory_name": item["name"],
                        "reason": "数据库不存在该赛事实体（不自动创建）",
                    }
                )

        added = 0
        for row in plan:
            if row["source_exists"] or dry_run:
                continue
            db.add(
                CompetitionSource(
                    competition_id=row["competition_id"],
                    source_type="higher_education_association",
                    authority_level="A",
                    source_name="《2023全国普通高校大学生竞赛分析报告》竞赛目录",
                    source_url=PDF_URL,
                    source_repository="cahe-2023-directory",
                    source_platform="rank.moocollege.com",
                    published_at=datetime(2024, 3, 22),
                    crawled_at=datetime.now(timezone.utc),
                    retrieved_at=datetime.now(timezone.utc),
                    is_official=True,
                    is_verified=True,
                    credibility_score=90,
                    reliability_tier=2,
                    verification_status="authority_confirmed",
                    raw_title="《2023全国普通高校大学生竞赛分析报告》竞赛目录",
                    metadata_json={
                        "directory_year": 2023,
                        "directory_rank": row["directory_rank"],
                        "directory_name": row["directory_name"],
                        "level": row["level"],
                        "anchor_page_cahe": ANCHOR_CAHE,
                        "news_page": NEWS_PAGE,
                        "extracted_from": "data/raw/authority/cahe2023/2023_competition_directory.json",
                        "issuing_authority": "中国高等教育学会高校竞赛评估与管理体系研究专家工作组",
                    },
                    is_demo=False,
                )
            )
            added += 1
        if not dry_run:
            db.flush()
            service = FactIntelligenceService()
            service.refresh_source_tiers(db)
            service.refresh_verification(db)
            db.commit()
        after = _status_counts(db)
        source_after = db.execute(text("SELECT COUNT(*) FROM competition_sources")).scalar()

    report = {
        "document": directory["document_title"],
        "list_year": directory["list_year"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "directory_total": directory["total_items"],
        "bound_rows_planned": len(plan),
        "source_rows_added": added,
        "source_rows_before": source_before,
        "source_rows_after": source_after,
        "top_level_matches": sum(1 for row in plan if row["level"] == "top_level"),
        "sub_item_matches": sum(1 for row in plan if row["level"].startswith("sub_item")),
        "manual_review": review,
        "unmatched": unmatched,
        "status_before": before,
        "status_after": after,
        "detail": plan,
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
