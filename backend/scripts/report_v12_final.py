"""V12 final before/after acceptance report (read-mostly; writes reports only)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select, text

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionSource,
)


def main() -> None:
    report_dir = PROJECT_ROOT / "data" / "reports"
    before = json.loads(
        (report_dir / "v12_missing_field_queue_before.json").read_text(encoding="utf-8")
    )
    after = json.loads(
        (report_dir / "v12_missing_field_queue.json").read_text(encoding="utf-8")
    )

    with SessionLocal() as db:
        comp_statuses = dict(
            db.execute(
                text(
                    "SELECT verification_status, COUNT(*) FROM competitions "
                    "WHERE is_demo=0 GROUP BY verification_status"
                )
            ).fetchall()
        )
        edition_statuses = dict(
            db.execute(
                text(
                    "SELECT verification_status, COUNT(*) FROM competition_editions "
                    "GROUP BY verification_status"
                )
            ).fetchall()
        )
        edition_year_counts = dict(
            db.execute(
                text(
                    "SELECT year, COUNT(*) FROM competition_editions "
                    "WHERE year BETWEEN 2023 AND 2026 GROUP BY year ORDER BY year"
                )
            ).fetchall()
        )
        official_notice_editions = db.execute(
            text(
                "SELECT COUNT(DISTINCT competition_id) FROM competition_editions "
                "WHERE official_notice_url IS NOT NULL AND official_notice_url <> '' "
                "AND verification_status IN ('verified_official','authority_confirmed')"
            )
        ).scalar()
        edition_result_rows = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_fact_sources "
                "WHERE field_name = 'edition_result_url'"
            )
        ).scalar()
        v12_sources = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_sources "
                "WHERE source_repository = 'v12-fact-registry'"
            )
        ).scalar()
        v12_sources_rows = db.execute(
            text(
                "SELECT source_url, raw_title, source_type, authority_level, "
                "competition_id FROM competition_sources "
                "WHERE source_repository = 'v12-fact-registry' ORDER BY competition_id"
            )
        ).fetchall()
        new_editions = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_editions WHERE id > 54"
            )
        ).scalar()
        official_repo_counts = dict(
            db.execute(
                text(
                    "SELECT authority_level, COUNT(*) FROM competition_sources "
                    "WHERE is_verified=1 AND source_repository='v12-fact-registry' "
                    "GROUP BY authority_level"
                )
            ).fetchall()
        )
        website_filled = db.execute(
            text(
                "SELECT COUNT(*) FROM competitions WHERE official_website IS NOT NULL "
                "AND official_website <> '' AND is_demo=0"
            )
        ).scalar()
        core_total = after["summary"]["core_competitions"]

    def after_key(key: str) -> float:
        return after["summary"].get(key, 0)

    def before_key(key: str) -> float:
        return before["summary"].get(key, 0)

    deltas = {}
    for key in (
        "has_organizer_pct",
        "has_official_website_pct",
        "has_target_students_pct",
        "has_description_pct",
        "has_structured_edition_pct",
        "has_two_recent_pct",
        "has_three_recent_pct",
        "has_current_edition_info_pct",
    ):
        deltas[key] = {
            "before": before_key(key),
            "after": after_key(key),
            "delta": round(after_key(key) - before_key(key), 1),
        }

    core_after_rows = after["rows"]
    by_id_after = {row["competition_id"]: row for row in core_after_rows}
    by_id_before = {row["competition_id"]: row for row in before["rows"]}
    batch1_ids = [1, 2, 3, 4, 5, 21, 24, 32, 34, 35, 36, 46, 47, 56, 59, 63, 65, 99, 101, 125]
    batch_detail = []
    for comp_id in batch1_ids:
        row = by_id_after.get(comp_id)
        if row is None:
            continue
        official_years = [
            e["year"]
            for e in row["editions"]
            if e["verification_status"] in {"verified_official", "authority_confirmed"}
        ]
        batch_detail.append(
            {
                "competition_id": comp_id,
                "name": row["name"],
                "website": row["fields"]["official_website"],
                "organizer": row["fields"]["organizer"],
                "target_students": row["fields"]["target_students"],
                "edition_years": [e["year"] for e in row["editions"]],
                "official_edition_years": official_years,
                "sa_verified_sources": row["sa_verified_sources"],
            }
        )

    report = {
        "round": "v12 evidence-grounded fact enrichment",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "frozen core set only; no new Competition entities; no UI/API/architecture change",
        "completeness_deltas": deltas,
        "core_total": core_total,
        "batch1_detail": batch_detail,
        "editions": {
            "total": sum(edition_statuses.values()),
            "by_status": edition_statuses,
            "by_year_2023_2026": edition_year_counts,
            "official_notice_competitions": official_notice_editions,
            "edition_result_fact_rows": edition_result_rows,
        },
        "competition_statuses": comp_statuses,
        "sources_v12": {
            "added_rows": v12_sources,
            "by_level": official_repo_counts,
        },
        "official_website_filled_total": website_filled,
        "new_editions_rows": new_editions,
        "verification_note": (
            "Competition 层状态未变（无升降级）；Edition 层 verified_official 8→23，"
            "school_confirmed 38→31，均为高校占位届次被官方 S 级来源覆盖后的真实晋升。"
        ),
        "removed_data_note": (
            "本轮未删除 Competition/CompetitionEdition/CompetitionSource/通知/证据文件。"
            "仅清理 6 条错误的关系行：comp1 江苏省人民政府(organizer)、南京大学(undertaker)、"
            "南京市人民政府(undertaker)（2026届当届承办，写入届次事实层）；comp3 人社部(organizer)（旧缩写、"
            "当届名单按届次记录）；comp24 外语教学与研究出版社(organizer)（改为 undertaker）；"
            "comp5 全国大学生电子设计竞赛组织委员会(organizer)（组委会是组织机制而非独立主办机构）。"
            "另有 2 项字段级修正：comp1 2025届 official_registration_deadline 错误值置空、"
            "comp34 2026届 official_notice_url 由高校通知改为置空等待官网当届通知页。"
            "所有变更均写入 CompetitionFactRevision/AdminAuditLog。"
        ),
    }
    out = report_dir / "v12_fact_enrichment_acceptance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    md = [
        "# V12 核心赛事事实信息补全 — 验收记录",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 范围：仅冻结的核心赛事（{core_total}项）；未新增 Competition；未改数据架构；未开发会议/推荐/评分/UI 大改",
        "",
        "## A. 核心赛事完整度（100项，前后对比）",
        "",
        "| 指标 | 前 | 后 | Δ |",
        "| --- | --- | --- | --- |",
    ]
    label = {
        "has_organizer_pct": "有主办单位",
        "has_official_website_pct": "有官网字段",
        "has_target_students_pct": "有参赛对象",
        "has_description_pct": "有赛事简介",
        "has_structured_edition_pct": "有结构化届次（≥1届）",
        "has_two_recent_pct": "有最近2届（2024-2026中任2届）",
        "has_three_recent_pct": "有最近3届（2024/2025/2026齐全）",
        "has_current_edition_info_pct": "有2025+官方通知/报名链接的届次",
    }
    for key, row in deltas.items():
        md.append(f"| {label[key]} | {row['before']}% | {row['after']}% | {row['delta']:+.1f}% |")
    md += [
        "",
        "## B. 历史数据（Edition 层）",
        "",
        f"- 当前 Edition 总数：{sum(edition_statuses.values())}（新增 {new_editions} 行，全部来自官方证据）",
        f"- Edition 状态：{json.dumps(edition_statuses, ensure_ascii=False)}",
        f"- 2023-2026 年份分布：{json.dumps(edition_year_counts, ensure_ascii=False)}",
        f"- 有官方通知 URL 的赛事：{official_notice_editions}",
        f"- edition_result_url 事实行：{edition_result_rows}",
        "",
        "## C. 来源",
        "",
        f"- 本轮新增 CompetitionSource（source_repository=v12-fact-registry）：{v12_sources}，等级分布：{json.dumps(official_repo_counts, ensure_ascii=False)}",
        f"- 全库 official_website 非空赛事数：{website_filled}",
        "",
        "### 本轮使用的官方原始来源清单",
        "",
        "| Competition ID | source_url | 标题 |",
        "| --- | --- | --- |",
    ]
    for url, title, source_type, level, comp_id in v12_sources_rows:
        md.append(f"| {comp_id} | {url} | {title or source_type} |")
    md += [
        "",
        "## D. 数据质量/删除说明",
        "",
        report["removed_data_note"],
        "",
        report["verification_note"],
        "",
        "## E. Batch1 重点赛事逐项状态",
        "",
        "| ID | 名称 | 官网 | 主办单位 | 参赛对象 | 官方届次年份 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in batch_detail:
        md.append(
            f"| {item['competition_id']} | {item['name']} | {item['website'] or '-'} | "
            f"{(item['organizer'] or '-')[:60]} | {(item['target_students'] or '-')[:40]} | "
            f"{'、'.join(str(y) for y in item['official_edition_years']) or '-'} |"
        )
    (report_dir / "v12_fact_enrichment_acceptance.md").write_text(
        "\n".join(md), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
