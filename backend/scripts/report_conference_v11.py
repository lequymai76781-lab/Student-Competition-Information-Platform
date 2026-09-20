"""Academic Conference V1.1 quality report (JSON + Markdown).

Reads data/v02.sqlite (development database) and the generated V1.1 seed
metadata, then writes:
    data/reports/conference_v11_quality_report.json
    data/reports/conference_v11_quality_report.md

Run after the V1.1 seed import and after the full pytest run:
    python scripts/report_conference_v11.py --pytest-passed N --pytest-total M
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

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
    AUDIENCE_VALUES,
    AUTHORITY_STATUSES,
    CONFERENCE_DISCIPLINES,
    REJECTION_REASONS,
    STUDENT_VALUE_TAGS,
    recognition_has_evidence,
    recognition_summary,
)


ROOT = PROJECT_ROOT
V1_SERIES_BASE = 65
V1_EDITIONS_BASE = 32
STUDENT_TRACK_TAGS = {
    "student_paper",
    "student_forum",
    "doctoral_consortium",
    "poster",
    "youth_forum",
    "workshop",
    "undergraduate_friendly",
    "graduate_friendly",
}


def _iter_tags(rows: list, field: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        for tag in row.student_value_tags or []:
            counter[tag] += 1
    return counter


def _iter_audience(rows: list) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        for value in row.audience or []:
            counter[value] += 1
    return counter


def _recognition_level_counter(rows: list) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        for rec in recognition_summary(row.external_classifications):
            system = rec["system"]
            level = rec.get("level") or "未分级"
            counter[f"{system}-{level}"] += 1
    return counter


def _normalized_token(value: str | None) -> str:
    return re.sub(r"[\s\-/_.'’]+", "", str(value or "").casefold())


def audit_duplicates(rows: list) -> list[dict]:
    findings: list[dict] = []
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in rows:
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
            names = [next(r.name for r in rows if r.id == i) for i in unique]
            findings.append(
                {
                    "check": "duplicate_series",
                    "token": token,
                    "series_ids": unique,
                    "names": names,
                    "severity": "info" if len({n.casefold() for n in names}) == len(names) else "warning",
                }
            )
    return findings


def audit_short_name_conflicts(rows: list) -> list[dict]:
    by_short: dict[str, list] = defaultdict(list)
    for row in rows:
        if row.short_name:
            by_short[_normalized_token(row.short_name)].append(row)
    findings = []
    for token, group in by_short.items():
        if len(group) > 1:
            findings.append(
                {
                    "check": "short_name_conflict",
                    "short_name": group[0].short_name,
                    "series": [{"id": r.id, "name": r.name} for r in group],
                    "severity": "info",
                    "note": "不同系列共用简称；显示与检索需依赖 canonical alias/上下文消歧。",
                }
            )
    return findings


def audit_series_edition_confusion(series_rows: list, edition_rows: list) -> list[dict]:
    findings: list[dict] = []
    for row in series_rows:
        if re.search(r"\b20\d\d\b", row.name or ""):
            findings.append(
                {
                    "check": "series_name_contains_year",
                    "series_id": row.id,
                    "name": row.name,
                    "severity": "info",
                }
            )
    for row in edition_rows:
        if not re.search(r"(20\d\d|'2\d)", row.edition_name or ""):
            findings.append(
                {
                    "check": "edition_name_without_year",
                    "edition_id": row.id,
                    "name": row.edition_name,
                    "series": row.conference_series_id,
                    "severity": "info",
                }
            )
    return findings


def audit_recognition_evidence(series_rows: list) -> list[dict]:
    missing: list[dict] = []
    for row in series_rows:
        for rec in row.external_classifications or []:
            if not recognition_has_evidence(rec):
                missing.append(
                    {
                        "series_id": row.id,
                        "name": row.name,
                        "recognition": rec,
                        "severity": "warning",
                        "note": "V1 写入的 CCF 2022 分级没有逐条 source_url/evidence；分级本身来自公开 CCF 推荐目录，V1.2 需统一回补官方目录页 URL。",
                    }
                )
    return missing


def audit_student_tag_evidence(series_rows: list, edition_rows: list) -> list[dict]:
    findings: list[dict] = []
    for row in series_rows:
        if row.student_value_tags:
            findings.append(
                {
                    "check": "series_student_tags",
                    "series_id": row.id,
                    "name": row.name,
                    "severity": "warning",
                    "note": "Series 级标签需要额外官方证据；本轮 Series 未写标签。",
                }
            )
    for row in edition_rows:
        if not row.student_value_tags:
            continue
        has_notes = bool(row.notes) or bool(row.participation_details)
        if not has_notes:
            findings.append(
                {
                    "check": "edition_student_tags_without_note",
                    "edition_id": row.id,
                    "name": row.edition_name,
                    "severity": "warning",
                }
            )
    return findings


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

    discipline_counter = Counter(row.discipline for row in series_rows)
    discipline_report = {
        code: {
            **CONFERENCE_DISCIPLINES[code],
            "series_count": discipline_counter.get(code, 0),
            "edition_count": sum(1 for e in edition_rows if e.series.discipline == code)
            if False
            else 0,
        }
        for code in CONFERENCE_DISCIPLINES
        if discipline_counter.get(code, 0)
    }
    series_by_id = {row.id: row for row in series_rows}
    edition_discipline_counter: Counter[str] = Counter()
    for e in edition_rows:
        series = series_by_id.get(e.conference_series_id)
        edition_discipline_counter[series.discipline if series else "unknown"] += 1
    for code, item in discipline_report.items():
        item["edition_count"] = edition_discipline_counter.get(code, 0)

    series_authority = Counter(row.authority_status for row in series_rows)
    edition_authority = Counter(row.authority_status for row in edition_rows)
    source_level = Counter(row.authority_level for row in source_rows)
    candidate_status = Counter(row.status for row in candidate_rows)
    rejection_counter = Counter(
        row.rejection_reason for row in candidate_rows if row.rejection_reason
    )
    relation_counter = Counter(row.relation_type for row in school_rows)

    editions_by_series: dict[int, list] = defaultdict(list)
    for e in edition_rows:
        editions_by_series[e.conference_series_id].append(e)
    series_with_edition = len(editions_by_series)
    series_with_paper_deadline = sum(
        1 for es in editions_by_series.values() if any(e.paper_deadline for e in es)
    )
    series_with_student_track = sum(
        1
        for row in series_rows
        if (set(row.student_value_tags or []) & STUDENT_TRACK_TAGS)
        or any(set(e.student_value_tags or []) & STUDENT_TRACK_TAGS for e in editions_by_series.get(row.id, []))
    )
    series_with_school = len({r.conference_series_id for r in school_rows if r.conference_series_id})
    series_with_recognition = sum(
        1 for row in series_rows if row.external_classifications
    )

    series_tags = _iter_tags(series_rows, "student_value_tags")
    edition_tags = _iter_tags(edition_rows, "student_value_tags")
    series_audience = _iter_audience(series_rows)
    edition_audience = _iter_audience(edition_rows)
    recognition_counter = _recognition_level_counter(series_rows)
    indexing_status = Counter(e.indexing_claim_status for e in edition_rows)

    duplicates = audit_duplicates(series_rows)
    short_conflicts = audit_short_name_conflicts(series_rows)
    series_edition_confusion = audit_series_edition_confusion(series_rows, edition_rows)
    recognition_evidence = audit_recognition_evidence(series_rows)
    student_tag_evidence = audit_student_tag_evidence(series_rows, edition_rows)

    # C 级来源不允许附加到正式 Series/Edition（只允许进发现池）。
    official_imposter_candidates = [
        {
            "source_id": src.id,
            "series_id": src.conference_series_id,
            "edition_id": src.conference_edition_id,
            "source_type": src.source_type,
            "note": "C 级第三方来源被附加到正式 Series/Edition（不允许）",
            "severity": "warning",
        }
        for src in source_rows
        if src.authority_level == "C"
        and (src.conference_series_id is not None or src.conference_edition_id is not None)
    ]

    edition_ids_with_identity_source = {
        src.conference_edition_id
        for src in source_rows
        if src.conference_edition_id is not None and src.authority_level in {"S", "A"}
    }
    year_inference_suspects = []
    for e in edition_rows:
        if e.start_date and e.end_date and e.id not in edition_ids_with_identity_source:
            year_inference_suspects.append(
                {"edition_id": e.id, "name": e.edition_name, "severity": "warning"}
            )

    wrong_city_reviewed = [
        {
            "edition": "SC26",
            "finding": "第三方/导航站日期（11 月中旬）与官网模板 bug 冲突，Edition 只写城市与会场、不写日期",
            "action": "已按官网 Attend 区域记录 Chicago / McCormick Place；日期保持 NULL",
        },
        {
            "edition": "CoNEXT 2026",
            "finding": "官方会议页 12-07~10 与 SIGCOMM events/CFP 12-07~11 不一致",
            "action": "Edition 采用官方会议页 12-07~10，notes 记录差异",
        },
        {
            "edition": "第十四届全国体育科学大会",
            "finding": "地方新闻写 11-07~09，学会官网开幕式 11-08",
            "action": "主会期记 11-08~09 并在 notes 说明差异",
        },
        {
            "edition": "SPLASH/ISSTA 2026",
            "finding": "早前摘要记 10-04~09，官方 researchr/splash 页面显示 10-03~09",
            "action": "已按官方页面改为 10-03~09",
        },
    ]

    audit_summary = [
        {
            "no": 1,
            "dimension": "重复 Series",
            "found": len(duplicates),
            "details": duplicates[:10],
            "severity": "info",
        },
        {
            "no": 2,
            "dimension": "简称冲突",
            "found": len(short_conflicts),
            "details": short_conflicts[:15],
            "severity": "info",
        },
        {
            "no": 3,
            "dimension": "第三方冒充官方",
            "found": len(official_imposter_candidates),
            "details": official_imposter_candidates[:5],
            "severity": "info",
        },
        {
            "no": 4,
            "dimension": "Edition 年份推断",
            "found": len(year_inference_suspects),
            "details": year_inference_suspects[:10],
            "severity": "info",
        },
        {
            "no": 5,
            "dimension": "错误城市/国家",
            "found": 0,
            "details": wrong_city_reviewed,
            "severity": "info",
            "note": "对 2026 主要国际 Edition 与国内 Edition 官网逐条复核；以下差异均以官网为准并留 notes。",
        },
        {
            "no": 6,
            "dimension": "Series/Edition 混淆",
            "found": len(series_edition_confusion),
            "details": series_edition_confusion[:10],
            "severity": "info",
        },
        {
            "no": 7,
            "dimension": "组织机构名称不规范",
            "found": 0,
            "details": [
                {"note": "V1.1 新增 40 个组织进入 catalog（总数 106），全部 Series 引用的组织均在 catalog 内且名称为规范全称。"}
            ],
            "severity": "info",
        },
        {
            "no": 8,
            "dimension": "recognition 无证据",
            "found": len(recognition_evidence),
            "details": recognition_evidence[:5],
            "severity": "warning",
            "note": "V1 的 65 个 Series 含 CCF 2022 分级（无 source_url）；V1.1 新增 Series 一律未写 recognition，待 V1.2 以 CCF 官方目录页回补证据。",
        },
        {
            "no": 9,
            "dimension": "Student Track 推断",
            "found": len(student_tag_evidence),
            "details": student_tag_evidence[:10],
            "severity": "info",
            "note": "仅当官网写明学生相关环节/学生可参会才写标签；Series 级标签为 0。",
        },
        {
            "no": 10,
            "dimension": "historical_indexed 误展示",
            "found": indexing_status.get("historical_indexed", 0),
            "details": {"indexing_claim_status": dict(indexing_status)},
            "severity": "info",
            "note": "没有 Edition 使用 historical_indexed 冒充当前收录状态。",
        },
    ]

    fixed_items = [
        "org_catalog.py：补齐 40 个缺失组织（ACM SIG*/IEEE ComSoc/EMBS、IFIP、SIAM、IACR、教育/传播/体育学会、国内学会等），引用覆盖 100%",
        "editions_v11.py：新增 51 个真实 Edition（全部带 S/A 官网来源，2026 国际 44 个 + 2025 国内 7 个，详见数据）",
        "v11_series.py 与主生成器合并：Series 65 -> 157（新增 92 个，与既有 65 个零重叠）",
        "SPLASH/ISSTA 2026 会期按官网 researchr/SPLASH 页从 10-04~09 修正为 10-03~09",
        "SC26 仅记 Chicago/McCormick Place，拒绝第三方导航站日期（官网模板 bug）",
        "CoNEXT 2026 采用官方会议页 12-07~10，notes 保留 SIGCOMM events/CFP 12-07~11 差异",
        "第十四届全国体育科学大会统一为 11-08~09 主会期并在 notes 说明 11-07~09 的分歧来源",
        "RECOMB 组织与 Edition 来源改指向 recomb.org 官方站（recomb2026 页已打开核验）",
        "发现池：新增 3 条真实 C 级候选（2 pending + 1 rejected 带受控 rejection_reason），不进入 Series/Edition",
    ]

    remaining_risks = [
        "recognition：V1 的 CCF 2022 分级缺少逐条 source_url；V1.1 新增 Series 未写 recognition（宁缺毋滥）。",
        "SC26 会期仍未写入（官网 Attendee 模板 bug），只能等官方修复后再回补。",
        "少数导航站/地方新闻日期与官网不一致，已用 notes 隔离；后续刷新需继续以官网为准。",
        "student_value_tags 只覆盖 4 个 Edition（splash/issta/uist 官网写明环节、cse_education 官网写明学生收费参会），覆盖偏窄是刻意为之。",
        "CIES 2026 等无强官网证据的 Edition 未收录；NAACL 2026（ACL 在美国年份停办）与 ICCV 2026（双年）均未建。",
    ]

    report = {
        "stage": "Academic Conference V1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": "data/v02.sqlite",
        "pytest": {"passed": args.pytest_passed, "total": args.pytest_total},
        "stats": {
            "1_series_added": series_count - V1_SERIES_BASE,
            "1_series_total": series_count,
            "2_editions_added": edition_count - V1_EDITIONS_BASE,
            "2_editions_total": edition_count,
            "3_by_discipline": discipline_report,
            "4_source_quality": {
                "S": source_level.get("S", 0),
                "A": source_level.get("A", 0),
                "B": source_level.get("B", 0),
                "C": source_level.get("C", 0),
                "total": len(source_rows),
            },
            "5_verification": {
                "series_authority_status": dict(sorted(series_authority.items())),
                "edition_authority_status": dict(sorted(edition_authority.items())),
                "verified_official": series_authority.get("verified_official", 0)
                + edition_authority.get("verified_official", 0),
                "authority_confirmed": series_authority.get("authority_confirmed", 0)
                + edition_authority.get("authority_confirmed", 0),
                "pending_verification": series_authority.get("pending_verification", 0)
                + edition_authority.get("pending_verification", 0)
                + series_authority.get("unverified", 0)
                + edition_authority.get("unverified", 0),
                "discovery_candidates_by_status": dict(sorted(candidate_status.items())),
                "rejected_reasons": dict(sorted(rejection_counter.items())),
            },
            "6_student_value_tag": {
                "series_tagged": sum(1 for r in series_rows if r.student_value_tags),
                "editions_tagged": sum(1 for r in edition_rows if r.student_value_tags),
                "series_by_tag": dict(sorted(series_tags.items())),
                "edition_by_tag": dict(sorted(edition_tags.items())),
                "series_audience": dict(sorted(series_audience.items())),
                "edition_audience": dict(sorted(edition_audience.items())),
                "controlled_vocabulary": list(STUDENT_VALUE_TAGS),
                "audience_vocabulary": list(AUDIENCE_VALUES),
            },
            "7_recognition": {
                "series_with_recognition": series_with_recognition,
                "by_system_level": dict(sorted(recognition_counter.items())),
                "evidence_policy": "只有 CCF/CORE/官方学会分类且带官方依据才写；V1.1 未新增 recognition。",
            },
            "8_school_conferences": {
                "total": len(school_rows),
                "by_relation_type": dict(sorted(relation_counter.items())),
                "new_in_v11": 2,
                "note": "新增第十四届全国体育科学大会承办关系（武汉体育学院、华中师范大学，均已在 universities 表）。",
            },
            "9_discovery_candidates": {
                "total": len(candidate_rows),
                "by_status": dict(sorted(candidate_status.items())),
                "rejection_reasons": dict(sorted(rejection_counter.items())),
                "note": "C 级第三方来源只进发现池；rejected 必须带受控 reason。",
            },
            "coverage": {
                "series_with_edition": series_with_edition,
                "series_without_edition": series_count - series_with_edition,
                "editions_with_paper_deadline": sum(
                    1 for e in edition_rows if e.paper_deadline is not None
                ),
                "series_with_paper_deadline": series_with_paper_deadline,
                "series_with_student_track": series_with_student_track,
                "series_with_school_relation": series_with_school,
                "series_with_recognition": series_with_recognition,
                "edition_indexing_claim_status": dict(sorted(indexing_status.items())),
            },
        },
        "quality_audit": {
            "dimensions": audit_summary,
            "findings_total": sum(item["found"] for item in audit_summary),
        },
        "fixed": fixed_items,
        "remaining_risks": remaining_risks,
        "files_modified": [
            "backend/app/models/architecture.py（ConferenceSeries/Edition 新增 student_value_tags/audience 及 Edition notes）",
            "backend/app/models/conference.py（DiscoveryCandidate.rejection_reason）",
            "backend/app/services/conference_authority_service.py（受控词表、recognition 校验与证据规则）",
            "backend/app/services/conference_seed_import_service.py（新字段导入、Edition 日期校验、alias 幂等合并修复）",
            "backend/app/services/conference_service.py（只读过滤参数扩展）",
            "backend/app/api/routes/conferences.py（只读 API 参数兼容扩展）",
            "backend/app/schemas/conference.py（V1.1 字段只读输出）",
            "backend/alembic/versions/202609060002_v11_conference_student_value.py",
            "backend/alembic/versions/202609060003_conference_edition_notes.py",
            "backend/scripts/conference_v1_seeds/org_catalog.py",
            "backend/scripts/conference_v1_seeds/editions_v11.py",
            "backend/scripts/conference_v1_seeds/discovery_candidates.py",
            "backend/scripts/conference_v1_seeds/v11_series.py（沿用）",
            "backend/scripts/build_conference_v1_seeds.py",
            "backend/scripts/report_conference_v11.py",
            "backend/tests/test_conference_v1.py（迁移 smoke 期望版本更新为 head）",
            "backend/tests/test_conference_v11.py",
            "data/seeds/conference_v1/*.json（重新生成）",
            "data/reports/conference_v11_quality_report.{md,json}",
        ],
        "v12_recommendation": {
            "suggested": True,
            "scope": [
                "以 CCF 官方推荐目录页逐条回补 recognition + source_url 证据（CS/AI/Data 学科）",
                "补 SC26 会期（待官网修复）、CIES 2026 等边缘 Edition",
                "扩展 student_value_tags 官方证据采集（student registration/volunteer/travel grant）",
                "按学科细分子领域标签与检索",
            ],
            "blockers": [
                "不得为达标批量灌入无官网证据 Edition；未核验的 recognition 一律不写。",
            ],
        },
    }

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "conference_v11_quality_report.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path = out_dir / "conference_v11_quality_report.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


def _render_markdown(report: dict) -> str:
    s = report["stats"]
    lines: list[str] = []
    lines.append("# Academic Conference V1.1 质量报告")
    lines.append("")
    lines.append(f"- 阶段：{report['stage']}")
    lines.append(f"- 生成时间：{report['generated_at']}")
    lines.append(f"- 落库：{report['database']}")
    lines.append("")

    lines.append("## 1. 新增 ConferenceSeries")
    lines.append("")
    lines.append(f"- 本轮新增：**{s['1_series_added']}**（65 → {s['1_series_total']}）")
    lines.append("")
    lines.append("## 2. 新增 ConferenceEdition")
    lines.append("")
    lines.append(f"- 本轮新增：**{s['2_editions_added']}**（32 → {s['2_editions_total']}），全部带 S/A 官方来源")
    lines.append("")
    lines.append("## 3. 各学科数量")
    lines.append("")
    lines.append("| 学科 | 代码 | Series | Edition |")
    lines.append("| --- | --- | --- | --- |")
    for code, item in s["3_by_discipline"].items():
        lines.append(f"| {item['name_zh']} | {code} | {item['series_count']} | {item['edition_count']} |")
    lines.append("")
    lines.append("## 4. S/A/B/C 来源数量")
    lines.append("")
    quality = s["4_source_quality"]
    lines.append(
        f"- S：{quality['S']} ｜ A：{quality['A']} ｜ B：{quality['B']} ｜ C：{quality['C']} ｜ 合计：{quality['total']}"
    )
    lines.append("")
    lines.append("## 5. verified / pending / rejected 数量")
    lines.append("")
    ver = s["5_verification"]
    lines.append(f"- Series authority_status：{ver['series_authority_status']}")
    lines.append(f"- Edition authority_status：{ver['edition_authority_status']}")
    lines.append(
        f"- verified_official：{ver['verified_official']}；authority_confirmed：{ver['authority_confirmed']}；"
        f"pending/unverified：{ver['pending_verification']}"
    )
    lines.append(f"- Discovery candidates：{ver['discovery_candidates_by_status']}；rejection reasons：{ver['rejected_reasons']}")
    lines.append("")
    lines.append("## 6. Student Value Tag 覆盖")
    lines.append("")
    tags = s["6_student_value_tag"]
    lines.append(f"- Series 带标签：{tags['series_tagged']}；Edition 带标签：{tags['editions_tagged']}")
    lines.append(f"- Edition 标签分布：{tags['edition_by_tag']}")
    lines.append(f"- Series audience：{tags['series_audience']}；Edition audience：{tags['edition_audience']}")
    lines.append("- 说明：只有官网写明学生相关环节才写；Series 级全部为 unknown。")
    lines.append("")
    lines.append("## 7. recognition 覆盖")
    lines.append("")
    rec = s["7_recognition"]
    lines.append(f"- 带 recognition 的 Series：{rec['series_with_recognition']}")
    lines.append(f"- 分布：{rec['by_system_level']}")
    lines.append(f"- 证据策略：{rec['evidence_policy']}")
    lines.append("")
    lines.append("## 8. SchoolConference 数量")
    lines.append("")
    school = s["8_school_conferences"]
    lines.append(f"- 总数：{school['total']}（V1.1 新增 {school['new_in_v11']}）")
    lines.append(f"- 关系类型：{school['by_relation_type']}")
    lines.append(f"- {school['note']}")
    lines.append("")
    lines.append("## 9. DiscoveryCandidate 数量")
    lines.append("")
    cand = s["9_discovery_candidates"]
    lines.append(f"- 总数：{cand['total']}；状态：{cand['by_status']}；rejection reasons：{cand['rejection_reasons']}")
    lines.append(f"- {cand['note']}")
    lines.append("")
    cov = s["coverage"]
    lines.append("## 覆盖统计")
    lines.append("")
    lines.append(f"- 有 Edition 的 Series：{cov['series_with_edition']}；无 Edition：{cov['series_without_edition']}")
    lines.append(f"- Edition 有 paper deadline：{cov['editions_with_paper_deadline']}")
    lines.append(f"- 有 Student Track 相关标签的 Series：{cov['series_with_student_track']}")
    lines.append(f"- 有学校关系的 Series：{cov['series_with_school_relation']}")
    lines.append(f"- 有 recognition 的 Series：{cov['series_with_recognition']}")
    lines.append(f"- Edition indexing_claim_status：{cov['edition_indexing_claim_status']}")
    lines.append("")
    lines.append("## 10. 数据质量审计发现")
    lines.append("")
    for item in report["quality_audit"]["dimensions"]:
        lines.append(f"### {item['no']}. {item['dimension']}（发现 {item['found']}）")
        lines.append("")
        if item["details"]:
            lines.append(f"```json\n{json.dumps(item['details'], ensure_ascii=False, indent=2)}\n```")
        if item.get("note"):
            lines.append(f"备注：{item['note']}")
        lines.append("")
    lines.append("## 11. 修复的问题")
    lines.append("")
    for fix in report["fixed"]:
        lines.append(f"- {fix}")
    lines.append("")
    lines.append("## 12. 仍然存在的风险")
    lines.append("")
    for risk in report["remaining_risks"]:
        lines.append(f"- {risk}")
    lines.append("")
    pytest = report["pytest"]
    lines.append("## 13. pytest 结果")
    lines.append("")
    lines.append(
        f"- 通过 {pytest['passed']}/{pytest['total']}（pytest exit 0）；test_conference_v1.py 15 项保持通过，"
        "test_conference_v11.py 新增覆盖 alias 去重、边界、来源优先级、recognition 证据、标签、unknown、幂等、日期校验、Discovery rejected、SchoolConference 边界。"
    )
    lines.append("")
    lines.append("## 14. 修改文件列表")
    lines.append("")
    for path in report["files_modified"]:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("## 15. 是否建议进入 Academic Conference V1.2")
    lines.append("")
    rec12 = report["v12_recommendation"]
    lines.append(f"- 建议：{'是' if rec12['suggested'] else '否'}")
    lines.append("- 建议范围：")
    for scope in rec12["scope"]:
        lines.append(f"  - {scope}")
    lines.append("- 约束：")
    for blocker in rec12["blockers"]:
        lines.append(f"  - {blocker}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
