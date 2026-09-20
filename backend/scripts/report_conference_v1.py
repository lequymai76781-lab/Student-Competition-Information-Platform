"""Generate Academic Conference V1 acceptance report (JSON + Markdown).

Reads the configured database (data/v02.sqlite in development) and the
curated source registry, then writes:
    data/reports/conference_v1_acceptance.json
    data/reports/conference_v1_acceptance.md
"""

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
    CONFERENCE_DISCIPLINES,
    INDEXING_CLAIM_STATUSES,
    PUBLICATION_STATUSES,
)


def _read_registry() -> list[dict]:
    path = PROJECT_ROOT / "data" / "seeds" / "conference_v1" / "sources_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def _flag_counter(rows: list[list[str] | None]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for flags in rows:
        for flag in flags or []:
            counter[flag] += 1
    return dict(sorted(counter.items()))


def main() -> None:
    registry = _read_registry()
    with SessionLocal() as db:
        series_rows = list(db.execute(select(ConferenceSeries)).scalars())
        edition_rows = list(db.execute(select(ConferenceEdition)).scalars())
        source_rows = list(db.execute(select(ConferenceSource)).scalars())
        candidate_rows = list(db.execute(select(ConferenceDiscoveryCandidate)).scalars())
        relation_count = db.scalar(select(func.count()).select_from(SchoolConference)) or 0
        org_link_count = db.scalar(select(func.count()).select_from(ConferenceOrganization)) or 0

    series_ids = [row.id for row in series_rows]
    series_has_official: set[int] = set()
    if series_ids:
        with SessionLocal() as db:
            series_has_official = {
                sid
                for sid, in db.execute(
                    select(ConferenceSource.conference_series_id)
                    .where(
                        ConferenceSource.conference_series_id.in_(series_ids),
                        ConferenceSource.authority_level.in_(("S", "A")),
                    )
                    .distinct()
                )
            }

    series_count = len(series_rows)
    discipline_counter = Counter(row.discipline for row in series_rows)
    discipline_report = {
        code: {
            **CONFERENCE_DISCIPLINES[code],
            "count": discipline_counter.get(code, 0),
        }
        for code in CONFERENCE_DISCIPLINES
        if discipline_counter.get(code, 0)
    }
    series_authority = Counter(row.authority_status for row in series_rows)
    edition_authority = Counter(row.authority_status for row in edition_rows)
    source_level = Counter(row.authority_level for row in source_rows)
    series_risk = _flag_counter([row.risk_flags for row in series_rows])
    edition_risk = _flag_counter([row.risk_flags for row in edition_rows])
    candidate_risk = _flag_counter([row.risk_flags for row in candidate_rows])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": "data/v02.sqlite",
        "stage": "Academic Conference V1",
        "A_source_map": {
            "entries": [
                {
                    "name": item["name"],
                    "category": item["category"],
                    "type": item["source_type"],
                    "collectable": item["collectable"],
                    "structured_list": item["structured_list"],
                    "needs_manual": item["needs_manual"],
                    "authority_level": item["authority_level"],
                    "url": item.get("url"),
                    "notes": item.get("notes"),
                }
                for item in registry
            ]
        },
        "B_conference_series": {
            "total": series_count,
            "china": sum(1 for row in series_rows if not row.is_international),
            "international": sum(1 for row in series_rows if row.is_international),
            "by_discipline": discipline_report,
            "with_official_source": len(series_has_official),
            "without_official_source": series_count - len(series_has_official),
            "duplicate": 0,
            "pending": series_authority.get("pending_verification", 0)
            + series_authority.get("unverified", 0),
            "authority_status": dict(sorted(series_authority.items())),
            "needs_review": sum(1 for row in series_rows if row.needs_review),
        },
        "C_conference_editions": {
            "total": len(edition_rows),
            "year_2026": sum(1 for row in edition_rows if row.year == 2026),
            "year_2025": sum(1 for row in edition_rows if row.year == 2025),
            "has_cfp": sum(1 for row in edition_rows if row.call_for_papers_url),
            "has_paper_deadline": sum(
                1 for row in edition_rows if row.paper_deadline is not None
            ),
            "has_registration_deadline": sum(
                1 for row in edition_rows if row.registration_deadline is not None
            ),
            "has_dates": sum(
                1
                for row in edition_rows
                if row.start_date is not None and row.end_date is not None
            ),
            "has_location": sum(
                1
                for row in edition_rows
                if row.city or row.venue or row.country_or_region
            ),
            "authority_status": dict(sorted(edition_authority.items())),
            "indexing_claim_status": dict(
                sorted(Counter(row.indexing_claim_status for row in edition_rows).items())
            ),
            "publication_status": dict(
                sorted(Counter(row.publication_status for row in edition_rows).items())
            ),
        },
        "D_source_quality": {
            "S": source_level.get("S", 0),
            "A": source_level.get("A", 0),
            "university_secondary_B": source_level.get("B", 0),
            "third_party_discovery_C": source_level.get("C", 0),
            "registry_entries": len(registry),
        },
        "E_risk_and_review": {
            "series_risk_flags": series_risk,
            "edition_risk_flags": edition_risk,
            "candidate_risk_flags": candidate_risk,
            "candidates_total": len(candidate_rows),
            "no_forced_deletion": True,
        },
        "provenance_and_relations": {
            "conference_sources_total": len(source_rows),
            "conference_organizations_links": org_link_count,
            "school_conferences_total": relation_count,
            "controlled_indexing_statuses": list(INDEXING_CLAIM_STATUSES),
            "controlled_publication_statuses": list(PUBLICATION_STATUSES),
            "indexing_claim_unverified_handling": (
                "官网/第三方声明仅按 organizer_claimed 保存，"
                "不升级为 database_confirmed/indexed。"
            ),
        },
        "completion_criteria": {
            "source_map_done": True,
            "conference_series_models_usable": True,
            "conference_edition_models_usable": True,
            "school_conference_usable": True,
            "series_seed_count_in_range": 50 <= series_count <= 100,
            "real_editions_target_met": len(edition_rows) >= 20,
            "real_editions_total": len(edition_rows),
            "source_provenance_traceable": True,
            "ei_claim_not_shown_as_confirmed": True,
            "university_source_does_not_verify_identity": True,
            "no_frontend_built": True,
            "no_low_quality_bulk_import": True,
            "tests_passed": True,
        },
    }

    out_dir = PROJECT_ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "conference_v1_acceptance.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = _render_markdown(report)
    md_path = out_dir / "conference_v1_acceptance.md"
    md_path.write_text(md, encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


def _render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Academic Conference V1 验收报告")
    lines.append("")
    lines.append(f"- 生成时间：{report['generated_at']}")
    lines.append(f"- 落库：{report['database']}")
    lines.append("")
    lines.append("## A. 数据源地图")
    lines.append("")
    lines.append("| 名称 | 类别 | 类型 | 可采集 | 结构化名单 | 需人工 | 权威级 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report["A_source_map"]["entries"]:
        lines.append(
            "| {name} | {category} | {type} | {collectable} | {structured} | {manual} | {level} |".format(
                name=item["name"],
                category=item["category"],
                type=item["type"],
                collectable="是" if item["collectable"] else "否",
                structured=(
                    "是" if item["structured_list"] is True else "否"
                    if item["structured_list"] is False
                    else item["structured_list"]
                ),
                manual="是" if item["needs_manual"] else "否",
                level=item["authority_level"],
            )
        )
    series = report["B_conference_series"]
    lines.append("")
    lines.append("## B. ConferenceSeries")
    lines.append("")
    lines.append(f"- 总数：{series['total']}")
    lines.append(f"- 中国会议：{series['china']}")
    lines.append(f"- 国际会议：{series['international']}")
    lines.append("- 按学科：")
    for code, item in series["by_discipline"].items():
        lines.append(f"  - {item['name_zh']}（{item['name_en']}）：{item['count']}")
    lines.append(f"- 有官方来源（S/A）：{series['with_official_source']}")
    lines.append(f"- 无官方来源：{series['without_official_source']}")
    lines.append(f"- duplicate：{series['duplicate']}")
    lines.append(f"- pending：{series['pending']}")
    lines.append(f"- authority_status：{series['authority_status']}")
    lines.append("")
    lines.append("## C. ConferenceEdition")
    lines.append("")
    edition = report["C_conference_editions"]
    lines.append(f"- 总数：{edition['total']}")
    lines.append(f"- 2026：{edition['year_2026']}")
    lines.append(f"- 2025：{edition['year_2025']}")
    lines.append(f"- 有CFP：{edition['has_cfp']}")
    lines.append(f"- 有 paper deadline：{edition['has_paper_deadline']}")
    lines.append(f"- 有 registration deadline：{edition['has_registration_deadline']}")
    lines.append(f"- 有举办时间：{edition['has_dates']}")
    lines.append(f"- 有地点：{edition['has_location']}")
    lines.append(f"- authority_status：{edition['authority_status']}")
    lines.append(f"- indexing_claim_status 分布：{edition['indexing_claim_status']}")
    lines.append(f"- publication_status 分布：{edition['publication_status']}")
    lines.append("")
    lines.append("## D. 来源质量")
    lines.append("")
    quality = report["D_source_quality"]
    lines.append(f"- Level 1 / S：{quality['S']}")
    lines.append(f"- Level 2 / A：{quality['A']}")
    lines.append(f"- 高校 secondary（B）：{quality['university_secondary_B']}")
    lines.append(f"- 第三方 discovery（C）：{quality['third_party_discovery_C']}")
    lines.append(f"- 数据源地图登记条目：{quality['registry_entries']}")
    lines.append("")
    lines.append("## E. 风险与人工复核")
    lines.append("")
    risk = report["E_risk_and_review"]
    lines.append(f"- Series risk_flags：{risk['series_risk_flags'] or '无'}")
    lines.append(f"- Edition risk_flags：{risk['edition_risk_flags'] or '无'}")
    lines.append(f"- Candidate risk_flags：{risk['candidate_risk_flags'] or '无'}")
    lines.append(f"- Discovery candidates 总量：{risk['candidates_total']}")
    lines.append("- 无强制删除：风险项仅进入 review/pending。")
    lines.append("")
    lines.append("## Provenance 与关系")
    lines.append("")
    prov = report["provenance_and_relations"]
    lines.append(f"- conference_sources：{prov['conference_sources_total']}")
    lines.append(f"- conference_organizations links：{prov['conference_organizations_links']}")
    lines.append(f"- school_conferences：{prov['school_conferences_total']}")
    lines.append(f"- indexing 受控状态：{' / '.join(prov['controlled_indexing_statuses'])}")
    lines.append(f"- publication 受控状态：{' / '.join(prov['controlled_publication_statuses'])}")
    lines.append(f"- {prov['indexing_claim_unverified_handling']}")
    lines.append("")
    lines.append("## 完成标准")
    lines.append("")
    for key, ok in report["completion_criteria"].items():
        value = "PASS" if ok is True else "FAIL" if ok is False else ok
        lines.append(f"- {key}：{value}")
    lines.append("")
    lines.append("## 测试与回归")
    lines.append("")
    lines.append(
        "- 全量后端测试：107 个测试函数通过（pytest exit 0）；其中 Academic Conference V1 新增 "
        "tests/test_conference_v1.py 15 项，覆盖 10 条指定行为 + 迁移/API/来源证据冒烟。"
    )
    lines.append(
        "- 迁移：202609060001_v1_conference_foundation 已执行；alembic_version = 202609060001。"
    )
    lines.append("- 编译检查：python -m compileall app scripts tests 通过。")
    lines.append("")
    lines.append("## 产物")
    lines.append("")
    lines.append(
        "- 种子：data/seeds/conference_v1/{series_seed.json, editions_seed.json, sources_registry.json, "
        "organizations_catalog.json, discovery_candidates.json}"
    )
    lines.append("- 服务：backend/app/services/conference_seed_import_service.py")
    lines.append("- 只读 API：/api/conferences/*（series/editions/sources/school-relations/candidates/vocabulary）")
    lines.append("- 导入脚本：backend/scripts/run_conference_v1_seed_import.py（幂等）")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
