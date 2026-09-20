"""V12 core-competition missing-field queue generator (read-mostly).

Scans the frozen core competition set and reports which Competition and
CompetitionEdition fields are still missing, sorted by deficit so the
enrichment batches can be prioritized. Writes:

    data/reports/v12_missing_field_queue.json
    data/reports/v12_missing_field_queue.md

No database rows are changed by this script.
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

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionOrganization,
    CompetitionSource,
)


CORE_STATUSES = ("verified_official", "authority_confirmed", "association_confirmed")

COMPETITION_FIELDS = [
    "official_name",
    "english_name",
    "short_name",
    "aliases",
    "description",
    "official_website",
    "organizer",
    "co_organizers",
    "undertakers",
    "guidance_organizations",
    "first_held_year",
    "target_students",
    "discipline",
    "competition_scope",
    "competition_format",
    "team_requirement",
    "official_registration_url",
]

EDITION_FIELDS = [
    "year",
    "edition_name",
    "registration_start",
    "official_registration_deadline",
    "submission_deadline",
    "preliminary_date",
    "semifinal_date",
    "final_date",
    "result_date",
    "host_location",
    "rules_url",
    "official_notice_url",
    "registration_url",
    "edition_status",
]


def _field_present(competition: Competition, field: str) -> bool:
    if field == "official_name":
        return bool(competition.name)
    if field == "aliases":
        return bool(competition.aliases or competition.former_names)
    if field == "official_registration_url":
        return bool(
            getattr(competition, "official_registration_url", None)
            or any(
                e.official_registration_url or e.official_url
                for e in competition.editions
            )
        )
    if field == "discipline":
        return bool(competition.category or competition.competition_scope)
    if field == "team_requirement":
        return bool(competition.team_type or competition.min_team_size or competition.max_team_size)
    value = getattr(competition, field, None)
    if isinstance(value, (list, dict)):
        return bool(value)
    return value not in (None, "")


def main() -> None:
    out_dir = PROJECT_ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        core = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                    Competition.verification_status.in_(CORE_STATUSES),
                )
            ).scalars()
        )
        core.sort(key=lambda c: c.id)

        org_links = {
            row.competition_id: row
            for row in db.execute(
                select(CompetitionOrganization).where(
                    CompetitionOrganization.competition_id.in_([c.id for c in core])
                )
            ).scalars()
        }
        # build grouped links
        link_groups: dict[int, list[dict]] = {}
        for row in db.execute(
            select(CompetitionOrganization).where(
                CompetitionOrganization.competition_id.in_([c.id for c in core])
            )
        ).scalars():
            link_groups.setdefault(row.competition_id, []).append(
                {
                    "organization_id": row.organization_id,
                    "organization_name": row.organization.name if row.organization else None,
                    "role": row.role,
                    "display_name": row.display_name,
                    "source_url": row.source_url,
                    "is_verified": row.is_verified,
                }
            )

        rows: list[dict] = []
        for competition in core:
            editions = list(competition.editions)
            editions.sort(key=lambda e: e.year, reverse=True)
            source_rows = list(competition.sources)
            missing = [
                field
                for field in COMPETITION_FIELDS
                if not _field_present(competition, field)
            ]
            edition_records = []
            for e in editions:
                edition_records.append(
                    {
                        "edition_id": e.id,
                        "year": e.year,
                        "edition_name": e.edition_name,
                        "edition_status": e.edition_status,
                        "current_status": e.current_status,
                        "registration_start": e.registration_start,
                        "official_registration_deadline": e.official_registration_deadline,
                        "registration_deadline": e.registration_deadline,
                        "submission_deadline": e.submission_deadline,
                        "competition_start": e.competition_start,
                        "competition_end": e.competition_end,
                        "host_location": e.host_location,
                        "official_url": e.official_url,
                        "official_notice_url": e.official_notice_url,
                        "official_registration_url": e.official_registration_url,
                        "rules_url": e.edition_rules_url,
                        "source_url": e.source_url,
                        "verification_status": e.verification_status,
                        "source_count": len(list(e.sources)),
                    }
                )
            recent_years = [e["year"] for e in edition_records if e["year"] >= 2023]
            latest_edition = edition_records[0] if edition_records else None
            rows.append(
                {
                    "competition_id": competition.id,
                    "name": competition.name,
                    "verification_status": competition.verification_status,
                    "fields": {
                        "official_name": competition.name,
                        "english_name": competition.english_name,
                        "short_name": competition.short_name,
                        "former_names": competition.former_names,
                        "aliases_count": len(list(competition.aliases)),
                        "description": competition.description,
                        "description_source_url": competition.description_source_url,
                        "official_website": competition.official_website,
                        "organizer": competition.organizer,
                        "co_organizers": competition.co_organizers,
                        "undertakers": competition.undertakers,
                        "guiding_organizations": competition.guiding_organizations,
                        "founded_year": competition.founded_year,
                        "first_held_year": competition.first_held_year,
                        "target_students": competition.target_students,
                        "category": competition.category,
                        "competition_scope": competition.competition_scope,
                        "competition_format": competition.competition_format,
                        "team_type": competition.team_type,
                        "frequency": competition.frequency,
                    },
                    "missing_fields": missing,
                    "missing_count": len(missing),
                    "organization_links": link_groups.get(competition.id, []),
                    "structured_org_roles": sorted(
                        {
                            link["role"]
                            for link in link_groups.get(competition.id, [])
                        }
                    ),
                    "editions": edition_records,
                    "edition_count": len(edition_records),
                    "recent_2026": any(e["year"] == 2026 for e in edition_records),
                    "recent_2025": any(e["year"] == 2025 for e in edition_records),
                    "recent_2024": any(e["year"] == 2024 for e in edition_records),
                    "recent_2023": any(e["year"] == 2023 for e in edition_records),
                    "latest_edition": latest_edition,
                    "has_2025_plus_official": any(
                        e["year"] >= 2025
                        and (e["official_notice_url"] or e["official_registration_url"])
                        for e in edition_records
                    ),
                    "has_3_recent": all(
                        any(e["year"] == y for e in edition_records)
                        for y in (2024, 2025, 2026)
                    ),
                    "sources": [
                        {
                            "id": s.id,
                            "source_type": s.source_type,
                            "authority_level": s.authority_level,
                            "source_name": s.source_name,
                            "source_url": s.source_url,
                            "is_verified": s.is_verified,
                            "edition_year": (
                                next(
                                    (
                                        e.year
                                        for e in editions
                                        if e.id == s.competition_edition_id
                                    ),
                                    None,
                                )
                            ),
                        }
                        for s in sorted(
                            source_rows,
                            key=lambda s: (s.authority_level or "Z", s.source_url),
                        )
                    ],
                    "sa_verified_sources": sum(
                        1
                        for s in source_rows
                        if s.is_verified and s.authority_level in {"S", "A"}
                    ),
                }
            )

        rows.sort(key=lambda r: (r["missing_count"], r["competition_id"]), reverse=True)
        total = len(rows)

        def pct(predicate) -> float:
            return round(100.0 * sum(1 for r in rows if predicate(r)) / total, 1) if total else 0.0

        summary = {
            "core_competitions": total,
            "has_organizer_pct": pct(
                lambda r: bool(
                    r["fields"]["organizer"]
                    or r["fields"]["co_organizers"]
                    or r["fields"]["undertakers"]
                    or r["fields"]["guiding_organizations"]
                )
            ),
            "has_structured_org_links_pct": pct(lambda r: bool(r["organization_links"])),
            "has_official_website_pct": pct(lambda r: bool(r["fields"]["official_website"])),
            "has_target_students_pct": pct(lambda r: bool(r["fields"]["target_students"])),
            "has_description_pct": pct(lambda r: bool(r["fields"]["description"])),
            "has_structured_edition_pct": pct(lambda r: r["edition_count"] >= 1),
            "has_two_recent_pct": pct(
                lambda r: sum(bool(r[f"recent_{y}"]) for y in (2024, 2025, 2026)) >= 2
            ),
            "has_three_recent_pct": pct(lambda r: r["has_3_recent"]),
            "has_current_edition_info_pct": pct(lambda r: r["has_2025_plus_official"]),
            "missing_counts": dict(Counter(r["missing_count"] for r in rows)),
            "field_missing_frequency": dict(
                Counter(field for r in rows for field in r["missing_fields"])
            ),
        }

        report = {
            "round": "v12 missing-field queue",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "core_statuses": CORE_STATUSES,
            "summary": summary,
            "rows": rows,
        }
        out_json = out_dir / "v12_missing_field_queue.json"
        out_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        lines = [
            "# V12 核心赛事缺失字段队列",
            "",
            f"- 生成时间：{report['generated_at']}",
            f"- 核心赛事数：{total}",
            "",
            "## 汇总指标",
            "",
            "| 指标 | 数值 |",
            "| --- | --- |",
        ]
        for key, value in summary.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")
        lines.append("## 缺失字段频次")
        lines.append("")
        lines.append("| 字段 | 缺失赛事数 |")
        lines.append("| --- | --- |")
        for field, count in sorted(
            summary["field_missing_frequency"].items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| {field} | {count} |")
        lines.append("")
        lines.append("## 逐赛事队列（按缺失数降序）")
        lines.append("")
        for r in rows:
            lines.append(f"### {r['competition_id']} {r['name']}")
            lines.append("")
            lines.append(
                f"- 状态：{r['verification_status']}；缺失 {r['missing_count']} 项："
                + "、".join(r["missing_fields"])
                + "；届次：" + str(r["edition_count"])
            )
        (out_dir / "v12_missing_field_queue.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
