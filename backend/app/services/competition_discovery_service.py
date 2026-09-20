from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CompetitionEdition,
    CompetitionLead,
    CompetitionSource,
    University,
    UniversityCompetitionDiscoveryReport,
    UniversityCompetitionEditionRelation,
)

ACTIVE_DISCOVERY_STATUSES = {"completed", "partial", "failed", "blocked"}
ACTIVE_DISCOVERY_STATUSES_081 = {"completed", "completed_with_gaps", "partial", "failed", "blocked"}
ACTION_NOTICE_TYPES = {"registration_notice", "internal_selection", "submission_notice"}


class CompetitionDiscoveryService:
    def coverage_summary(self, db: Session) -> dict:
        progress = self.get_985_progress(db)
        return {
            "universities_985_total": 39,
            "universities_985_seeded": len(progress),
            "scanned_985_count": sum(item["discovery_status"] in ACTIVE_DISCOVERY_STATUSES for item in progress),
            "completed_985_count": sum(item["discovery_status"] == "completed" for item in progress),
            "partial_985_count": sum(item["discovery_status"] == "partial" for item in progress),
            "failed_985_count": sum(item["discovery_status"] == "failed" for item in progress),
            "blocked_985_count": sum(item["discovery_status"] == "blocked" for item in progress),
            "universities_with_leads": sum(item["competition_leads"] > 0 for item in progress),
            "universities_with_matched_competitions": sum(item["matched_competitions"] > 0 for item in progress),
            "universities_with_2026_editions": sum(item["edition_2026_count"] > 0 for item in progress),
            "competition_leads": sum(item["competition_leads"] for item in progress),
            "matched_competitions": sum(item["matched_competitions"] for item in progress),
            "new_competitions": sum(item["new_competitions"] for item in progress),
            "new_editions": sum(item["new_editions"] for item in progress),
            "official_sources": sum(item["official_sources"] for item in progress),
            "university_notice_count": sum(item["university_notice_count"] for item in progress),
            "college_notice_count": sum(item["college_notice_count"] for item in progress),
            "current_registration_count": sum(item["current_registration_count"] for item in progress),
            "edition_2026_count": sum(item["edition_2026_count"] for item in progress),
            "wechat_leads": sum(item["wechat_leads"] for item in progress),
            "source_distribution": self.source_distribution(db),
            "progress": progress,
        }

    def v08_coverage_summary(self, db: Session) -> dict:
        progress_985 = self.get_progress(db, scope="985")
        progress_211 = self.get_progress(db, scope="211_non_985")
        progress = progress_985 + progress_211
        return {
            "universities_985_total": 39,
            "universities_985_seeded": len(progress_985),
            "scanned_985_count": sum(
                item["discovery_status"] in ACTIVE_DISCOVERY_STATUSES_081 for item in progress_985
            ),
            "completed_985_count": sum(item["discovery_status"] == "completed" for item in progress_985),
            "completed_with_gaps_985_count": sum(
                item["discovery_status"] == "completed_with_gaps" for item in progress_985
            ),
            "partial_985_count": sum(item["discovery_status"] == "partial" for item in progress_985),
            "failed_985_count": sum(item["discovery_status"] == "failed" for item in progress_985),
            "blocked_985_count": sum(item["discovery_status"] == "blocked" for item in progress_985),
            "universities_211_non_985_total": 73,
            "universities_211_non_985_seeded": len(progress_211),
            "scanned_211_non_985_count": sum(
                item["discovery_status"] in ACTIVE_DISCOVERY_STATUSES_081 for item in progress_211
            ),
            "completed_211_non_985_count": sum(item["discovery_status"] == "completed" for item in progress_211),
            "completed_with_gaps_211_non_985_count": sum(
                item["discovery_status"] == "completed_with_gaps" for item in progress_211
            ),
            "partial_211_non_985_count": sum(item["discovery_status"] == "partial" for item in progress_211),
            "failed_211_non_985_count": sum(item["discovery_status"] == "failed" for item in progress_211),
            "blocked_211_non_985_count": sum(item["discovery_status"] == "blocked" for item in progress_211),
            **self._aggregate(progress),
            "discovery_methods": self.discovery_method_summary(db),
            "source_distribution": self.source_distribution(db),
            "progress_985": progress_985,
            "progress_211_non_985": progress_211,
            "progress": progress,
        }

    def get_985_progress(self, db: Session) -> list[dict]:
        return self.get_progress(db, scope="985")

    def get_progress(self, db: Session, *, scope: str) -> list[dict]:
        if scope == "985":
            predicate = University.is_985.is_(True)
        elif scope == "211_non_985":
            predicate = University.is_211.is_(True) & University.is_985.is_(False)
        else:
            raise ValueError(f"Unsupported discovery scope: {scope}")
        universities = list(
            db.execute(
                select(University)
                .where(predicate, University.is_demo.is_(False))
                .order_by(University.name.asc())
            )
            .scalars()
            .all()
        )
        leads = list(db.execute(select(CompetitionLead)).scalars())
        lead_by_university: dict[str, list[CompetitionLead]] = {}
        for lead in leads:
            university_name = (lead.metadata_json or {}).get("university")
            if university_name:
                lead_by_university.setdefault(university_name, []).append(lead)

        progress: list[dict] = []
        for university in universities:
            report = db.execute(
                select(UniversityCompetitionDiscoveryReport)
                .where(UniversityCompetitionDiscoveryReport.university_id == university.id)
                .order_by(UniversityCompetitionDiscoveryReport.last_crawled_at.desc())
            ).scalars().first()
            relations = list(
                db.execute(
                    select(UniversityCompetitionEditionRelation, CompetitionEdition)
                    .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
                    .where(
                        UniversityCompetitionEditionRelation.university_id == university.id,
                        UniversityCompetitionEditionRelation.is_demo.is_(False),
                    )
                ).all()
            )
            university_leads = lead_by_university.get(university.name, [])
            matched_competitions = len({lead.matched_competition_id for lead in university_leads if lead.matched_competition_id})
            edition_2026_count = len({edition.id for _, edition in relations if edition.year == 2026})
            current_registration_count = self._current_registration_count(relations)
            university_notice_count = sum(1 for relation, _ in relations if relation.college_id is None)
            college_notice_count = sum(1 for relation, _ in relations if relation.college_id is not None)

            progress.append(
                {
                    "university_id": university.id,
                    "university_name": university.name,
                    "short_name": university.short_name,
                    "province": university.province,
                    "city": university.city,
                    "official_domain": university.official_domain,
                    "scope": scope,
                    "is_985": university.is_985,
                    "is_211": university.is_211,
                    "seeded": True,
                    "batch_name": report.batch_name if report else None,
                    "discovery_status": report.status if report else university.competition_discovery_status,
                    "methods_attempted": report.methods_attempted if report else [],
                    "methods_successful": report.methods_successful if report else [],
                    "pages_examined": report.pages_examined if report else 0,
                    "candidate_articles": report.candidate_articles if report else 0,
                    "pages_searched": report.pages_searched if report else 0,
                    "competition_leads": max(report.competition_leads if report else 0, len(university_leads)),
                    "matched_competitions": max(report.matched_competitions if report else 0, matched_competitions),
                    "new_competitions": report.new_competitions if report else 0,
                    "new_editions": report.new_editions if report else 0,
                    "official_sources": report.official_sources if report else 0,
                    "university_notice_count": university_notice_count if relations else (report.university_notice_count if report else 0),
                    "college_notice_count": college_notice_count if relations else (report.college_notice_count if report else 0),
                    "current_registration_count": current_registration_count if relations else (report.current_registration_count if report else 0),
                    "edition_2026_count": edition_2026_count if relations else (report.edition_2026_count if report else 0),
                    "wechat_leads": max(
                        report.wechat_leads if report else 0,
                        sum("wechat" in (lead.source_platform or "").lower() for lead in university_leads),
                    ),
                    "internal_deadlines": report.internal_deadlines if report else 0,
                    "last_crawled_at": self._as_utc(
                        (report.last_crawled_at if report else None) or university.last_competition_discovery_at
                    ),
                    "reason": report.reason if report else university.competition_discovery_error,
                    "channel_stats": report.channel_stats if report else {},
                }
            )
        return progress

    def _aggregate(self, progress: list[dict]) -> dict[str, int]:
        return {
            "universities_with_leads": sum(item["competition_leads"] > 0 for item in progress),
            "universities_with_matched_competitions": sum(item["matched_competitions"] > 0 for item in progress),
            "universities_with_2026_editions": sum(item["edition_2026_count"] > 0 for item in progress),
            "competition_leads": sum(item["competition_leads"] for item in progress),
            "matched_competitions": sum(item["matched_competitions"] for item in progress),
            "new_competitions": sum(item["new_competitions"] for item in progress),
            "new_editions": sum(item["new_editions"] for item in progress),
            "official_sources": sum(item["official_sources"] for item in progress),
            "university_notice_count": sum(item["university_notice_count"] for item in progress),
            "college_notice_count": sum(item["college_notice_count"] for item in progress),
            "current_registration_count": sum(item["current_registration_count"] for item in progress),
            "edition_2026_count": sum(item["edition_2026_count"] for item in progress),
            "wechat_leads": sum(item["wechat_leads"] for item in progress),
            "university_relations": sum(
                item["university_notice_count"] + item["college_notice_count"] for item in progress
            ),
            "internal_deadlines": sum(item.get("internal_deadlines", 0) for item in progress),
        }

    def source_distribution(self, db: Session) -> dict[str, int]:
        leads = list(db.execute(select(CompetitionLead)).scalars())
        sources = list(db.execute(select(CompetitionSource).where(CompetitionSource.is_demo.is_(False))).scalars())
        reports = list(db.execute(select(UniversityCompetitionDiscoveryReport)).scalars())
        universities = {item.name: item for item in db.execute(select(University)).scalars()}
        source_types_by_competition: dict[int, set[str]] = {}
        for source in sources:
            if source.competition_id:
                source_types_by_competition.setdefault(source.competition_id, set()).add(source.source_type)

        def lead_in_scope(lead: CompetitionLead, scope: str) -> bool:
            university = universities.get((lead.metadata_json or {}).get("university"))
            if university is None:
                return False
            return university.is_985 if scope == "985" else university.is_211 and not university.is_985

        return {
            "university_official": sum(lead.source_type == "university_official" for lead in leads),
            "college_official": sum(lead.source_platform == "college_website" for lead in leads)
            + sum(source.source_type == "college_official_notice" for source in sources),
            "organizer_official": sum(lead.source_type in {"organizer_official_notice", "competition_official"} for lead in leads)
            + sum(source.source_type in {"organizer_official_notice", "competition_official"} for source in sources),
            "third_party_platform": sum(lead.source_type == "third_party_platform" for lead in leads),
            "source_repository_discovery": sum(lead.source_type == "source_repository_discovery" for lead in leads),
            "wechat": sum("wechat" in (lead.source_platform or "").lower() for lead in leads)
            + sum(report.wechat_leads for report in reports),
            "university_985": sum(lead_in_scope(lead, "985") for lead in leads),
            "university_211_non_985": sum(lead_in_scope(lead, "211_non_985") for lead in leads),
            "github": sum(lead.source_platform == "github" for lead in leads),
            "competition_platform": sum(lead.source_type == "third_party_platform" for lead in leads),
            "competitions_with_two_source_types": sum(
                len(source_types) >= 2 for source_types in source_types_by_competition.values()
            ),
        }

    def discovery_method_summary(self, db: Session) -> dict[str, Any]:
        reports = list(db.execute(select(UniversityCompetitionDiscoveryReport)).scalars())
        counts = {
            "sitemap": 0,
            "department_feed": 0,
            "site_search": 0,
            "external_search": 0,
            "wechat": 0,
            "reverse_match": 0,
            "navigation": 0,
        }
        status_by_scope: dict[str, dict[str, int]] = {
            "985": {"completed": 0, "completed_with_gaps": 0, "partial": 0, "failed": 0, "blocked": 0},
            "211_non_985": {"completed": 0, "completed_with_gaps": 0, "partial": 0, "failed": 0, "blocked": 0},
        }
        universities = {item.id: item for item in db.execute(select(University)).scalars()}
        for report in reports:
            university = universities.get(report.university_id)
            if university is None:
                continue
            scope = "985" if university.is_985 else "211_non_985" if university.is_211 else "other"
            if scope != "other" and report.status in status_by_scope[scope]:
                status_by_scope[scope][report.status] += 1
            for method in report.methods_successful or []:
                if method in counts:
                    counts[method] += 1
        return {
            **counts,
            "status_by_scope": status_by_scope,
        }

    def _current_registration_count(
        self,
        relations: list[tuple[UniversityCompetitionEditionRelation, CompetitionEdition]],
    ) -> int:
        now = datetime.now(timezone.utc)
        edition_ids: set[int] = set()
        for relation, edition in relations:
            if relation.notice_type not in ACTION_NOTICE_TYPES:
                continue
            relation_deadline = (
                relation.college_registration_deadline
                if relation.college_id is not None
                else relation.internal_registration_deadline
            )
            deadline = self._aware(relation_deadline) or self._aware(edition.official_registration_deadline)
            if deadline and deadline >= now and edition.current_status in {"registration_open", "registration_upcoming"}:
                edition_ids.add(edition.id)
        return len(edition_ids)

    def _aware(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)
