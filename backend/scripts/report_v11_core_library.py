"""V11 core-library completeness & cleanup report generator (read-mostly).

Writes data/reports/v11_core_library_report.json and the acceptance markdown.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import Competition
from app.services.authority_audit_service import run_authority_audit
from app.services.authority_match_service import strip_year_and_edition


PENDING_VERDICTS = {
    6: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实全国赛事（教育部推动），缺S/A来源"},
    13: {"kind": "national_art_competition", "recommend": "pending_verification", "reason": "真实全国舞蹈赛事，缺官方文件证据"},
    15: {"kind": "national_competition", "recommend": "pending_verification", "reason": "科技部系统赛事，缺S级来源"},
    17: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实学科赛事，缺官方来源"},
    18: {"kind": "national_competition", "recommend": "pending_verification", "reason": "体育总局系统赛事，缺S级来源"},
    88: {"kind": "national_festival_like", "recommend": "pending_verification", "reason": "全国性朗诵艺术节，实体性质需官方章程确认"},
    91: {"kind": "provincial", "recommend": "school_confirmed", "reason": "省级教学技能竞赛，非全国核心库"},
    92: {"kind": "provincial", "recommend": "pending_verification", "reason": "省级营销挑战赛，来源仅为高校"},
    93: {"kind": "provincial_award", "recommend": "non_competition_candidate", "reason": "省级舞蹈奖项/比赛，建议进一步确认实体类型"},
    94: {"kind": "provincial", "recommend": "pending_verification", "reason": "省级技能竞赛，来源仅为高校"},
    95: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实国际传播赛事，缺官方来源"},
    96: {"kind": "provincial", "recommend": "pending_verification", "reason": "省级科普讲解，来源仅为高校"},
    97: {"kind": "college_level", "recommend": "school_confirmed", "reason": "学院级技能赛，不属于全国核心库"},
    98: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实国际学科竞赛（COMAP），缺S级来源"},
    102: {"kind": "duplicate", "recommend": "duplicate", "reason": "已并入53（CULSC）"},
    109: {"kind": "series_child", "recommend": "school_confirmed", "reason": "外研社系列子赛项，母赛事已S级；子赛项自身证据不足"},
    124: {"kind": "campus_competition", "recommend": "school_confirmed", "reason": "校级赛事，不应以全国身份展示"},
    126: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实全国模拟法庭竞赛，缺S级来源"},
    127: {"kind": "campus_competition", "recommend": "school_confirmed", "reason": "校级计算机竞赛"},
    128: {"kind": "national_competition", "recommend": "pending_verification", "reason": "真实全国FPGA/嵌入式竞赛，缺S级来源"},
    129: {"kind": "niche_international", "recommend": "pending_verification", "reason": "国际设计赛事，缺官方来源"},
    132: {"kind": "campus_competition", "recommend": "school_confirmed", "reason": "校级智能体大赛"},
    133: {"kind": "campus_competition", "recommend": "school_confirmed", "reason": "校级创新创业年会类赛事"},
    134: {"kind": "national_competition", "recommend": "pending_verification", "reason": "与生命科学竞赛体系相关，需人工确认归属（suspected duplicate）"},
    136: {"kind": "campus_or_brand_competition", "recommend": "school_confirmed", "reason": "校方/品牌案例赛，缺全国官方证据"},
}


def main() -> None:
    binding = json.loads(
        (PROJECT_ROOT / "data" / "reports" / "v10_cahe_directory_binding_report.json").read_text(
            encoding="utf-8"
        )
    )
    detail = binding.get("detail", [])
    by_rank: dict[int, list[dict]] = {}
    for row in detail:
        by_rank.setdefault(row["directory_rank"], []).append(row)
    one_to_one = 0
    series_ranks = set()
    for rank, rows in by_rank.items():
        has_sub = any(r["level"].startswith("sub_item") for r in rows)
        if has_sub:
            series_ranks.add(rank)
        elif len(rows) == 1 and rows[0]["level"] == "top_level":
            one_to_one += 1
    sub_rows = [r for r in detail if r["level"].startswith("sub_item")]

    with SessionLocal() as db:
        statuses = dict(
            db.execute(
                text(
                    "SELECT verification_status, COUNT(*) FROM competitions "
                    "GROUP BY verification_status ORDER BY verification_status"
                )
            ).fetchall()
        )
        no_source = db.execute(
            text(
                "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
                "(SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id)"
            )
        ).scalar()
        core_ids = [
            c.id
            for c in db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                    Competition.verification_status.in_(
                        ("verified_official", "authority_confirmed", "association_confirmed")
                    ),
                )
            ).scalars()
        ]
        rows = list(
            db.execute(
                select(Competition).where(Competition.id.in_(core_ids))
            ).scalars()
        )
        total = len(rows)

        def pct(flag: bool) -> float:
            return round(100.0 * sum(1 for c in rows if flag(c)) / total, 1) if total else 0.0

        completeness = {
            "core_competitions": total,
            "has_organizer_pct": pct(lambda c: bool(c.organizer or c.co_organizers or c.guiding_organizations or c.undertakers)),
            "has_official_website_pct": pct(lambda c: bool(c.official_website)),
            "has_official_source_pct": pct(
                lambda c: any(
                    s.authority_level in {"S", "A"} and s.is_verified for s in c.sources
                )
            ),
            "has_target_students_pct": pct(lambda c: bool(c.target_students)),
            "has_description_pct": pct(lambda c: bool(c.description)),
            "has_structured_edition_pct": pct(lambda c: len(c.editions) >= 1),
            "has_three_recent_editions_pct": pct(lambda c: len(c.editions) >= 3),
            "has_current_2026_official_pct": pct(
                lambda c: any(
                    e.year >= 2025
                    and (e.official_notice_url or e.official_registration_url)
                    for e in c.editions
                )
            ),
        }
        audit = run_authority_audit(db)
        duplicate_groups = []
        seen: dict[str, list[int]] = {}
        for c in db.execute(select(Competition).where(Competition.is_competition.is_(True))).scalars():
            key = strip_year_and_edition(c.name)
            if key:
                seen.setdefault(key, []).append((c.id, c.verification_status))
        for key, items in seen.items():
            if len(items) > 1:
                duplicate_groups.append({"key": key, "items": items})
        name_conflicts = [g for g in duplicate_groups if not any(s == "duplicate" for _, s in g["items"])]

    report = {
        "round": "v11 core-library integrity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directory_84_relations": {
            "directory_total": 84,
            "db_rows_bound": len(detail),
            "one_to_one": one_to_one,
            "series_with_sub_events": sorted(series_ranks),
            "series_with_sub_events_count": len(series_ranks),
            "sub_event_bindings": len(sub_rows),
            "unmatched_not_in_db": binding.get("unmatched", []),
            "manual_review": binding.get("manual_review", []),
            "duplicate_resolved_this_round": [
                {"dup": 102, "keep": 53},
                {"dup": 118, "keep": 121},
            ],
        },
        "statuses": dict(statuses),
        "no_source_count": no_source,
        "completeness": completeness,
        "audit": audit,
        "duplicate_name_groups_still_conflicting": name_conflicts,
        "pending_verdicts": PENDING_VERDICTS,
        "pending_remaining": sum(
            1 for verdict in PENDING_VERDICTS.values() if verdict["recommend"] == "pending_verification"
        ),
    }
    out = PROJECT_ROOT / "data" / "reports" / "v11_core_library_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
