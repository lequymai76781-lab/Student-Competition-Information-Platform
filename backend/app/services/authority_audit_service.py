"""Read-only authority / integrity audit used by the V1 main-library report."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionSource
from app.services.authority_match_service import strip_year_and_edition


def run_authority_audit(db: Session) -> dict[str, Any]:
    def scalar(sql: str) -> int:
        return int(db.execute(text(sql)).scalar() or 0)

    comp_statuses = dict(
        db.execute(
            text(
                "SELECT verification_status, COUNT(*) FROM competitions "
                "GROUP BY verification_status ORDER BY verification_status"
            )
        ).all()
    )
    edition_statuses = dict(
        db.execute(
            text(
                "SELECT verification_status, COUNT(*) FROM competition_editions "
                "GROUP BY verification_status ORDER BY verification_status"
            )
        ).all()
    )
    source_levels = dict(
        db.execute(
            text(
                "SELECT authority_level, COUNT(*) FROM competition_sources "
                "GROUP BY authority_level ORDER BY authority_level"
            )
        ).all()
    )

    # 1. verified_official without any source
    official_without_source = list(
        db.execute(
            text(
                "SELECT id, name FROM competitions c WHERE verification_status='verified_official' "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id)"
            )
        ).mappings()
    )
    # 2. verified_official supported only by university/college sources
    official_only_university = list(
        db.execute(
            text(
                "SELECT c.id, c.name FROM competitions c "
                "WHERE c.verification_status='verified_official' "
                "AND NOT EXISTS (SELECT 1 FROM competition_sources s "
                "WHERE s.competition_id=c.id AND s.authority_level IN ('S','A') AND s.is_verified=1)"
            )
        ).mappings()
    )
    # 3. school-sourced national deadline fields still present on editions
    school_copied_national_fields = list(
        db.execute(
            text(
                """
                SELECT DISTINCT e.id edition_id, e.competition_id, e.year,
                       e.official_registration_deadline
                FROM competition_editions e
                WHERE e.official_registration_deadline IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM competition_sources s
                    WHERE s.competition_edition_id = e.id
                      AND s.authority_level IN ('S','A') AND s.is_verified=1)
                ORDER BY e.id
                """
            )
        ).mappings()
    )
    # 4. duplicate URLs inside competition_sources
    duplicate_url_rows = list(
        db.execute(
            text(
                "SELECT competition_id, competition_edition_id, source_url, COUNT(*) cnt "
                "FROM competition_sources GROUP BY competition_id, competition_edition_id, source_url "
                "HAVING cnt > 1"
            )
        ).mappings()
    )
    # 5. same URL reused by multiple competitions
    shared_urls = list(
        db.execute(
            text(
                "SELECT source_url, COUNT(DISTINCT competition_id) comp_cnt "
                "FROM competition_sources WHERE competition_id IS NOT NULL "
                "GROUP BY source_url HAVING comp_cnt > 1"
            )
        ).mappings()
    )
    # 6. same normalized competition name (duplicate-entity candidate)
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, list[int]] = {}
    for competition in db.execute(
        select(Competition).where(Competition.is_competition.is_(True))
    ).scalars():
        key = strip_year_and_edition(competition.name)
        if key:
            seen.setdefault(key, []).append(competition.id)
    for key, ids in seen.items():
        if len(ids) > 1:
            duplicates.append({"key": key, "competition_ids": ids})
    # 7. edition year earlier than competition founding year
    year_conflicts = list(
        db.execute(
            text(
                "SELECT e.id edition_id, e.competition_id, e.year, "
                "COALESCE(c.founded_year, c.first_held_year) founding_year "
                "FROM competition_editions e JOIN competitions c ON c.id=e.competition_id "
                "WHERE COALESCE(c.founded_year, c.first_held_year) IS NOT NULL "
                "AND e.year < COALESCE(c.founded_year, c.first_held_year)"
            )
        ).mappings()
    )
    # 8. campus deadline later than national deadline (school_competitions layer)
    campus_after_national = list(
        db.execute(
            text(
                "SELECT sc.id, sc.school_id, sc.competition_id, sc.competition_edition_id, "
                "sc.campus_registration_deadline, e.official_registration_deadline "
                "FROM school_competitions sc "
                "JOIN competition_editions e ON e.id=sc.competition_edition_id "
                "WHERE e.official_registration_deadline IS NOT NULL "
                "AND sc.campus_registration_deadline IS NOT NULL "
                "AND datetime(sc.campus_registration_deadline) "
                "    > datetime(e.official_registration_deadline)"
            )
        ).mappings()
    )
    # 9. orphan school_competitions (missing school/competition or edition mismatch)
    orphan_school_competitions = list(
        db.execute(
            text(
                "SELECT sc.id, sc.school_id, sc.competition_id, sc.competition_edition_id "
                "FROM school_competitions sc "
                "LEFT JOIN competitions c ON c.id = sc.competition_id "
                "LEFT JOIN universities u ON u.id = sc.school_id "
                "WHERE c.id IS NULL OR u.id IS NULL"
            )
        ).mappings()
    )
    edition_competition_mismatch = list(
        db.execute(
            text(
                "SELECT sc.id, sc.school_id, sc.competition_id, sc.competition_edition_id "
                "FROM school_competitions sc "
                "JOIN competition_editions e ON e.id = sc.competition_edition_id "
                "WHERE e.competition_id <> sc.competition_id"
            )
        ).mappings()
    )
    # 10. official deadlines later than contest start on the same edition
    deadline_after_contest = list(
        db.execute(
            text(
                "SELECT id, competition_id, year, official_registration_deadline, competition_start "
                "FROM competition_editions "
                "WHERE official_registration_deadline IS NOT NULL "
                "AND competition_start IS NOT NULL "
                "AND datetime(official_registration_deadline) > datetime(competition_start)"
            )
        ).mappings()
    )
    # 11. entity types that are not competitions
    non_competition_entities = list(
        db.execute(
            text(
                "SELECT id, name, entity_type, is_competition, verification_status "
                "FROM competitions WHERE is_competition=0 OR entity_type NOT IN "
                "('competition','track','series') ORDER BY id"
            )
        ).mappings()
    )
    # 12. source verification/authority sanity: verified S/A rows
    s_competitions = scalar(
        "SELECT COUNT(DISTINCT competition_id) FROM competition_sources "
        "WHERE authority_level='S' AND is_verified=1 AND is_demo=0"
    )
    a_competitions = scalar(
        "SELECT COUNT(DISTINCT competition_id) FROM competition_sources "
        "WHERE authority_level='A' AND is_verified=1 AND is_demo=0"
    )
    university_only = scalar(
        "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
        "(SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id "
        "AND s.authority_level IN ('S','A') AND s.is_verified=1 AND s.is_demo=0) "
        "AND EXISTS (SELECT 1 FROM competition_sources s2 WHERE s2.competition_id=c.id "
        "AND s2.authority_level IN ('B','C') AND s2.is_verified=1 AND s2.is_demo=0)"
    )
    no_source = scalar(
        "SELECT COUNT(*) FROM competitions c WHERE NOT EXISTS "
        "(SELECT 1 FROM competition_sources s WHERE s.competition_id=c.id AND s.is_demo=0)"
    )
    official_multi_url = list(
        db.execute(
            text(
                "SELECT competition_id, COUNT(DISTINCT source_url) urls "
                "FROM competition_sources WHERE authority_level IN ('S','A') "
                "AND is_verified=1 AND is_demo=0 GROUP BY competition_id HAVING urls > 1"
            )
        ).mappings()
    )
    return {
        "competition_verification_statuses": comp_statuses,
        "edition_verification_statuses": edition_statuses,
        "source_authority_levels": source_levels,
        "competitions_with_s_source": s_competitions,
        "competitions_with_a_source": a_competitions,
        "competitions_only_university_college_sources": university_only,
        "competitions_without_any_source": no_source,
        "official_without_source": [dict(r) for r in official_without_source],
        "official_only_university_sources": [dict(r) for r in official_only_university],
        "school_copied_national_field_editions": [
            dict(r) for r in school_copied_national_fields
        ],
        "duplicate_source_rows": [dict(r) for r in duplicate_url_rows],
        "shared_source_urls": [dict(r) for r in shared_urls],
        "duplicate_competition_name_groups": duplicates,
        "edition_year_before_founding": [dict(r) for r in year_conflicts],
        "campus_after_national_deadline": [dict(r) for r in campus_after_national],
        "orphan_school_competitions": [dict(r) for r in orphan_school_competitions],
        "school_competition_edition_mismatch": [dict(r) for r in edition_competition_mismatch],
        "official_deadline_after_contest_start": [dict(r) for r in deadline_after_contest],
        "non_competition_entities": [dict(r) for r in non_competition_entities],
        "multi_sa_official_urls": [dict(r) for r in official_multi_url],
    }


def build_pending_verification_matrix(db: Session) -> list[dict[str, Any]]:
    """Per-competition re-verification matrix for pending entities."""
    rows: list[dict[str, Any]] = []
    competitions = list(
        db.execute(
            select(Competition).where(
                Competition.verification_status == "pending_verification"
            )
        ).scalars()
    )
    for competition in sorted(competitions, key=lambda item: item.id):
        sources = [
            source
            for source in db.execute(
                select(CompetitionSource).where(
                    CompetitionSource.competition_id == competition.id,
                    CompetitionSource.is_demo.is_(False),
                )
            ).scalars()
        ]
        levels = {
            source.authority_level
            for source in sources
            if source.is_verified and source.authority_level
        }
        ministry_hit = any(
            source.source_type in {"government_official_notice", "ministry_official_notice", "ministry"}
            or (source.authority_level == "S" and "教育部" in (source.source_name or ""))
            for source in sources
            if source.is_verified
        )
        association_hit = any(
            (source.authority_level == "A" and source.is_verified)
            or "高等教育学会" in (source.source_name or "")
            for source in sources
        )
        official_site_hit = any(
            source.source_type
            in {"organizer_official", "competition_official_site", "competition_official_website", "official_competition_website"}
            and source.is_verified
            for source in sources
        )
        has_official_website = bool(competition.official_website) or official_site_hit
        if "S" in levels or ministry_hit:
            result_status = "verified_official"
            confidence = 1.0
        elif "A" in levels or association_hit:
            result_status = "authority_confirmed"
            confidence = 0.95
        elif official_site_hit:
            result_status = "official_site_candidate"
            confidence = 0.8
        else:
            result_status = competition.verification_status
            confidence = 0.0
        rows.append(
            {
                "competition_id": competition.id,
                "name": competition.name,
                "current_sources": [
                    {
                        "source_type": source.source_type,
                        "authority_level": source.authority_level,
                        "source_name": source.source_name,
                        "source_url": source.source_url,
                        "is_verified": source.is_verified,
                    }
                    for source in sources
                ],
                "has_official_website": has_official_website,
                "matched_ministry_source": ministry_hit,
                "matched_association_source": association_hit,
                "matched_official_source": official_site_hit,
                "confidence": confidence,
                "result_status": result_status,
            }
        )
    return rows
