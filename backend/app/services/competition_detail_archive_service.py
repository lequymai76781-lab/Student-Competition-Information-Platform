from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionSource,
    UniversityCompetitionEditionRelation,
)

STRUCTURED_FIELDS = {
    "history_timeline",
    "participation_requirements",
    "competition_process",
    "submission_requirements",
    "award_settings",
}
DETAIL_OPTIONAL_FIELDS = (
    "short_name",
    "english_name",
    "description",
    "organizer",
    "official_website",
    "founded_year",
    "frequency",
    "competition_scope",
    "target_students",
    "team_type",
    "min_team_size",
    "max_team_size",
    "competition_format",
    "history_timeline",
    "participation_requirements",
    "competition_process",
    "submission_requirements",
    "award_settings",
)


class CompetitionDetailArchiveService:
    def import_json(self, db: Session, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        before_count = self._competition_count(db)
        facts_created = 0
        facts_updated = 0
        sources_created = 0
        updated_ids: list[int] = []
        now = datetime.now(timezone.utc)

        for record in payload.get("competitions", []):
            competition = db.get(Competition, int(record["id"]))
            if competition is None or competition.name != record["name"]:
                raise ValueError(f"Existing competition mismatch: {record['id']} {record['name']}")
            source = record["source"]
            sources_created += int(self._upsert_source(db, competition, source, now))
            for field_name, raw_value in record.get("fields", {}).items():
                value = self._with_item_sources(raw_value, source) if field_name in STRUCTURED_FIELDS else raw_value
                setattr(competition, field_name, value)
                created = self._upsert_fact(db, competition, field_name, value, source, now)
                facts_created += int(created)
                facts_updated += int(not created)
                if field_name == "description":
                    competition.description_source_url = source["url"]

            edition_updates = record.get("edition_updates") or {}
            edition = next((item for item in competition.editions if item.year == 2026), None)
            if edition is not None:
                for field_name, value in edition_updates.items():
                    setattr(edition, field_name, value)
                    created = self._upsert_fact(db, competition, field_name, value, source, now, edition.id)
                    facts_created += int(created)
                    facts_updated += int(not created)

            competition.last_verified_at = now
            competition.last_seen_at = now
            competition.source_hash = self._hash(json.dumps(record, ensure_ascii=False, sort_keys=True))
            updated_ids.append(competition.id)

        db.flush()
        ready_count = self.refresh_detail_ready(db)
        after_count = self._competition_count(db)
        if before_count != after_count:
            raise RuntimeError(f"V0.7.1 must not change Competition count: {before_count} -> {after_count}")
        return {
            "version": payload.get("version", "v0.7.1"),
            "competition_count_before": before_count,
            "competition_count_after": after_count,
            "competitions_created": 0,
            "competitions_updated": len(updated_ids),
            "updated_ids": updated_ids,
            "sources_created": sources_created,
            "facts_created": facts_created,
            "facts_updated": facts_updated,
            "detail_ready": ready_count,
        }

    def refresh_detail_ready(self, db: Session) -> int:
        competitions = list(
            db.execute(
                select(Competition).options(selectinload(Competition.sources))
                .where(Competition.is_competition.is_(True), Competition.is_demo.is_(False))
            ).scalars().unique()
        )
        ready_count = 0
        for competition in competitions:
            has_reliable_source = any(
                source.is_verified
                and source.source_type not in {"github_seed", "source_repository_discovery", "third_party_platform"}
                and source.reliability_tier <= 3
                for source in competition.sources
            )
            competition.detail_ready = bool(
                competition.name
                and self._useful_description(competition.description)
                and competition.organizer
                and competition.category
                and (competition.target_students or competition.team_type)
                and has_reliable_source
                and (competition.official_website or competition.founded_year or competition.competition_format)
            )
            ready_count += int(competition.detail_ready)
        db.flush()
        return ready_count

    def acceptance(self, db: Session, updated_ids: list[int]) -> dict[str, Any]:
        competitions = list(
            db.execute(
                select(Competition)
                .options(
                    selectinload(Competition.sources),
                    selectinload(Competition.editions),
                    selectinload(Competition.tracks),
                )
                .where(Competition.is_competition.is_(True), Competition.is_demo.is_(False))
                .order_by(Competition.id)
            ).scalars().unique()
        )
        sample_ids = self._acceptance_ids(competitions, updated_ids)
        sample = [item for item in competitions if item.id in sample_ids]
        fact_rows = list(db.execute(select(CompetitionFactSource)).scalars())
        fact_by_competition: dict[int, list[CompetitionFactSource]] = {}
        for fact in fact_rows:
            fact_by_competition.setdefault(fact.competition_id, []).append(fact)

        audits = []
        for competition in sample:
            present = sum(self._present(getattr(competition, field, None)) for field in DETAIL_OPTIONAL_FIELDS)
            hidden = len(DETAIL_OPTIONAL_FIELDS) - present
            current_edition = next((edition for edition in competition.editions if edition.year == 2026), None)
            facts = fact_by_competition.get(competition.id, [])
            audits.append(
                {
                    "competition_id": competition.id,
                    "name": competition.name,
                    "visible_information_fields": present,
                    "hidden_empty_fields": hidden,
                    "has_description": self._useful_description(competition.description),
                    "has_organizer": bool(competition.organizer),
                    "has_history": bool(competition.history_timeline),
                    "has_participation_rules": bool(competition.participation_requirements or competition.target_students or competition.team_type),
                    "has_current_edition": current_edition is not None,
                    "has_sources": bool(facts or competition.sources),
                    "detail_ready": competition.detail_ready,
                    "needs_more": self._needs_more(competition, current_edition),
                }
            )

        grouped_reduction = sum(
            max(0, len(rows) - len({row.source_url for row in rows}))
            for rows in fact_by_competition.values()
        )
        school_deadline_competitions = db.scalar(
            select(func.count(func.distinct(CompetitionEdition.competition_id)))
            .select_from(UniversityCompetitionEditionRelation)
            .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
            .where(
                UniversityCompetitionEditionRelation.college_id.is_(None),
                UniversityCompetitionEditionRelation.internal_registration_deadline.is_not(None),
            )
        ) or 0
        college_deadline_competitions = db.scalar(
            select(func.count(func.distinct(CompetitionEdition.competition_id)))
            .select_from(UniversityCompetitionEditionRelation)
            .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
            .where(
                UniversityCompetitionEditionRelation.college_id.is_not(None),
                func.coalesce(
                    UniversityCompetitionEditionRelation.college_registration_deadline,
                    UniversityCompetitionEditionRelation.internal_registration_deadline,
                ).is_not(None),
            )
        ) or 0
        return {
            "competition_count": len(competitions),
            "competitions_added": 0,
            "detail_enriched": len(updated_ids),
            "detail_ready": sum(item.detail_ready for item in competitions),
            "with_description": sum(self._useful_description(item.description) for item in competitions),
            "with_organizer": sum(bool(item.organizer) for item in competitions),
            "with_official_website": sum(bool(item.official_website) for item in competitions),
            "with_founded_year": sum(item.founded_year is not None for item in competitions),
            "with_frequency": sum(bool(item.frequency) for item in competitions),
            "with_history_timeline": sum(bool(item.history_timeline) for item in competitions),
            "with_target_students": sum(bool(item.target_students) for item in competitions),
            "with_team_rules": sum(bool(item.team_type or item.min_team_size or item.max_team_size) for item in competitions),
            "with_competition_process": sum(bool(item.competition_process) for item in competitions),
            "with_tracks": sum(bool(item.tracks) for item in competitions),
            "with_submission_requirements": sum(bool(item.submission_requirements) for item in competitions),
            "with_award_settings": sum(bool(item.award_settings) for item in competitions),
            "with_fee_information": sum(
                any(edition.registration_fee is not None or edition.fee_notes for edition in item.editions)
                for item in competitions
            ),
            "with_current_edition": sum(any(edition.year == 2026 for edition in item.editions) for item in competitions),
            "with_registration_entry": sum(any(edition.official_registration_url for edition in item.editions) for item in competitions),
            "with_university_internal_deadline": school_deadline_competitions,
            "with_college_internal_deadline": college_deadline_competitions,
            "frontend_hidden_empty_fields": sum(
                len(DETAIL_OPTIONAL_FIELDS)
                - sum(self._present(getattr(item, field, None)) for field in DETAIL_OPTIONAL_FIELDS)
                for item in competitions
            ),
            "source_ui_duplicate_rows_merged": grouped_reduction,
            "detail_page_audit": audits,
        }

    def _upsert_source(self, db: Session, competition: Competition, source: dict[str, Any], now: datetime) -> bool:
        row = db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_id == competition.id,
                CompetitionSource.source_url == source["url"],
            )
        ).scalar_one_or_none()
        values = {
            "source_type": source["type"],
            "source_name": source["name"],
            "source_platform": "official_website",
            "crawled_at": now,
            "retrieved_at": now,
            "is_official": source["level"] in {"LEVEL_1", "LEVEL_2", "LEVEL_3"},
            "is_verified": True,
            "credibility_score": 100 if source["level"] == "LEVEL_1" else 90,
            "reliability_tier": int(source["tier"]),
            "verification_status": "verified_official",
            "raw_title": source["name"],
            "content_hash": self._hash(source["url"] + source["name"]),
            "metadata_json": {"pipeline": "v0.7.1-detail-archive", "source_level": source["level"]},
            "is_demo": False,
        }
        created = row is None
        if created:
            db.add(CompetitionSource(competition_id=competition.id, source_url=source["url"], **values))
        else:
            for field, value in values.items():
                setattr(row, field, value)
        return created

    def _upsert_fact(
        self,
        db: Session,
        competition: Competition,
        field_name: str,
        value: Any,
        source: dict[str, Any],
        now: datetime,
        edition_id: int | None = None,
    ) -> bool:
        row = db.execute(
            select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == competition.id,
                CompetitionFactSource.competition_edition_id == edition_id,
                CompetitionFactSource.field_name == field_name,
                CompetitionFactSource.source_url == source["url"],
            )
        ).scalar_one_or_none()
        values = {
            "fact_value": value,
            "source_type": source["type"],
            "source_name": source["name"],
            "reliability_tier": int(source["tier"]),
            "source_level": source["level"],
            "is_official": source["level"] in {"LEVEL_1", "LEVEL_2", "LEVEL_3"},
            "verification_status": "verified_official",
            "observed_at": now,
            "last_verified_at": now,
            "source_hash": self._hash(json.dumps(value, ensure_ascii=False, sort_keys=True)),
            "notes": "V0.7.1赛事资料档案字段级来源。",
        }
        created = row is None
        if created:
            db.add(
                CompetitionFactSource(
                    competition_id=competition.id,
                    competition_edition_id=edition_id,
                    field_name=field_name,
                    source_url=source["url"],
                    **values,
                )
            )
        else:
            for field, item in values.items():
                setattr(row, field, item)
        return created

    def _with_item_sources(self, value: Any, source: dict[str, Any]) -> Any:
        result = deepcopy(value)
        for item in result:
            item.setdefault("source_url", source["url"])
            item.setdefault("source_name", source["name"])
            item.setdefault("verification_status", "verified_official")
        return result

    def _acceptance_ids(self, competitions: list[Competition], updated_ids: list[int]) -> list[int]:
        selected = list(dict.fromkeys(updated_ids))[:10]
        remaining = [item.id for item in competitions if item.id not in selected]
        random.Random(20260901).shuffle(remaining)
        return selected + remaining[: 20 - len(selected)]

    def _needs_more(self, competition: Competition, current_edition: object | None) -> list[str]:
        needs = []
        checks = (
            ("赛事历史", competition.history_timeline),
            ("参赛细则", competition.participation_requirements or competition.target_students),
            ("比赛流程", competition.competition_process or competition.competition_format),
            ("作品要求", competition.submission_requirements),
            ("奖项设置", competition.award_settings),
            ("当前届报名入口", getattr(current_edition, "official_registration_url", None)),
        )
        for label, value in checks:
            if not self._present(value):
                needs.append(label)
        return needs

    def _useful_description(self, value: str | None) -> bool:
        return bool(value and "首次发现" not in value and not value.startswith("由已验证高校政策"))

    def _present(self, value: Any) -> int:
        return int(value not in (None, "", [], {}, "unknown"))

    def _competition_count(self, db: Session) -> int:
        return db.scalar(select(func.count()).select_from(Competition)) or 0

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
