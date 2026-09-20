"""V0.9 repeatable competition data-quality audit.

Checks the semantic invariants introduced by the refactor and writes a
structured JSON report to data/reports/v09_quality_audit_report.json.
Read-only with respect to business data; can be run after every import.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionSource, SchoolCompetition
from app.services.competition_normalization_service import CompetitionNormalizationService


def main() -> None:
    checks: list[dict[str, object]] = []

    def add(rule_id: str, description: str, count: int, detail: list[object], *, status: str | None = None) -> None:
        checks.append(
            {
                "rule_id": rule_id,
                "description": description,
                "status": status or ("pass" if count == 0 else "fail"),
                "count": count,
                "detail": detail[:30],
            }
        )

    with SessionLocal() as db:
        # 1. official label without S/A evidence
        rows = db.execute(
            text(
                "SELECT c.id, c.name FROM competitions c "
                "WHERE c.verification_status = 'verified_official' "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_id = c.id AND s.authority_level IN ('S','A') "
                "AND s.is_verified = 1 AND s.is_demo = 0)"
            )
        ).all()
        add(
            "official_without_national_source",
            "赛事标记 verified_official 但没有 S/A 级已核验来源",
            len(rows),
            [{"id": row[0], "name": row[1]} for row in rows],
        )

        # 2. duplicate normalized competition entities
        normalizer = CompetitionNormalizationService()
        competitions = list(db.execute(select(Competition)).scalars())
        groups: dict[str, list[Competition]] = {}
        for competition in competitions:
            key = normalizer._normalize_text(competition.name)
            groups.setdefault(key, []).append(competition)
        duplicates = [group for group in groups.values() if len(group) > 1]
        add(
            "duplicate_competition_entities",
            "归一化后同名赛事实体超过一个",
            len(duplicates),
            [
                {"ids": [item.id for item in group], "names": [item.name for item in group]}
                for group in duplicates
            ],
        )

        # 3. same source url imported multiple times
        rows = db.execute(
            text(
                "SELECT s.competition_id, c.name, s.source_url, COUNT(*) AS cnt "
                "FROM competition_sources s JOIN competitions c ON c.id = s.competition_id "
                "GROUP BY s.competition_id, s.source_url HAVING cnt > 1 ORDER BY cnt DESC"
            )
        ).all()
        add(
            "duplicate_source_urls",
            "同一来源 URL 被重复导入",
            len(rows),
            [{"competition_id": row[0], "competition": row[1], "url": row[2], "count": row[3]} for row in rows],
        )

        # 4. school-level markers leaked into competition body
        leaked = [
            competition
            for competition in competitions
            if competition.competition_level
            and re.match(r"^(A\+?|B\+?|C|Ⅰ类?|Ⅱ类?|校级|院级)$", str(competition.competition_level).strip())
        ]
        add(
            "school_level_in_competition_body",
            "高校 A/B/Ⅰ/Ⅱ 类等学校级认定写入赛事本体",
            len(leaked),
            [{"id": item.id, "name": item.name, "level": item.competition_level} for item in leaked],
        )

        # 5/13. campus deadline copied into generic national field
        rows = db.execute(
            text(
                "SELECT e.id, e.year, e.registration_deadline, "
                "e.university_registration_deadline, "
                "e.official_registration_deadline FROM competition_editions e "
                "WHERE e.registration_deadline IS NOT NULL "
                "AND e.registration_deadline = e.university_registration_deadline"
            )
        ).all()
        add(
            "campus_deadline_in_generic_national_field",
            "通用报名截止字段仍与校内截止字段相同",
            len(rows),
            [
                {
                    "edition_id": row[0],
                    "year": row[1],
                    "deadline": str(row[2]),
                    "university_deadline": str(row[3]),
                    "official_deadline": str(row[4]),
                }
                for row in rows
            ],
        )

        # 6. orphan school_competition rows
        school_rows = list(db.execute(select(SchoolCompetition)).scalars())
        orphan_rows = [
            row
            for row in school_rows
            if row.notice_url is None
            and (
                not row.provenance
                or (
                    not row.provenance.get("competition_policy_recognition_ids")
                    and not row.provenance.get("university_competition_edition_relation_ids")
                )
            )
        ]
        add(
            "orphan_school_competitions",
            "无任何证据来源的 school_competition 行",
            len(orphan_rows),
            [{"school_id": row.school_id, "competition_id": row.competition_id} for row in orphan_rows],
        )

        # 7. verified official with no source at all
        rows = db.execute(
            text(
                "SELECT c.id, c.name FROM competitions c "
                "WHERE c.verification_status IN ('verified_official','authority_confirmed') "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_id = c.id AND s.is_demo = 0)"
            )
        ).all()
        add(
            "verified_without_source",
            "无任何来源却标记为已核实",
            len(rows),
            [{"id": row[0], "name": row[1]} for row in rows],
        )

        # 8. only school-level sources but verified_official
        rows = db.execute(
            text(
                "SELECT c.id, c.name FROM competitions c "
                "WHERE c.verification_status = 'verified_official' "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_id = c.id AND s.authority_level IN ('S','A') "
                "AND s.is_verified = 1 AND s.is_demo = 0)"
            )
        ).all()
        add(
            "university_source_only_verified_official",
            "只有高校/低权威来源却 verified_official",
            len(rows),
            [{"id": row[0], "name": row[1]} for row in rows],
        )

        # 9. edition earlier than founded year
        rows = db.execute(
            text(
                "SELECT e.id, e.year, c.id, c.name, c.founded_year "
                "FROM competition_editions e JOIN competitions c ON c.id = e.competition_id "
                "WHERE c.founded_year IS NOT NULL AND e.year < c.founded_year"
            )
        ).all()
        add(
            "edition_before_founded_year",
            "赛事届次早于创办年份",
            len(rows),
            [{"edition_id": row[0], "year": row[1], "competition": row[3]} for row in rows],
        )

        # 10. campus deadline later than national deadline
        rows = db.execute(
            text(
                "SELECT e.id, c.name, e.year, e.official_registration_deadline, "
                "e.university_registration_deadline FROM competition_editions e "
                "JOIN competitions c ON c.id = e.competition_id "
                "WHERE e.official_registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline IS NOT NULL "
                "AND e.university_registration_deadline > e.official_registration_deadline"
            )
        ).all()
        add(
            "campus_later_than_national",
            "校内截止晚于全国截止",
            len(rows),
            [
                {
                    "edition_id": row[0],
                    "competition": row[1],
                    "official": str(row[3]),
                    "campus": str(row[4]),
                }
                for row in rows
            ],
        )

        # 11. award/festival/exhibition rows still listed as competitions
        rows = list(
            db.execute(
                text(
                    "SELECT id, name, entity_type FROM competitions "
                    "WHERE is_competition = 1 AND entity_type NOT IN "
                    "('competition','series','track')"
                )
            ).all()
        )
        add(
            "non_competition_entity_in_catalog",
            "奖项/艺术节/展览等仍以正式赛事身份展示",
            len(rows),
            [{"id": row[0], "name": row[1], "entity_type": row[2]} for row in rows],
        )

        # 12. dual track modeling
        track_rows = db.scalar(text("SELECT COUNT(*) FROM competitions WHERE competition_type='track'"))
        track_table_rows = db.scalar(text("SELECT COUNT(*) FROM competition_tracks"))
        add(
            "dual_track_modeling",
            "competitions 内 track 行与 competition_tracks 表并存",
            int(track_rows or 0) + int(track_table_rows or 0),
            [{"competition_track_rows": track_rows, "competition_tracks_rows": track_table_rows}],
            status="warn" if (track_rows and track_table_rows) else "pass",
        )

        # 14. official national deadline without S/A evidence
        rows = db.execute(
            text(
                "SELECT e.id, c.name, e.official_registration_deadline "
                "FROM competition_editions e JOIN competitions c ON c.id = e.competition_id "
                "WHERE e.official_registration_deadline IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_edition_id = e.id AND s.authority_level IN ('S','A') "
                "AND s.is_verified = 1 AND s.is_demo = 0) "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s2 "
                "WHERE s2.competition_id = c.id AND s2.authority_level IN ('S','A') "
                "AND s2.is_verified = 1 AND s2.is_demo = 0)"
            )
        ).all()
        add(
            "national_deadline_without_sa_evidence",
            "全国截止时间存在但该届无 S/A 级来源支撑",
            len(rows),
            [{"edition_id": row[0], "competition": row[1]} for row in rows],
            status="warn" if rows else "pass",
        )

        summary = {
            "pass": sum(1 for item in checks if item["status"] == "pass"),
            "warn": sum(1 for item in checks if item["status"] == "warn"),
            "fail": sum(1 for item in checks if item["status"] == "fail"),
        }
        report = {
            "version": "v0.9",
            "stage": "competition data quality audit",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "checks": checks,
        }
        report_path = PROJECT_ROOT / "data" / "reports" / "v09_quality_audit_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(summary))
        for item in checks:
            print(f"{item['status'].upper():5} {item['rule_id']}: {item['description']} ({item['count']})")


if __name__ == "__main__":
    main()
