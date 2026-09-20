from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionLead,
    CompetitionTrack,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.source_authority_service import authority_level_for, can_prove

ACTION_NOTICE_TYPES = {"registration_notice", "internal_selection", "submission_notice"}
CORE_FIELDS = (
    "name",
    "short_name",
    "english_name",
    "former_names",
    "description",
    "organizer",
    "co_organizers",
    "guiding_organizations",
    "undertakers",
    "official_website",
    "official_account",
    "founded_year",
    "first_held_year",
    "frequency",
    "competition_scope",
    "country_or_region",
    "target_students",
    "team_type",
    "min_team_size",
    "max_team_size",
    "competition_format",
    "typical_schedule",
)
COMPLETENESS_FIELDS = (
    "description",
    "organizer",
    "official_website",
    "founded_year",
    "frequency",
    "target_students",
    "team_type",
    "competition_format",
)


class CompetitionDetailEnrichmentService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()

    def run(self, db: Session, *, common_limit: int = 30) -> dict[str, Any]:
        relation_stats = self._refresh_notice_relations(db)
        deadline_cleanup = self._clear_unproven_official_deadlines(db)
        hierarchy_stats = self._repair_hierarchy(db)
        targets = self._target_competitions(db, common_limit=common_limit)

        facts_created = 0
        facts_updated = 0
        descriptions_created = 0
        processed_by_priority: dict[str, int] = {}
        for priority, competition in targets:
            processed_by_priority[priority] = processed_by_priority.get(priority, 0) + 1
            source = self._best_source(competition)
            if source is not None and not competition.description:
                description = self._summary_from_verified_fields(competition)
                if description:
                    competition.description = description
                    competition.description_source_url = source.source_url
                    descriptions_created += 1

            if source is not None:
                for field_name in CORE_FIELDS:
                    value = getattr(competition, field_name, None)
                    if value in (None, "", []):
                        continue
                    created = self._upsert_fact(
                        db,
                        competition=competition,
                        edition=None,
                        field_name=field_name,
                        value=value,
                        source=source,
                    )
                    facts_created += int(created)
                    facts_updated += int(not created)
                competition.last_verified_at = self._source_time(source)
                competition.last_seen_at = datetime.now(timezone.utc)
                competition.source_hash = self._source_hash(source.source_url, source.content_hash, source.raw_title)

            competition.data_completeness_score = self._completeness_score(competition)
            for edition in competition.editions:
                created, updated = self._enrich_edition(db, competition, edition)
                facts_created += created
                facts_updated += updated

        duplicate_groups = self._duplicate_groups(db)
        db.flush()
        return {
            "targets_processed": len(targets),
            "processed_by_priority": processed_by_priority,
            "facts_created": facts_created,
            "facts_updated": facts_updated,
            "descriptions_created": descriptions_created,
            "notice_relations": relation_stats,
            "deadline_cleanup": deadline_cleanup,
            "hierarchy_repairs": hierarchy_stats,
            "duplicate_groups": duplicate_groups,
        }

    def _target_competitions(self, db: Session, *, common_limit: int) -> list[tuple[str, Competition]]:
        competitions = list(
            db.execute(
                select(Competition)
                .options(
                    selectinload(Competition.sources),
                    selectinload(Competition.editions),
                    selectinload(Competition.editions).selectinload(CompetitionEdition.sources),
                )
                .where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
                .order_by(Competition.id)
            ).scalars().unique()
        )
        active_ids = {
            competition.id
            for competition in competitions
            if any(edition.current_status in {"registration_open", "submission_open"} for edition in competition.editions)
        }
        edition_2026_ids = {
            competition.id for competition in competitions if any(edition.year == 2026 for edition in competition.editions)
        }
        new_v06_ids = {competition.id for competition in competitions if 119 <= competition.id <= 141}
        common_ids = {competition.id for competition in competitions[:common_limit]}

        result: list[tuple[str, Competition]] = []
        seen: set[int] = set()
        for priority, ids in (
            ("P0-P1_active", active_ids),
            ("P2_2026", edition_2026_ids),
            ("P3_v06_new", new_v06_ids),
            ("P5_common", common_ids),
        ):
            for competition in competitions:
                if competition.id in ids and competition.id not in seen:
                    result.append((priority, competition))
                    seen.add(competition.id)
        return result

    def _refresh_notice_relations(self, db: Session) -> dict[str, int]:
        relations = list(db.execute(select(UniversityCompetitionEditionRelation)).scalars())
        leads_by_url = {
            lead.source_url: lead
            for lead in db.execute(select(CompetitionLead)).scalars()
            if lead.source_url
        }
        counts: dict[str, int] = {}
        now = datetime.now(timezone.utc)
        for relation in relations:
            lead = leads_by_url.get(relation.internal_notice_url)
            if lead is not None and lead.raw_title:
                relation.notice_title = lead.raw_title
            classified = self._notice_type(relation.notice_title or relation.source_name or "")
            if (
                classified in {"other", "competition_announcement"}
                and lead is not None
                and lead.classification == "registration_notice"
            ):
                classified = "registration_notice"
            relation.notice_type = classified
            if relation.college_id is not None and relation.college_registration_deadline is None:
                relation.college_registration_deadline = relation.internal_registration_deadline
            relation.notice_title = relation.notice_title or relation.source_name
            relation.contact_method = relation.contact_method or relation.internal_contact
            relation.last_verified_at = relation.last_verified_at or relation.observed_at
            relation.last_seen_at = now
            relation.source_hash = self._source_hash(
                relation.internal_notice_url,
                None,
                relation.notice_title,
            )
            counts[relation.notice_type] = counts.get(relation.notice_type, 0) + 1

        editions = list(
            db.execute(
                select(CompetitionEdition).options(selectinload(CompetitionEdition.university_relations))
            ).scalars().unique()
        )
        for edition in editions:
            university_deadlines = [
                relation.internal_registration_deadline
                for relation in edition.university_relations
                if relation.college_id is None
                and relation.notice_type in ACTION_NOTICE_TYPES
                and relation.internal_registration_deadline is not None
            ]
            edition.university_registration_deadline = min(university_deadlines) if university_deadlines else None
        return {"total": len(relations), **counts}

    def _clear_unproven_official_deadlines(self, db: Session) -> dict[str, int]:
        editions = list(
            db.execute(
                select(CompetitionEdition).options(
                    selectinload(CompetitionEdition.sources),
                    selectinload(CompetitionEdition.university_relations),
                )
            ).scalars().unique()
        )
        cleared = 0
        facts_removed = 0
        direct_official_types = {"official_notice", "organizer_official_notice", "government_official_notice"}
        for edition in editions:
            deadline = edition.official_registration_deadline
            if deadline is None:
                continue
            relation_evidence = any(
                relation.is_verified
                and relation.official_registration_deadline == deadline
                and relation.internal_notice_url
                for relation in edition.university_relations
            )
            direct_official_evidence = any(
                source.is_verified and source.source_type in direct_official_types
                for source in edition.sources
            )
            if relation_evidence or direct_official_evidence:
                continue
            edition.official_registration_deadline = None
            cleared += 1
            facts = list(
                db.execute(
                    select(CompetitionFactSource).where(
                        CompetitionFactSource.competition_edition_id == edition.id,
                        CompetitionFactSource.field_name == "official_registration_deadline",
                    )
                ).scalars()
            )
            for fact in facts:
                db.delete(fact)
                facts_removed += 1
        return {"official_deadlines_cleared": cleared, "fact_sources_removed": facts_removed}

    def _repair_hierarchy(self, db: Session) -> dict[str, int]:
        repaired = 0
        tracks_created = 0
        parent = db.execute(select(Competition).where(Competition.name == "中国国际大学生创新大赛")).scalar_one_or_none()
        child = db.execute(
            select(Competition).where(Competition.name == "中国国际大学生创新大赛产业命题赛道")
        ).scalar_one_or_none()
        if parent is not None and child is not None:
            if child.parent_competition_id != parent.id or child.competition_type != "track":
                child.parent_competition_id = parent.id
                child.competition_type = "track"
                child.entity_type = "track"
                repaired += 1
            track = db.execute(
                select(CompetitionTrack).where(
                    CompetitionTrack.competition_id == parent.id,
                    CompetitionTrack.name == "产业命题赛道",
                )
            ).scalar_one_or_none()
            if track is None:
                source = self._best_source(child)
                db.add(
                    CompetitionTrack(
                        competition_id=parent.id,
                        name="产业命题赛道",
                        track_type="official_track",
                        description="企业发布真实产业命题，参赛团队选择命题并提交解决方案。",
                        source_url=source.source_url if source else None,
                        source_name=source.source_name if source else None,
                        reliability_tier=source.reliability_tier if source else 5,
                        is_official=bool(source and source.is_official),
                        verification_status=source.verification_status if source else "secondary_source_only",
                        observed_at=self._source_time(source) if source else None,
                        order_index=3,
                    )
                )
                tracks_created += 1

        university_scopes = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.competition_scope == "校级",
                )
            ).scalars()
        )
        for competition in university_scopes:
            competition.competition_scope = "university"
        return {
            "competition_hierarchy_repaired": repaired,
            "tracks_created": tracks_created,
            "university_scope_normalized": len(university_scopes),
        }

    def _enrich_edition(
        self,
        db: Session,
        competition: Competition,
        edition: CompetitionEdition,
    ) -> tuple[int, int]:
        source = self._best_edition_source(edition) or self._best_source(competition)
        if source is None:
            return 0, 0
        if edition.official_submission_deadline is None and source.source_type in {
            "official_notice",
            "competition_official",
            "organizer_official_notice",
        }:
            edition.official_submission_deadline = edition.submission_deadline
        if edition.official_competition_date is None and source.source_type in {
            "official_notice",
            "competition_official",
            "organizer_official_notice",
        }:
            edition.official_competition_date = edition.competition_start
        edition.last_seen_at = datetime.now(timezone.utc)
        edition.source_hash = self._source_hash(source.source_url, source.content_hash, source.raw_title)
        fields = {
            "edition_name": edition.edition_name,
            "registration_start": edition.registration_start,
            "registration_deadline": edition.registration_deadline,
            "official_registration_deadline": edition.official_registration_deadline,
            "submission_deadline": edition.submission_deadline,
            "official_submission_deadline": edition.official_submission_deadline,
            "competition_start": edition.competition_start,
            "competition_end": edition.competition_end,
            "official_competition_date": edition.official_competition_date,
            "official_registration_url": edition.official_registration_url,
            "current_status": edition.current_status,
        }
        created = 0
        updated = 0
        for field_name, value in fields.items():
            if value in (None, "", []):
                continue
            was_created = self._upsert_fact(
                db,
                competition=competition,
                edition=edition,
                field_name=field_name,
                value=value,
                source=source,
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated

    def _upsert_fact(
        self,
        db: Session,
        *,
        competition: Competition,
        edition: CompetitionEdition | None,
        field_name: str,
        value: Any,
        source: Any,
    ) -> bool:
        fact = db.execute(
            select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == competition.id,
                CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
                CompetitionFactSource.field_name == field_name,
                CompetitionFactSource.source_url == source.source_url,
            )
        ).scalar_one_or_none()
        level = self._source_level(source.source_type)
        observed_at = self._source_time(source)
        payload = {
            "fact_value": self._json_value(value),
            "source_type": source.source_type,
            "source_name": source.source_name,
            "reliability_tier": source.reliability_tier,
            "source_level": level,
            "is_official": bool(source.is_official),
            "verification_status": (
                "verified_official"
                if source.is_verified
                and authority_level_for(source.source_type) in {"S", "A"}
                and can_prove(source.source_type, field_name)
                else "secondary_source_only"
            ),
            "published_at": source.published_at,
            "observed_at": observed_at,
            "last_verified_at": observed_at,
            "source_hash": self._source_hash(source.source_url, source.content_hash, source.raw_title),
            "notes": "V0.7字段级事实回填；事实等级由原始来源类型决定。",
        }
        created = fact is None
        if fact is None:
            db.add(
                CompetitionFactSource(
                    competition_id=competition.id,
                    competition_edition_id=edition.id if edition else None,
                    field_name=field_name,
                    source_url=source.source_url,
                    **payload,
                )
            )
        else:
            for key, item in payload.items():
                setattr(fact, key, item)
        return created

    def _best_source(self, competition: Competition) -> Any | None:
        sources = [source for source in competition.sources if not source.is_demo and source.source_type != "university_policy"]
        if not sources:
            return None
        return min(sources, key=lambda source: (self._source_rank(source.source_type), -int(source.is_verified), source.id))

    def _best_edition_source(self, edition: CompetitionEdition) -> Any | None:
        sources = [source for source in edition.sources if not source.is_demo]
        if not sources:
            return None
        return min(sources, key=lambda source: (self._source_rank(source.source_type), -int(source.is_verified), source.id))

    def _summary_from_verified_fields(self, competition: Competition) -> str | None:
        if not competition.organizer:
            return None
        details = []
        if competition.category:
            details.append(f"聚焦{competition.category}")
        if competition.team_type:
            details.append(f"采用{competition.team_type}形式")
        if competition.competition_scope:
            details.append(f"赛事范围为{competition.competition_scope}")
        if not details:
            return None
        return f"{competition.name}由{competition.organizer}组织，" + "，".join(details) + "。"

    def _completeness_score(self, competition: Competition) -> float:
        present = sum(getattr(competition, field, None) not in (None, "", []) for field in COMPLETENESS_FIELDS)
        has_edition = any(edition.year == 2026 for edition in competition.editions)
        has_registration = any(edition.official_registration_url for edition in competition.editions)
        has_official_source = any(source.is_official and source.is_verified for source in competition.sources)
        return round((present + int(has_edition) + int(has_registration) + int(has_official_source)) / 11 * 100, 2)

    def _duplicate_groups(self, db: Session) -> list[dict[str, Any]]:
        groups: dict[str, list[Competition]] = {}
        competitions = list(
            db.execute(select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))).scalars()
        )
        for competition in competitions:
            normalized = self.normalizer._normalize_text(competition.name)
            groups.setdefault(normalized, []).append(competition)
        return [
            {"normalized_name": key, "competition_ids": [item.id for item in items], "names": [item.name for item in items]}
            for key, items in groups.items()
            if len(items) > 1
        ]

    def _notice_type(self, title: str) -> str:
        if any(token in title for token in ("获奖", "表彰")):
            return "award_news"
        if any(token in title for token in ("结果", "名单")):
            return "result_notice"
        if any(token in title for token in ("培训", "训练营", "宣讲")):
            return "training_notice"
        if any(token in title for token in ("招募", "组队", "队员")):
            return "team_recruitment"
        if any(token in title for token in ("作品提交", "提交作品", "投稿")):
            return "submission_notice"
        if any(token in title for token in ("校内选拔", "选拔赛", "校赛", "初选")):
            return "internal_selection"
        if any(token in title for token in ("报名", "组织参加", "参赛通知")):
            return "registration_notice"
        if any(token in title for token in ("公示", "公告", "通知")):
            return "competition_announcement"
        return "other"

    def _source_rank(self, source_type: str) -> int:
        return {
            "competition_official": 1,
            "competition_official_site": 1,
            "organizer_official_notice": 1,
            "official": 1,
            "official_notice": 2,
            "university_official": 3,
            "university_official_notice": 3,
            "college_official_notice": 3,
            "github_seed": 5,
            "github": 5,
            "third_party_platform": 5,
        }.get(source_type, 6)

    def _source_level(self, source_type: str) -> str:
        return f"LEVEL_{self._source_rank(source_type)}"

    def _source_time(self, source: Any) -> datetime:
        if source is None:
            return datetime.now(timezone.utc)
        return source.retrieved_at or source.crawled_at or source.published_at or datetime.now(timezone.utc)

    def _source_hash(self, url: str, content_hash: str | None, title: str | None) -> str:
        return content_hash or hashlib.sha256(f"{url}|{title or ''}".encode("utf-8")).hexdigest()

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
