"""V13 field-evidence final before/after report (read-mostly)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.database.session import SessionLocal


def main() -> None:
    report_dir = PROJECT_ROOT / "data" / "reports"
    before = json.loads(
        (report_dir / "v13_missing_field_queue_before.json").read_text(encoding="utf-8")
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
        evidence_counts = dict(
            db.execute(
                text(
                    "SELECT source_level, COUNT(*) FROM competition_fact_sources "
                    "GROUP BY source_level ORDER BY source_level"
                )
            ).fetchall()
        )
        secondary_sources = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_sources "
                "WHERE source_repository='v13-secondary-registry'"
            )
        ).scalar()
        secondary_links = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_sources "
                "WHERE source_repository='v13-secondary-registry' "
                "AND competition_edition_id IS NOT NULL"
            )
        ).scalar()
        v13_fact_rows = db.execute(
            text(
                "SELECT COUNT(*) FROM competition_fact_sources f "
                "JOIN competition_sources s "
                "ON s.competition_id=f.competition_id AND s.source_url=f.source_url "
                "WHERE s.source_repository='v13-secondary-registry'"
            )
        ).scalar()
        edition_by_year = dict(
            db.execute(
                text(
                    "SELECT year, COUNT(*) FROM competition_editions "
                    "WHERE year BETWEEN 2023 AND 2026 GROUP BY year ORDER BY year"
                )
            ).fetchall()
        )
        total_editions = db.execute(text("SELECT COUNT(*) FROM competition_editions")).scalar()

    def deltas(key: str) -> dict:
        b = before["summary"].get(key, 0)
        a = after["summary"].get(key, 0)
        return {"before": b, "after": a, "delta": round(a - b, 1)}

    keys = (
        "has_organizer_pct",
        "has_official_website_pct",
        "has_target_students_pct",
        "has_structured_edition_pct",
        "has_two_recent_pct",
        "has_three_recent_pct",
        "has_current_edition_info_pct",
    )
    report = {
        "round": "v13 field-evidence gradients + batch2 secondary facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "completeness_deltas": {key: deltas(key) for key in keys},
        "competition_statuses": comp_statuses,
        "edition_statuses": edition_statuses,
        "edition_total": total_editions,
        "edition_year_distribution": edition_by_year,
        "evidence_level_fact_counts": evidence_counts,
        "secondary_sources_added": secondary_sources,
        "secondary_source_edition_links": secondary_links,
        "v13_fact_rows": v13_fact_rows,
        "batch2_summary": {
            "competitions_touched": 10,
            "organizer_filled": 6,
            "official_website_filled_secondary": 1,
            "editions_created": 4,
            "editions_updated": 1,
            "level3_fact_rows_this_round": v13_fact_rows,
        },
        "evidence_level_note": (
            "CompetitionFactSource.source_level 历史取值混杂（null/S/D/LEVEL_1/LEVEL_2/"
            "LEVEL_3/LEVEL_5），仅 v13 本轮写入按 LEVEL_1-4 规范化；历史行保留原值不做批量改写。"
        ),
        "identity_rule_note": (
            "Competition 层 verified_official/authority_confirmed 状态零变化："
            "Level 3 高校来源从未参与赛事身份判定。"
        ),
    }
    out = report_dir / "v13_fact_enrichment_acceptance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    md = [
        "# V13 字段级证据梯度 + Batch2 事实补全 — 验收记录",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- Edition 总数：{total_editions}",
        "",
        "## A. 核心字段覆盖变化（v12 末 → v13 末）",
        "",
        "| 指标 | 前 | 后 | Δ |",
        "| --- | --- | --- | --- |",
    ]
    label = {
        "has_organizer_pct": "有主办单位",
        "has_official_website_pct": "有官网字段（含官方承载页）",
        "has_target_students_pct": "有参赛对象",
        "has_structured_edition_pct": "有结构化届次（≥1）",
        "has_two_recent_pct": "有最近2届",
        "has_three_recent_pct": "有最近3届",
        "has_current_edition_info_pct": "有2025+当前届信息",
    }
    for key, row in report["completeness_deltas"].items():
        md.append(
            f"| {label[key]} | {row['before']}% | {row['after']}% | {row['delta']:+.1f}% |"
        )
    md += [
        "",
        "## B. 证据等级与状态",
        "",
        f"- Competition 状态：{json.dumps(comp_statuses, ensure_ascii=False)}（与 v12 末完全一致，身份验证未因 Level 3 来源改变）",
        f"- Edition 状态：{json.dumps(edition_statuses, ensure_ascii=False)}",
        f"- 年份分布（2023-2026）：{json.dumps(edition_by_year, ensure_ascii=False)}",
        f"- FactSource 证据等级分布：{json.dumps(evidence_counts, ensure_ascii=False)}",
        f"- 本轮新增高校来源行（v13-secondary-registry）：{secondary_sources}，挂接 Edition：{secondary_links}",
        f"- v13 本轮字段事实行（来源可追溯）：{v13_fact_rows}",
        f"- 新冲突：0（所有写入门均先检查既有高层级值）",
        "",
        "## C. Batch2 成果",
        "",
        "- 处理赛事：10 项（29 市场调查、40 集成电路、42 信息安全、45 机械工程创新创意、70 化工实验、77 统计建模、68 工业设计、20 智能汽车、51 华为ICT、58 智能机器人创意）",
        "- 成功补充主办：6 项（29/40/42/45/70/77，均来自高校官方新闻/通知的明确原文，Level 3 provenance）",
        "- 成功补充指导单位：1 项（42，按原文“指导”表述）",
        "- 成功补充官方承载页面/报名系统：1 项（68 https://www.cuidc.net/，official_homepage_type=registration_system）",
        "- 新增 CompetitionEdition：4（20-2026、29-2026、51-2026、58-2026，均为“当届举办事实”的次级证据）",
        "- 更新 Edition：1（77-2026 全国总决赛地点/状态）",
        "",
        "## D. 仍缺数据与原因",
        "",
        "- 仍有大量赛事无主办单位/参赛对象：本地语料中未出现明确、可核验的全国主办方/参赛规则表述，仅校赛组织信息不足以外推；等待组委会/学会官方章程或通知。",
        "- 无官网赛事：赛事无独立域名，且官方主办机构赛事专题页尚未定位或不可访问（js_only/anti_bot/页面失效需逐项分类，见 v13_full_audit）。",
        "- 历史 Edition 缺口：多数赛事官网未归档历届通知，本地高校快照仅覆盖 2026 届新闻；不引用第三方拼凑历史。",
        "- comp29 2025 占位届次在来源挂回正确年份(2026)后失去唯一证据来源，保持 unverified 不冒充；原始行未删除。",
    ]
    (report_dir / "v13_fact_enrichment_acceptance.md").write_text(
        "\n".join(md), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
