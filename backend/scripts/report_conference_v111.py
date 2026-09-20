"""Academic Conference V1.1.1 quality report (JSON + Markdown).

Reads data/v02.sqlite (development database) and writes:
    data/reports/conference_v111_quality_report.json
    data/reports/conference_v111_quality_report.md

Run after the V1.1.1 seed import and the full pytest run:
    python scripts/report_conference_v111.py --pytest-passed N --pytest-total M
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
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
    ConferenceDiscoveryCandidate,
    ConferenceEdition,
    ConferenceOrganization,
    ConferenceSeries,
    ConferenceSource,
    SchoolConference,
)
from app.services.conference_authority_service import (  # noqa: E402
    ACTIONABLE_DEADLINE_FIELDS,
    AUDIENCE_VALUES,
    CONFERENCE_DISCIPLINES,
    STUDENT_OPPORTUNITY_TAGS,
    STUDENT_VALUE_TAGS,
    edition_actionable_status,
    edition_has_actionable_official_info,
    recognition_summary,
    student_opportunity_tags,
)


ROOT = PROJECT_ROOT
TODAY = date(2026, 9, 6)
V1_1_1_SERIES_BASE = 157
V1_1_1_EDITIONS_BASE = 83


def _semantic_list(value: Any) -> list[str]:
    """DB JSON columns may store the literal JSON ``null``; treat it as empty."""
    if not value or value == "null":
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return list(value or [])


def _json_payload(value: Any) -> dict | None:
    if not value or value == "null":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value or None


def _recognition_rows(series_rows: list) -> list[dict]:
    rows: list[dict] = []
    for series in series_rows:
        for rec in recognition_summary(series.external_classifications):
            rec = {**rec, "series_id": series.id, "series_name": series.name}
            rows.append(rec)
    return rows


def _normalized_token(value: str | None) -> str:
    return re.sub(r"[\s\-/_.'’]+", "", str(value or "").casefold())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-passed", type=int, default=0)
    parser.add_argument("--pytest-total", type=int, default=0)
    args = parser.parse_args()

    with SessionLocal() as db:
        series_rows = list(db.execute(select(ConferenceSeries)).scalars())
        edition_rows = list(db.execute(select(ConferenceEdition)).scalars())
        source_rows = list(db.execute(select(ConferenceSource)).scalars())
        candidate_rows = list(db.execute(select(ConferenceDiscoveryCandidate)).scalars())
        school_rows = list(db.execute(select(SchoolConference)).scalars())
        org_link_count = db.scalar(select(func.count()).select_from(ConferenceOrganization)) or 0

    series_count = len(series_rows)
    edition_count = len(edition_rows)
    series_by_id = {row.id: row for row in series_rows}

    discipline_series: Counter[str] = Counter(row.discipline for row in series_rows)
    discipline_editions: Counter[str] = Counter()
    for e in edition_rows:
        series = series_by_id.get(e.conference_series_id)
        discipline_editions[series.discipline if series else "unknown"] += 1
    discipline_report = {
        code: {
            **CONFERENCE_DISCIPLINES[code],
            "series_count": discipline_series.get(code, 0),
            "edition_count": discipline_editions.get(code, 0),
        }
        for code in CONFERENCE_DISCIPLINES
        if discipline_series.get(code, 0) or discipline_editions.get(code, 0)
    }

    series_authority = Counter(row.authority_status for row in series_rows)
    edition_authority = Counter(row.authority_status for row in edition_rows)
    source_level = Counter(row.authority_level for row in source_rows)
    candidate_status = Counter(row.status for row in candidate_rows)
    rejection_reasons = Counter(
        row.rejection_reason for row in candidate_rows if row.rejection_reason
    )
    relation_types = Counter(row.relation_type for row in school_rows)

    recognition_rows = _recognition_rows(series_rows)
    recognition_with_url = sum(1 for rec in recognition_rows if rec.get("source_url"))
    recognition_with_evidence = sum(
        1 for rec in recognition_rows if rec.get("source_url") or rec.get("evidence")
    )
    recognition_records = len(recognition_rows)
    series_with_recognition = sum(1 for row in series_rows if row.external_classifications)

    # ---- Student Value / Student Opportunity coverage --------------------
    series_with_student_tags = sum(
        1 for row in series_rows if _semantic_list(row.student_value_tags)
    )
    editions_with_opportunity: list[ConferenceEdition] = []
    for e in edition_rows:
        tags = _semantic_list(e.student_value_tags)
        if tags or _json_payload(e.participation_details) or _json_payload(e.paper_details):
            editions_with_opportunity.append(e)
    series_with_opportunity = {
        e.conference_series_id for e in editions_with_opportunity
    }
    edition_tag_counter: Counter[str] = Counter()
    edition_opportunity_tag_counter: Counter[str] = Counter()
    for e in edition_rows:
        for tag in _semantic_list(e.student_value_tags):
            edition_tag_counter[tag] += 1
        for tag in student_opportunity_tags(_semantic_list(e.student_value_tags)):
            edition_opportunity_tag_counter[tag] += 1
    series_tag_counter: Counter[str] = Counter()
    for row in series_rows:
        for tag in _semantic_list(row.student_value_tags):
            series_tag_counter[tag] += 1

    # ---- deadline / field coverage ---------------------------------------
    deadline_fields = (
        "abstract_deadline",
        "paper_deadline",
        "poster_deadline",
        "workshop_deadline",
        "notification_date",
        "camera_ready_deadline",
        "registration_deadline",
    )
    field_null_stats: dict[str, dict[str, int]] = {}
    for field in deadline_fields:
        missing = sum(1 for e in edition_rows if getattr(e, field) is None)
        field_null_stats[field] = {
            "editions_total": edition_count,
            "null_count": missing,
            "filled_count": edition_count - missing,
            "null_ratio": round(missing / edition_count, 4) if edition_count else 0,
        }
    for field in ("registration_url", "call_for_papers_url", "edition_official_url"):
        missing = sum(1 for e in edition_rows if not getattr(e, field))
        field_null_stats[field] = {
            "editions_total": edition_count,
            "null_count": missing,
            "filled_count": edition_count - missing,
        }
    field_null_stats["student_value_tags"] = {
        "editions_total": edition_count,
        "empty_count": sum(1 for e in edition_rows if not _semantic_list(e.student_value_tags)),
        "filled_count": sum(
            1 for e in edition_rows if _semantic_list(e.student_value_tags)
        ),
    }
    field_null_stats["participation_details"] = {
        "editions_total": edition_count,
        "null_count": sum(1 for e in edition_rows if _json_payload(e.participation_details) is None),
        "filled_count": sum(1 for e in edition_rows if _json_payload(e.participation_details) is not None),
    }
    field_null_stats["paper_details"] = {
        "editions_total": edition_count,
        "null_count": sum(1 for e in edition_rows if _json_payload(e.paper_details) is None),
        "filled_count": sum(1 for e in edition_rows if _json_payload(e.paper_details) is not None),
    }
    unknown_status_count = sum(
        1 for e in edition_rows if (e.edition_status or "unknown") in {"unknown", ""}
    )

    editions_with_paper_deadline = sum(
        1 for e in edition_rows if e.paper_deadline is not None
    )
    editions_with_poster = sum(
        1 for e in edition_rows if e.poster_deadline is not None or "poster" in _semantic_list(e.student_value_tags)
    )
    editions_with_student_track = sum(
        1 for e in edition_rows if student_opportunity_tags(_semantic_list(e.student_value_tags))
    )
    editions_with_registration_deadline = sum(
        1 for e in edition_rows if e.registration_deadline is not None
    )
    editions_with_registration = sum(
        1 for e in edition_rows if e.registration_deadline is not None or e.registration_url
    )

    # ---- 2026 actionable -------------------------------------------------
    actionable_editions: list[dict[str, Any]] = []
    for e in edition_rows:
        status = edition_actionable_status(e, today=TODAY)
        if status is None:
            continue
        series = series_by_id.get(e.conference_series_id)
        actionable_editions.append(
            {
                "edition_id": e.id,
                "series_id": e.conference_series_id,
                "series_name": series.name if series else None,
                "edition_name": e.edition_name,
                "status": status,
                "deadlines": {
                    field: (
                        getattr(e, field).date().isoformat()
                        if getattr(e, field) is not None
                        else None
                    )
                    for field in ACTIONABLE_DEADLINE_FIELDS
                },
                "opportunity_tags": student_opportunity_tags(
                    _semantic_list(e.student_value_tags)
                ),
            }
        )
    actionable_status = Counter(item["status"] for item in actionable_editions)
    actionable_series = {
        item["series_id"]: item["status"] for item in actionable_editions
    }

    # ---- audits ----------------------------------------------------------
    duplicates: list[dict] = []
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in series_rows:
        tokens = {
            _normalized_token(row.name),
            _normalized_token(row.english_name),
            _normalized_token(row.short_name),
        }
        tokens.update(_normalized_token(a) for a in (row.aliases or []))
        for token in tokens:
            if len(token) >= 6:
                buckets[token].append(row.id)
    for token, ids in buckets.items():
        unique = sorted(set(ids))
        if len(unique) > 1:
            duplicates.append(
                {
                    "token": token,
                    "series_ids": unique,
                    "names": [next(r.name for r in series_rows if r.id == i) for i in unique],
                }
            )
    missing_recognition_evidence = []
    for row in series_rows:
        for rec in row.external_classifications or []:
            if not (rec.get("source_url") or rec.get("evidence")):
                missing_recognition_evidence.append(
                    {"series_id": row.id, "name": row.name}
                )

    wrong_city_reviewed = [
        {
            "item": "SC26",
            "finding": "官网 Attend 模板 bug，导航站日期不可信",
            "action": "Edition 只记 Chicago/McCormick Place；日期保持 NULL（V1.1.1 未改判）",
        },
        {
            "item": "BEI/部分国际学会官网",
            "finding": "beaweb.org、cmstudies.org、ire.org 等对自动访问受限",
            "action": "日期以官方会议页/官方站内检索片段为准，notes 标注核对方式；不采第三方目录",
        },
        {
            "item": "FIMS 2026",
            "finding": "部分转发材料误写 9 月",
            "action": "以 fims.org 官方新闻（2026-04-16）的 11/24-27 Santiago 为准",
        },
        {
            "item": "AEJMC 2026",
            "finding": "division 页投稿日期不一（部分 7/15）",
            "action": "Edition 采用 AEJMC 年会总页 4/1 paper deadline，notes 说明差异",
        },
    ]

    fixed_items = [
        "CCF 2022 分级证据回填：为缺 source_url/evidence 的 recognition 行补 CCF 官方目录公告 URL 与 evidence，标记 legacy；36/36 条 recognition 现均带证据（PRCV 保留 pending_evidence）",
        "新增 v111_series.py：49 个新 Series，全部为官方学会/会议站核实的新闻传播（15）、体育科学（13）、教育（11）、数据科学（10）",
        "新增 editions_v111.py：49 个真实 Edition，均带 S/A 官网来源与会期；4 个 Edition 写入官方学生事实（ECC poster & mentoring、EASM student/PhD seminar、ECER ERC、IEEE BigData Undergraduate & REU Consortium）",
        "org_catalog.py：新增约 45 个国际学会/组委会组织（总数 151），全部 Series 组织引用在目录内",
        "builder 新增 recognition evidence 校验、primary/secondary discipline 校验、SchoolConference 证据校验",
        "conference_authority_service.py：新增 student opportunity tags、actionable 判定与 Edition 日期状态计算（open/upcoming/closed/unknown）",
        "只读 API 扩展：Series/Edition 支持 primary_discipline、has_submission、has_student_track、has_poster、has_registration、actionable 过滤，不改变默认返回",
        "新增 test_conference_v111.py：10 项行为测试全部通过",
    ]

    remaining_risks = [
        "少量官网对自动访问受限（BEA/SCMS/IRE/ECSS 等），日期经官方站内检索片段核对并已写入 source notes，未升级为‘全页直读’的 fully_verified",
        "SC26 会期仍因官网模板问题保持 NULL；第 14 届全国体育科学大会等既有差异维持 notes 隔离",
        "Edition 学生机会字段仍偏少：多数 2026 Edition 官方页未写明面向学生的 deadline/学生分轨，按要求保持 NULL/unknown",
        "student_value_tags 语义补全需要逐 Edition 官方页再采集；Series 级无标签（防止无证据传播）",
        "数据库 JSON 列在种子导入时会写入字面量 'null'（SQLAlchemy JSON 行为），报告按语义空值统计；后续可统一清理为 SQL NULL（不改 schema）",
    ]

    report: dict[str, Any] = {
        "stage": "Academic Conference V1.1.1（数据债务清理 + 学科再平衡 + Edition 学生机会补全）",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": "data/v02.sqlite",
        "reference_date": TODAY.isoformat(),
        "pytest": {"passed": args.pytest_passed, "total": args.pytest_total},
        "stats": {
            "1_series_total": series_count,
            "1_series_added_in_v111": series_count - V1_1_1_SERIES_BASE,
            "2_editions_total": edition_count,
            "2_editions_added_in_v111": edition_count - V1_1_1_EDITIONS_BASE,
            "3_series_by_discipline": discipline_report,
            "4_editions_by_discipline": {
                code: discipline_report[code]["edition_count"]
                for code in discipline_report
            },
            "5_source_quality": {
                "S": source_level.get("S", 0),
                "A": source_level.get("A", 0),
                "B": source_level.get("B", 0),
                "C": source_level.get("C", 0),
                "total": len(source_rows),
            },
            "6_verification": {
                "series_authority_status": dict(sorted(series_authority.items())),
                "edition_authority_status": dict(sorted(edition_authority.items())),
                "verified_official": series_authority.get("verified_official", 0)
                + edition_authority.get("verified_official", 0),
                "authority_confirmed": series_authority.get("authority_confirmed", 0)
                + edition_authority.get("authority_confirmed", 0),
                "pending_or_unverified": series_authority.get("pending_verification", 0)
                + series_authority.get("unverified", 0)
                + edition_authority.get("pending_verification", 0)
                + edition_authority.get("unverified", 0),
                "discovery_candidates_by_status": dict(sorted(candidate_status.items())),
                "rejected_reasons": dict(sorted(rejection_reasons.items())),
            },
            "7_recognition": {
                "recognition_records": recognition_records,
                "series_with_recognition": series_with_recognition,
                "by_system_level": dict(
                    sorted(
                        Counter(
                            f"{rec['system']}-{rec.get('level') or '未分级'}"
                            for rec in recognition_rows
                        ).items()
                    )
                ),
            },
            "8_recognition_evidence": {
                "records_with_direct_source_url": recognition_with_url,
                "records_with_evidence": recognition_with_evidence,
                "direct_source_url_ratio": round(
                    recognition_with_url / recognition_records, 4
                )
                if recognition_records
                else 0,
                "evidence_ratio": round(
                    recognition_with_evidence / recognition_records, 4
                )
                if recognition_records
                else 0,
            },
            "9_student_value_series_coverage": {
                "series_total": series_count,
                "series_with_student_value_tags": series_with_student_tags,
                "series_covering_student_opportunity_editions": len(
                    series_with_opportunity
                ),
                "coverage_ratio": round(
                    (series_with_student_tags + len(series_with_opportunity))
                    / series_count,
                    4,
                )
                if series_count
                else 0,
                "series_by_tag": dict(sorted(series_tag_counter.items())),
            },
            "10_student_opportunity_edition_coverage": {
                "editions_total": edition_count,
                "editions_with_student_opportunity": len(editions_with_opportunity),
                "coverage_ratio": round(
                    len(editions_with_opportunity) / edition_count, 4
                )
                if edition_count
                else 0,
                "edition_by_opportunity_tag": dict(
                    sorted(edition_opportunity_tag_counter.items())
                ),
                "edition_by_any_tag": dict(sorted(edition_tag_counter.items())),
                "controlled_vocabulary": list(STUDENT_VALUE_TAGS),
            },
            "11_editions_with_paper_deadline": editions_with_paper_deadline,
            "12_editions_with_poster": editions_with_poster,
            "13_editions_with_student_track": editions_with_student_track,
            "14_editions_with_registration_deadline": editions_with_registration_deadline,
            "15_school_conferences": {
                "total": len(school_rows),
                "by_relation_type": dict(sorted(relation_types.items())),
                "new_in_v111": 0,
                "note": "V1.1.1 未新增 SchoolConference：ICDM 2026 等虽可判断高校承办，但无独立校方通知，不冒然建关系。",
            },
            "16_discovery_candidates": {
                "total": len(candidate_rows),
                "by_status": dict(sorted(candidate_status.items())),
                "rejection_reasons": dict(sorted(rejection_reasons.items())),
                "note": "第三方目录/商业平台只进发现池；rejected 必须带受控 reason。",
            },
            "17_null_unknown_field_stats": {
                **field_null_stats,
                "edition_status_unknown_or_empty": unknown_status_count,
                "indexing_claim_status_unknown": sum(
                    1
                    for e in edition_rows
                    if (e.indexing_claim_status or "unknown") in {"unknown", None, ""}
                ),
            },
            "2026_actionable": {
                "definition": (
                    "存在真实 2026 Edition，且具备 paper_deadline/poster_deadline/"
                    "registration_deadline/workshop_deadline 或官方学生机会标签中的至少一项；"
                    "open=官方截止日期仍未来；upcoming=无未来截止但会期未结束；"
                    "closed=会期已结束；unknown=有官方信息但无可用日期。状态由 2026-09-06 计算，不预测。"
                ),
                "reference_date": TODAY.isoformat(),
                "actionable_editions_total": len(actionable_editions),
                "actionable_series_total": len(actionable_series),
                "by_status": dict(sorted(actionable_status.items())),
                "editions": actionable_editions,
            },
            "coverage": {
                "series_with_edition": len({e.conference_series_id for e in edition_rows}),
                "series_without_edition": series_count
                - len({e.conference_series_id for e in edition_rows}),
                "editions_with_registration": editions_with_registration,
                "editions_with_cfp_url": sum(
                    1 for e in edition_rows if e.call_for_papers_url
                ),
                "organization_links": org_link_count,
                "series_with_recognition": series_with_recognition,
            },
        },
        "quality_audit": {
            "duplicate_series_tokens": len(duplicates),
            "duplicate_details": duplicates[:15],
            "recognition_missing_evidence": len(missing_recognition_evidence),
            "wrong_city_reviewed": wrong_city_reviewed,
            "school_relations_without_dedicated_notice": [
                {
                    "note": "NDBC 2025（吉林大学）、中国力学大会 2025（国防科技大学）沿用 Edition 的 S/A 来源作证据，不重复建 notice_url。"
                }
            ],
        },
        "fixed": fixed_items,
        "remaining_risks": remaining_risks,
        "files_modified": [
            "backend/scripts/conference_v1_seeds/org_catalog.py（新增约 45 个组织）",
            "backend/scripts/conference_v1_seeds/v111_series.py（新增 49 Series）",
            "backend/scripts/conference_v1_seeds/editions_v111.py（新增 49 Editions）",
            "backend/scripts/build_conference_v1_seeds.py（接入 V1.1.1 + 校验）",
            "backend/app/services/conference_authority_service.py（actionable/student opportunity 规则）",
            "backend/app/services/conference_service.py（只读过滤）",
            "backend/app/api/routes/conferences.py（只读过滤参数）",
            "backend/tests/test_conference_v111.py（10 项新测试）",
            "backend/scripts/report_conference_v111.py",
            "data/seeds/conference_v1/*.json（重新生成）",
            "data/reports/conference_v111_quality_report.{md,json}",
        ],
        "v12_recommendation": {
            "suggested": True,
            "scope": [
                "按 CCF 官方目录逐会议行核对 recognition（legacy -> fully_verified）",
                "官网恢复后可逐条回补 BEA/SCMS/IRE/ECSS 等 Edition 的深层官方页与日期",
                "为已核实的高校承办 Edition（如 ICDM 2026 东北大学）补充校方通知后建 SchoolConference",
                "继续为 2026/2027 Edition 采集官方学生 deadline/student registration/volunteer/travel grant 证据",
                "清理 JSON 列的 'null' 字面量（不改 schema）",
            ],
            "blockers": [
                "不因 KPI 灌入无官网证据的会议/Edition；未核验的日期与学生机会保持 NULL/unknown。",
            ],
        },
    }

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "conference_v111_quality_report.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path = out_dir / "conference_v111_quality_report.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


def _render_markdown(report: dict) -> str:
    stats = report["stats"]
    lines: list[str] = []
    lines.append("# Academic Conference V1.1.1 质量报告")
    lines.append("")
    lines.append(f"- 参考日期：{report['reference_date']}（日期状态由真实官方日期计算，不预测）")
    lines.append(f"- pytest：{report['pytest']['passed']}/{report['pytest']['total']} 通过")
    lines.append("")

    lines.append("## 一、总体数量")
    lines.append("")
    lines.append(f"- ConferenceSeries：{stats['1_series_total']}（V1.1.1 新增 {stats['1_series_added_in_v111']}）")
    lines.append(f"- ConferenceEdition：{stats['2_editions_total']}（V1.1.1 新增 {stats['2_editions_added_in_v111']}）")
    lines.append(f"- SchoolConference：{stats['15_school_conferences']['total']}")
    lines.append(f"- DiscoveryCandidate：{stats['16_discovery_candidates']['total']}")
    lines.append("")

    lines.append("## 二、学科分布")
    lines.append("")
    lines.append("| 学科 | Series | Edition |")
    lines.append("| --- | ---: | ---: |")
    for code, item in sorted(stats["3_series_by_discipline"].items()):
        lines.append(
            f"| {item['name_zh']}（{code}） | {item['series_count']} | {item['edition_count']} |"
        )
    lines.append("")

    lines.append("## 三、来源与核验状态")
    lines.append("")
    quality = stats["5_source_quality"]
    lines.append(
        f"- Source：S={quality['S']} / A={quality['A']} / B={quality['B']} / C={quality['C']} / 共 {quality['total']}"
    )
    verification = stats["6_verification"]
    lines.append(
        f"- Series 核验状态：{json.dumps(verification['series_authority_status'], ensure_ascii=False)}"
    )
    lines.append(
        f"- Edition 核验状态：{json.dumps(verification['edition_authority_status'], ensure_ascii=False)}"
    )
    lines.append(
        f"- DiscoveryCandidate 状态：{json.dumps(verification['discovery_candidates_by_status'], ensure_ascii=False)}"
    )
    lines.append("")

    lines.append("## 四、recognition 证据")
    lines.append("")
    rec = stats["7_recognition"]
    evidence = stats["8_recognition_evidence"]
    lines.append(f"- recognition 记录数：{rec['recognition_records']}（涉及 {rec['series_with_recognition']} 个 Series）")
    lines.append(
        f"- 直接 source_url 比例：{evidence['records_with_direct_source_url']}/{rec['recognition_records']}"
        f" = {evidence['direct_source_url_ratio']:.2%}；带 evidence 比例 {evidence['evidence_ratio']:.2%}"
    )
    lines.append("")

    lines.append("## 五、学生价值与学生机会")
    lines.append("")
    sv = stats["9_student_value_series_coverage"]
    so = stats["10_student_opportunity_edition_coverage"]
    lines.append(
        f"- Student Value Series 覆盖率：{sv['series_with_student_value_tags'] + sv['series_covering_student_opportunity_editions']}/{sv['series_total']}"
        f" = {sv['coverage_ratio']:.2%}（Series 级标签 {sv['series_with_student_value_tags']} 个；覆盖学生机会 Edition 的 Series {sv['series_covering_student_opportunity_editions']} 个）"
    )
    lines.append(
        f"- Student Opportunity Edition 覆盖率：{so['editions_with_student_opportunity']}/{so['editions_total']}"
        f" = {so['coverage_ratio']:.2%}"
    )
    lines.append(
        f"- Edition 机会标签分布：{json.dumps(so['edition_by_opportunity_tag'], ensure_ascii=False)}"
    )
    lines.append("")

    lines.append("## 六、Edition 关键字段覆盖")
    lines.append("")
    lines.append(
        f"- paper_deadline：{stats['11_editions_with_paper_deadline']} 个 Edition"
    )
    lines.append(f"- poster：{stats['12_editions_with_poster']} 个 Edition")
    lines.append(f"- student track：{stats['13_editions_with_student_track']} 个 Edition")
    lines.append(
        f"- registration_deadline：{stats['14_editions_with_registration_deadline']} 个 Edition"
    )
    null_stats = stats["17_null_unknown_field_stats"]
    lines.append(
        f"- 全库 NULL/unknown 统计（共 {null_stats['paper_deadline']['editions_total']} 个 Edition）："
    )
    lines.append("")
    lines.append("| 字段 | 空/NULL 数 | 已填数 |")
    lines.append("| --- | ---: | ---: |")
    for field in (
        "paper_deadline",
        "poster_deadline",
        "registration_deadline",
        "registration_url",
        "call_for_papers_url",
        "participation_details",
        "paper_details",
        "student_value_tags",
    ):
        item = null_stats[field]
        label = {"student_value_tags": "student_value_tags(语义空)"}.get(field, field)
        lines.append(f"| {label} | {item.get('null_count', item.get('empty_count', 0))} | {item['filled_count']} |")
    lines.append(
        f"| edition_status unknown/empty | {null_stats['edition_status_unknown_or_empty']} | - |"
    )
    lines.append("")

    lines.append("## 七、2026 可行动会议")
    lines.append("")
    act = stats["2026_actionable"]
    lines.append(f"- 定义：{act['definition']}")
    lines.append(
        f"- actionable 2026 Edition 共 {act['actionable_editions_total']} 个"
        f"（涉及 {act['actionable_series_total']} 个 Series）"
    )
    lines.append(f"- 状态分布：{json.dumps(act['by_status'], ensure_ascii=False)}")
    lines.append("")
    lines.append("| 状态 | Edition 数 |")
    lines.append("| --- | ---: |")
    for status in ("open", "upcoming", "closed", "unknown"):
        lines.append(f"| {status} | {act['by_status'].get(status, 0)} |")
    lines.append("")
    lines.append("### 明细")
    lines.append("")
    lines.append("| Series | Edition | 状态 |")
    lines.append("| --- | --- | --- |")
    for item in sorted(act["editions"], key=lambda x: (x["status"], x["series_name"] or "")):
        lines.append(f"| {item['series_name']} | {item['edition_name']} | {item['status']} |")
    lines.append("")

    lines.append("## 八、修复与遗留")
    lines.append("")
    lines.append("### 本轮修复")
    lines.append("")
    for item in report["fixed"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### 遗留风险")
    lines.append("")
    for item in report["remaining_risks"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 九、V1.2 建议")
    lines.append("")
    lines.append(
        f"- 建议进入 V1.2：{report['v12_recommendation']['suggested']}"
    )
    for item in report["v12_recommendation"]["scope"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
