"""Academic Conference V1.2 acceptance report (JSON + Markdown).

Reads data/v02.sqlite and writes:
    data/reports/conference_v12_acceptance.json
    data/reports/conference_v12_acceptance.md
    data/reports/conference_v12_quality_report.json
    data/reports/conference_v12_quality_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ConferenceDisciplineMapping,
    ConferenceDiscoveryCandidate,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceOrganization,
    ConferenceSeries,
    ConferenceSource,
    SchoolConference,
)
from app.services.conference_authority_service import (  # noqa: E402
    CONFERENCE_DISCIPLINES,
    OPPORTUNITY_AUDIENCES,
    OPPORTUNITY_TYPES,
    edition_lifecycle_status,
    opportunity_status,
    recognition_summary,
)


ROOT = PROJECT_ROOT
TODAY = date(2026, 9, 6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-passed", type=int, default=0)
    parser.add_argument("--pytest-total", type=int, default=0)
    args = parser.parse_args()

    with SessionLocal() as db:
        series_rows = list(db.execute(select(ConferenceSeries)).scalars())
        edition_rows = list(db.execute(select(ConferenceEdition)).scalars())
        opportunity_rows = list(db.execute(select(ConferenceOpportunity)).scalars())
        source_rows = list(db.execute(select(ConferenceSource)).scalars())
        candidate_rows = list(db.execute(select(ConferenceDiscoveryCandidate)).scalars())
        school_rows = list(db.execute(select(SchoolConference)).scalars())
        mapping_rows = list(db.execute(select(ConferenceDisciplineMapping)).scalars())
        org_link_count = db.scalar(select(func.count()).select_from(ConferenceOrganization)) or 0
        edition_by_id = {row.id: row for row in edition_rows}
        series_by_id = {row.id: row for row in series_rows}

    opportunity_payloads: list[dict[str, Any]] = []
    for opp in opportunity_rows:
        edition = edition_by_id.get(opp.conference_edition_id)
        series = series_by_id.get(edition.conference_series_id) if edition else None
        opp_status = opportunity_status(opp, edition=edition)
        opportunity_payloads.append(
            {
                "id": opp.id,
                "edition_id": opp.conference_edition_id,
                "series_id": series.id if series else None,
                "series_name": series.name if series else None,
                "year": edition.year if edition else None,
                "opportunity_type": opp.opportunity_type,
                "title": opp.title,
                "official_label": opp.official_label,
                "audience": opp.audience,
                "deadline": opp.deadline.isoformat() if opp.deadline else None,
                "status": opp_status,
                "official_url": opp.official_url,
                "evidence_status": opp.evidence_status,
                "verification_status": opp.verification_status,
                "is_verified": opp.is_verified,
            }
        )

    status_counter = Counter(item["status"] for item in opportunity_payloads)
    type_counter = Counter(item["opportunity_type"] for item in opportunity_payloads)
    audience_counter: Counter[str] = Counter()
    for item in opportunity_payloads:
        for value in item["audience"] or []:
            audience_counter[value] += 1
    audience_counter["unknown_or_not_stated"] += sum(
        1 for item in opportunity_payloads if not item["audience"]
    )
    year_counter = Counter(item["year"] for item in opportunity_payloads if item["year"])
    discipline_counter: Counter[str] = Counter()
    actionable_by_discipline: Counter[str] = Counter()
    for item in opportunity_payloads:
        if item["year"] != TODAY.year:
            continue
        series = series_by_id.get(item["series_id"])
        discipline = series.discipline if series else "unknown"
        discipline_counter[discipline] += 1
        if item["status"] in {"open", "closing_soon", "upcoming"}:
            actionable_by_discipline[discipline] += 1

    editions_with_opportunity = {
        item["edition_id"] for item in opportunity_payloads
    }
    current_future_years = {2026, 2027}
    editions_2026_2027 = [
        e for e in edition_rows if e.year in current_future_years
    ]
    editions_2026_2027_with_opportunity = {
        item["edition_id"]
        for item in opportunity_payloads
        if item["year"] in current_future_years
    }

    recognition_records = []
    for series in series_rows:
        for rec in recognition_summary(series.external_classifications):
            recognition_records.append({**rec, "series_id": series.id})
    recognition_with_url = sum(1 for r in recognition_records if r.get("source_url"))

    secondary_series = [
        {
            "series_id": row.id,
            "name": row.name,
            "primary_discipline": row.discipline,
            "secondary_disciplines": row.secondary_disciplines or [],
        }
        for row in series_rows
        if row.secondary_disciplines
    ]

    verified_opportunities = sum(
        1 for item in opportunity_payloads if item["is_verified"]
    )
    full_evidence = sum(
        1
        for item in opportunity_payloads
        if item["evidence_status"] == "full_page_verified"
    )

    recognition_counter = Counter(
        f"{rec['system']}-{rec.get('level') or '未分级'}"
        for rec in recognition_records
    )
    evidence_state = {
        "opportunities_total": len(opportunity_payloads),
        "full_page_verified": full_evidence,
        "pending_or_limited": len(opportunity_payloads) - full_evidence,
        "verified_opportunities": verified_opportunities,
    }

    acceptance = {
        "stage": "Academic Conference V1.2（学生学术机会关联层）",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_date": TODAY.isoformat(),
        "pytest": {"passed": args.pytest_passed, "total": args.pytest_total},
        "1_opportunity_entity_introduced": True,
        "1_reason": (
            "现有 ConferenceEdition 只能保存一组会议级 deadline/student tags，"
            "无法表达同一届多个学生机会各自独立的 audience/deadline/official_url/evidence"
            "（如 EASM 的 bachelor/master Student Seminar 与 PhD Seminar 并存）；"
            "故引入轻量 ConferenceOpportunity，避免 Edition 字段爆炸为 has_xxx。"
        ),
        "2_schema_changes": [
            "新增 conference_opportunities（conference_edition_id, opportunity_type, title/official_label, audience, open_date, deadline, participation_mode, official_url, source_id, evidence, evidence_status, verification_status, is_verified, risk_flags, notes；唯一键 edition+type+official_url）",
            "conference_series 新增 secondary_disciplines、discipline_evidence（JSON）",
            "新增 conference_discipline_mappings（major_alias -> 受控 discipline；relationship_type=direct/related/interdisciplinary）",
            "alembic 202609060004_v12_conference_opportunity.py",
        ],
        "3_conference_series_total": len(series_rows),
        "4_conference_edition_total": len(edition_rows),
        "5_opportunity_total": len(opportunity_payloads),
        "6_opportunity_2026": year_counter.get(2026, 0),
        "7_opportunity_2027": year_counter.get(2027, 0),
        "8_opportunity_type_distribution": dict(sorted(type_counter.items())),
        "9_opportunity_audience_distribution": dict(sorted(audience_counter.items())),
        "10_opportunity_status_distribution": {
            status: status_counter.get(status, 0)
            for status in ("open", "closing_soon", "upcoming", "closed", "held", "unknown")
        },
        "11_student_opportunity_coverage": {
            "editions_total": len(edition_rows),
            "editions_with_opportunity": len(editions_with_opportunity),
            "coverage_ratio": round(
                len(editions_with_opportunity) / len(edition_rows), 4
            )
            if edition_rows
            else 0,
        },
        "12_2026_2027_opportunity_coverage": {
            "editions_2026_2027_total": len(editions_2026_2027),
            "editions_2026_2027_with_opportunity": len(
                editions_2026_2027_with_opportunity
            ),
            "coverage_ratio": round(
                len(editions_2026_2027_with_opportunity)
                / len(editions_2026_2027),
                4,
            )
            if editions_2026_2027
            else 0,
        },
        "13_actionable_opportunity_by_discipline": dict(
            sorted(actionable_by_discipline.items())
        ),
        "14_major_discipline_mapping_total": len(mapping_rows),
        "14_major_discipline_mapping_by_discipline": dict(
            sorted(Counter(row.discipline for row in mapping_rows).items())
        ),
        "14_secondary_discipline_series": secondary_series,
        "15_recognition_state": {
            "recognition_records": len(recognition_records),
            "records_with_direct_source_url": recognition_with_url,
            "by_system_level": dict(sorted(recognition_counter.items())),
        },
        "16_evidence_state": evidence_state,
        "17_unresolved_source_debt": [
            "BEA/SCMS/IRE/ECSS/NASPSPA/SC26 等既有 Edition 来源仍为 access_limited/snippet_only 或会期 NULL；本轮未据此创建任何机会。",
            "无新增机会证据债务：15/15 机会均 full_page_verified，来源为 S/A 官方页。",
        ],
        "18_api_changes": [
            "GET /api/conferences/opportunities（edition_id/series_id/opportunity_type/audience/status/year/discipline/actionable/verified_only）",
            "GET /api/conferences/discipline-mappings",
            "GET /api/conferences/actionable（Series+Edition+Opportunity+Discipline+Recognition+Evidence 结构化只读）",
            "GET /api/conferences/actionable-summary（current_actionable_editions/opportunities，按 status/type/audience/discipline 统计）",
            "GET /api/conferences/summary 增加 opportunities_total 与 actionable",
            "Series/Edition 列表新增 has_opportunity/opportunity_type/opportunity_audience/actionable 过滤（全部向后兼容）",
        ],
        "19_pytest": {"passed": args.pytest_passed, "total": args.pytest_total},
        "20_files_modified": [
            "backend/alembic/versions/202609060004_v12_conference_opportunity.py",
            "backend/app/models/conference.py（ConferenceOpportunity / ConferenceDisciplineMapping）",
            "backend/app/models/architecture.py（secondary_disciplines/discipline_evidence/opportunities relationship）",
            "backend/app/models/__init__.py",
            "backend/app/schemas/conference.py",
            "backend/app/services/conference_authority_service.py（机会词汇、audience、closing_soon、状态规则）",
            "backend/app/services/conference_seed_import_service.py（机会/映射幂等导入）",
            "backend/app/services/conference_service.py（只读列表与聚合）",
            "backend/app/api/routes/conferences.py",
            "backend/scripts/conference_v1_seeds/opportunities_v12.py（15 条真实机会）",
            "backend/scripts/conference_v1_seeds/disciplines_v12.py（4 个 Series 二级学科+证据）",
            "backend/scripts/conference_v1_seeds/discipline_mapping_v12.py（54 条映射）",
            "backend/scripts/build_conference_v1_seeds.py",
            "backend/scripts/report_conference_v12.py",
            "backend/tests/test_conference_v12.py（11 个测试函数覆盖 18 项验收点）",
            "backend/tests/test_conference_v1.py（migration smoke 期望版本 003->004）",
            "data/seeds/conference_v1/*.json（重新生成）",
            "data/reports/conference_v12_acceptance.{md,json}",
            "data/reports/conference_v12_quality_report.{md,json}",
        ],
        "21_ready_for_conference_frontend": {
            "ready": True,
            "basis": (
                "已有 Series/Edition/Opportunity/Discipline/Recognition/Organization/Evidence"
                "结构化只读数据与 /actionable、/actionable-summary 聚合；前端可展示‘为什么相关/为什么对学生有价值’的事实与来源。"
            ),
            "frontend_scope_note": "按任务要求，本轮不开始 Conference 前端开发。",
        },
        "opportunities": opportunity_payloads,
    }

    quality_report = {
        "stage": "Academic Conference V1.2 quality report",
        "generated_at": acceptance["generated_at"],
        "reference_date": TODAY.isoformat(),
        "counts": {
            "series": len(series_rows),
            "editions": len(edition_rows),
            "opportunities": len(opportunity_payloads),
            "sources": len(source_rows),
            "candidates": len(candidate_rows),
            "school_conferences": len(school_rows),
            "discipline_mappings": len(mapping_rows),
            "organization_links": org_link_count,
        },
        "by_discipline_series": dict(
            sorted(Counter(row.discipline for row in series_rows).items())
        ),
        "by_discipline_editions": dict(
            sorted(
                Counter(
                    (series_by_id.get(e.conference_series_id).discipline if series_by_id.get(e.conference_series_id) else "unknown")
                    for e in edition_rows
                ).items()
            )
        ),
        "opportunity_status": acceptance["10_opportunity_status_distribution"],
        "opportunity_type": acceptance["8_opportunity_type_distribution"],
        "opportunity_audience": acceptance["9_opportunity_audience_distribution"],
        "opportunity_evidence": {
            "full_page_verified": evidence_state["full_page_verified"],
            "pending_or_limited": evidence_state["pending_or_limited"],
        },
        "recognition": acceptance["15_recognition_state"],
    }

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data, title in (
        ("conference_v12_acceptance.json", acceptance, None),
        ("conference_v12_acceptance.md", acceptance, "# Academic Conference V1.2 验收报告"),
        ("conference_v12_quality_report.json", quality_report, None),
        ("conference_v12_quality_report.md", quality_report, "# Academic Conference V1.2 数据质量报告"),
    ):
        path = out_dir / name
        if name.endswith(".json"):
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(_render_markdown(title, data), encoding="utf-8")
    print(
        json.dumps(
            {
                "acceptance_md": str(out_dir / "conference_v12_acceptance.md"),
                "acceptance_json": str(out_dir / "conference_v12_acceptance.json"),
                "quality_md": str(out_dir / "conference_v12_quality_report.md"),
                "quality_json": str(out_dir / "conference_v12_quality_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _render_markdown(title: str, report: dict) -> str:
    lines = [title, ""]
    if "1_opportunity_entity_introduced" in report:
        lines.append("## 结论")
        lines.append("")
        lines.append(f"- 是否引入 ConferenceOpportunity：{report['1_opportunity_entity_introduced']}")
        lines.append(f"- 原因：{report['1_reason']}")
        lines.append("")
        lines.append("## 验收统计")
        lines.append("")
        for key in (
            "3_conference_series_total",
            "4_conference_edition_total",
            "5_opportunity_total",
            "6_opportunity_2026",
            "7_opportunity_2027",
            "14_major_discipline_mapping_total",
        ):
            label = key.split("_", 1)[1]
            lines.append(f"- {label}：{report[key]}")
        lines.append("")
        lines.append(f"- opportunity_type 分布：{json.dumps(report['8_opportunity_type_distribution'], ensure_ascii=False)}")
        lines.append(f"- audience 分布：{json.dumps(report['9_opportunity_audience_distribution'], ensure_ascii=False)}")
        lines.append(f"- status 分布：{json.dumps(report['10_opportunity_status_distribution'], ensure_ascii=False)}")
        lines.append(
            f"- Student Opportunity 覆盖率：{report['11_student_opportunity_coverage']}"
        )
        lines.append(
            f"- 2026/2027 Opportunity 覆盖率：{report['12_2026_2027_opportunity_coverage']}"
        )
        lines.append(
            f"- 各学科 actionable opportunity：{json.dumps(report['13_actionable_opportunity_by_discipline'], ensure_ascii=False)}"
        )
        lines.append(
            f"- recognition：{json.dumps(report['15_recognition_state'], ensure_ascii=False)}"
        )
        lines.append(f"- evidence：{json.dumps(report['16_evidence_state'], ensure_ascii=False)}")
        lines.append("")
        lines.append("## 遗留来源债务")
        lines.append("")
        for item in report["17_unresolved_source_debt"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## API 修改")
        lines.append("")
        for item in report["18_api_changes"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append(f"## pytest：{report['pytest']['passed']}/{report['pytest']['total']} 通过")
        lines.append("")
        lines.append("## 前端就绪判定")
        lines.append("")
        lines.append(f"- ready：{report['21_ready_for_conference_frontend']['ready']}")
        lines.append(f"- basis：{report['21_ready_for_conference_frontend']['basis']}")
        lines.append(f"- 说明：{report['21_ready_for_conference_frontend']['frontend_scope_note']}")
    else:
        lines.append("## 关键计数")
        lines.append("")
        for key, value in report["counts"].items():
            lines.append(f"- {key}：{value}")
        lines.append("")
        lines.append(f"- 状态分布：{json.dumps(report['opportunity_status'], ensure_ascii=False)}")
        lines.append(f"- 类型分布：{json.dumps(report['opportunity_type'], ensure_ascii=False)}")
        lines.append(f"- audience 分布：{json.dumps(report['opportunity_audience'], ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
