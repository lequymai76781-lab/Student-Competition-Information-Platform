from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CandidateCompetition,
    CandidateFact,
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionLead,
    CompetitionSource,
    PolicyDocument,
    PolicyRawItem,
    ReviewQueue,
)
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.source_authority_service import (
    OFFICIAL_COMPETITION_SOURCE_TYPES,
    authority_level_for,
    competition_status_from_source_levels,
    is_national_authority_source,
)


NON_COMPETITION_CLASSIFICATIONS = {
    "中国新闻奖": ("award", 1.0, "名称及奖项办法均指向新闻作品奖，不是可报名的大学生竞赛。"),
    "中国舞蹈荷花奖": ("award", 1.0, "该项目是舞蹈专业奖项，不是面向大学生统一报名的竞赛。"),
    "省级新闻奖": ("award", 1.0, "泛指省级新闻作品奖，缺少独立赛事主体。"),
    "市级新闻奖": ("award", 1.0, "泛指市级新闻作品奖，缺少独立赛事主体。"),
    "全国大学生艺术节": ("festival", 0.95, "名称和公开活动形态为艺术节/展演，不能等同为单一竞赛。"),
    "全国大学生创新创业训练计划年会展示": (
        "exhibition",
        1.0,
        "该项目是国家级大学生创新创业训练计划年度展示交流活动。",
    ),
    "AIGC应用大赛": ("unknown", 0.5, "名称过于宽泛，尚未核实唯一主办方和连续届次。"),
}

class FactIntelligenceService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()
        self.freshness = CompetitionFreshnessService()

    def run(
        self,
        db: Session,
        *,
        policy_rows_path: Path,
        github_snapshot_path: Path,
        university_seed_path: Path,
        github_repository: str,
        github_commit: str,
    ) -> dict[str, object]:
        policy_stats = self.classify_policy_rows(db, policy_rows_path)
        github_stats = self.import_github_leads(
            db,
            github_snapshot_path,
            repository=github_repository,
            commit=github_commit,
        )
        university_stats = self.import_university_discovery(db, university_seed_path)
        source_stats = self.refresh_source_tiers(db)
        verification_stats = self.refresh_verification(db)
        db.commit()
        return {
            "policy_raw_items": policy_stats,
            "github_discovery": github_stats,
            "university_discovery": university_stats,
            "source_tiers": source_stats,
            "verification": verification_stats,
        }

    def classify_policy_rows(self, db: Session, path: Path) -> dict[str, int]:
        rows = json.loads(path.read_text(encoding="utf-8"))
        document = db.execute(
            select(PolicyDocument).where(PolicyDocument.title == "武汉体育学院新闻传播学院大学生学科竞赛目录")
        ).scalar_one()
        counts: dict[str, int] = {}

        for item in rows:
            candidate = db.execute(
                select(CandidateCompetition).where(
                    CandidateCompetition.policy_document_id == document.id,
                    CandidateCompetition.table_row == str(item["row"]),
                    CandidateCompetition.raw_name == item["name"],
                )
            ).scalar_one_or_none()
            competition = candidate.normalized_competition if candidate else None
            entity_type, confidence, reason = NON_COMPETITION_CLASSIFICATIONS.get(
                item["name"],
                ("competition", 0.95, "目录名称明确指向竞赛、大赛、比赛或已核验的连续赛事。"),
            )
            needs_review = entity_type == "unknown"
            raw_text = f'目录第{item["row"]}行：{item["name"]}，级别{item["level"]}。'
            raw = db.execute(
                select(PolicyRawItem).where(
                    PolicyRawItem.policy_document_id == document.id,
                    PolicyRawItem.raw_order == item["row"],
                    PolicyRawItem.raw_name == item["name"],
                )
            ).scalar_one_or_none()
            payload = {
                "raw_level": item["level"],
                "raw_text": raw_text,
                "entity_type": entity_type,
                "normalized_competition_id": competition.id if competition else None,
                "confidence": confidence,
                "needs_manual_review": needs_review,
                "classification_reason": reason,
                "metadata_json": {"page": item["page"], "classification_version": "v0.4"},
            }
            if raw is None:
                raw = PolicyRawItem(
                    policy_document_id=document.id,
                    raw_order=item["row"],
                    raw_name=item["name"],
                    **payload,
                )
                db.add(raw)
            else:
                for field, value in payload.items():
                    setattr(raw, field, value)

            if competition is not None:
                competition.entity_type = entity_type
                competition.is_competition = entity_type == "competition"
                if not competition.is_competition:
                    competition.verification_status = "suspected" if entity_type == "unknown" else "unverified"

            counts[entity_type] = counts.get(entity_type, 0) + 1
        db.flush()
        return {"total": len(rows), **counts}

    def import_github_leads(
        self,
        db: Session,
        path: Path,
        *,
        repository: str,
        commit: str,
    ) -> dict[str, int | str]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = [item for item in payload.get("items", []) if item.get("event_type") in {"competition", "hackathon"}]
        stats: dict[str, int | str] = {
            "repository": repository,
            "commit": commit,
            "records_read": len(items),
            "leads_created": 0,
            "leads_updated": 0,
            "matched_competitions": 0,
            "third_party_platform_leads": 0,
            "official_platform_leads": 0,
        }
        discovered_at = self._date(payload.get("generated_at")) or datetime.now(timezone.utc)

        for item in items:
            name = (item.get("name") or "").strip()
            source = item.get("source") or {}
            source_url = source.get("url") or item.get("official_url")
            if not name or not source_url:
                continue
            authority = int(source.get("authority") or 1)
            platform = "saikr" if "saikr" in source.get("name", "").lower() else "github"
            source_type = "third_party_platform" if authority <= 2 else "source_repository_discovery"
            if source_type == "third_party_platform":
                stats["third_party_platform_leads"] = int(stats["third_party_platform_leads"]) + 1
            else:
                stats["official_platform_leads"] = int(stats["official_platform_leads"]) + 1

            normalization = self.normalizer.normalize(db, item.get("catalog_name") or name)
            competition = (
                normalization.competition
                if normalization.competition is not None and not normalization.needs_manual_review
                else None
            )
            if competition:
                stats["matched_competitions"] = int(stats["matched_competitions"]) + 1
            lead = db.execute(
                select(CompetitionLead).where(
                    CompetitionLead.source_url == source_url,
                    CompetitionLead.raw_title == name,
                )
            ).scalar_one_or_none()
            lead_payload = {
                "raw_content": item.get("description"),
                "detected_competition_name": item.get("catalog_name") or name,
                "source_type": source_type,
                "source_platform": platform,
                "source_name": source.get("name"),
                "author": None,
                "published_at": None,
                "discovered_at": discovered_at,
                "possible_year": self._year(item),
                "possible_deadline": self._date(item.get("primary_deadline")),
                "possible_organizer": item.get("organizer"),
                "classification": "registration_notice" if "open" in str(item.get("status")) else "competition_notice",
                "verification_status": "secondary_source_only",
                "matched_competition_id": competition.id if competition else None,
                "matched_edition_id": None,
                "needs_review": True,
                "notes": "GitHub快照仅用于发现；底层来源需单独回到主办方或高校官方页面核验。",
                "content_hash": self._hash(json.dumps(item, ensure_ascii=False, sort_keys=True)),
                "metadata_json": {
                    "repository": repository,
                    "commit": commit,
                    "source_file": path.name,
                    "license": "MIT (repository code); third-party data retains original rights",
                    "event_type": item.get("event_type"),
                    "source_authority": authority,
                    "source_checked_at": source.get("checked_at"),
                    "github_record_id": item.get("id"),
                },
            }
            if lead is None:
                lead = CompetitionLead(raw_title=name, source_url=source_url, **lead_payload)
                db.add(lead)
                db.flush()
                stats["leads_created"] = int(stats["leads_created"]) + 1
            else:
                for field, value in lead_payload.items():
                    setattr(lead, field, value)
                stats["leads_updated"] = int(stats["leads_updated"]) + 1
            self._candidate_facts_from_lead(db, lead, item, authority)
        db.flush()
        return stats

    def import_university_discovery(self, db: Session, path: Path) -> dict[str, object]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stats: dict[str, object] = {
            "universities_crawled": len(payload.get("universities_crawled", [])),
            "university_names": payload.get("universities_crawled", []),
            "leads_created": 0,
            "leads_updated": 0,
            "competitions_created": 0,
            "official_records_promoted": 0,
            "editions_created": 0,
        }
        discovered_at = self._date(payload.get("retrieved_at")) or datetime.now(timezone.utc)
        for item in payload.get("leads", []):
            lead, created = self._upsert_lead(
                db,
                item,
                discovered_at=discovered_at,
                source_type="university_official",
                source_platform="university_website",
            )
            key = "leads_created" if created else "leads_updated"
            stats[key] = int(stats[key]) + 1

        for record in payload.get("official_records", []):
            result = self._promote_official_record(db, record, discovered_at)
            stats["official_records_promoted"] = int(stats["official_records_promoted"]) + 1
            stats["competitions_created"] = int(stats["competitions_created"]) + int(result["competition_created"])
            stats["editions_created"] = int(stats["editions_created"]) + int(result["edition_created"])
        db.flush()
        return stats

    def refresh_source_tiers(self, db: Session) -> dict[str, int]:
        stats: dict[str, int] = {}
        for source in db.execute(select(CompetitionSource)).scalars():
            level = authority_level_for(source.source_type) or "D"
            source.authority_level = level
            tier = {"S": 1, "A": 2, "B": 2, "C": 3, "D": 4}.get(level, 4)
            if source.is_verified and level in {"S", "A"}:
                status = "verified_official"
            elif source.is_verified and level in {"B", "C"}:
                status = "school_confirmed"
            elif source.is_verified:
                status = "secondary_source_only"
            else:
                status = "unverified"
            source.reliability_tier = tier
            source.verification_status = status
            source.retrieved_at = source.retrieved_at or source.crawled_at
            stats[status] = stats.get(status, 0) + 1
        return stats

    def refresh_verification(self, db: Session) -> dict[str, int]:
        stats: dict[str, int] = {}
        competitions = list(db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars())
        for competition in competitions:
            # Explicit editorial states (duplicate / non_competition) are kept
            # as-is; authority recomputation must not resurrect them.
            if competition.verification_status in {"duplicate", "non_competition"}:
                stats["kept_explicit_state"] = stats.get("kept_explicit_state", 0) + 1
                continue
            sources = [source for source in competition.sources if not source.is_demo]
            active_sources = [
                source for source in sources if source.is_verified and not source.is_demo
            ]
            # Catalog rows only mention a competition; they cannot confirm
            # that the school actually organizes participation this year.
            proof_sources = [
                source for source in active_sources if source.source_type != "university_policy"
            ]
            verified_levels = [
                source.authority_level or authority_level_for(source.source_type)
                for source in proof_sources
            ]
            has_any_source = bool(sources)
            status = competition_status_from_source_levels(
                verified_levels,
                has_any_source=has_any_source,
                entity_type=competition.entity_type,
            )
            if status == "unverified" and any(
                source.source_type == "university_policy" for source in active_sources
            ):
                status = "pending_verification"
            competition.verification_status = status
            competition.is_official_verified = status in {"verified_official", "authority_confirmed"}
            stats[status] = stats.get(status, 0) + 1
            for edition in competition.editions:
                edition_sources = [source for source in edition.sources if not source.is_demo]
                edition_levels = {
                    source.authority_level or authority_level_for(source.source_type)
                    for source in edition_sources
                    if source.is_verified
                }
                relation_evidence = any(
                    relation.is_verified
                    for relation in edition.university_relations
                    if not relation.is_demo
                )
                if "S" in edition_levels:
                    edition.verification_status = "verified_official"
                    edition.is_verified = True
                elif "A" in edition_levels:
                    edition.verification_status = "authority_confirmed"
                    edition.is_verified = True
                elif relation_evidence:
                    edition.verification_status = "school_confirmed"
                    edition.is_verified = True
                elif edition_sources or edition.source_url or edition.official_notice_url:
                    edition.verification_status = "pending_verification"
                    edition.is_verified = True
                else:
                    edition.verification_status = "unverified"
                    edition.is_verified = False
        return stats

    def _upsert_lead(
        self,
        db: Session,
        item: dict,
        *,
        discovered_at: datetime,
        source_type: str,
        source_platform: str,
    ) -> tuple[CompetitionLead, bool]:
        lead = db.execute(
            select(CompetitionLead).where(
                CompetitionLead.source_url == item["source_url"],
                CompetitionLead.raw_title == item["raw_title"],
            )
        ).scalar_one_or_none()
        normalization = self.normalizer.normalize(db, item.get("detected_competition_name") or item["raw_title"])
        competition = normalization.competition if normalization.competition and not normalization.needs_manual_review else None
        payload = {
            "raw_content": item.get("raw_content"),
            "detected_competition_name": item.get("detected_competition_name"),
            "source_type": item.get("source_type", source_type),
            "source_platform": item.get("source_platform", source_platform),
            "source_name": item.get("source_name"),
            "author": item.get("author"),
            "published_at": self._date(item.get("published_at")),
            "discovered_at": discovered_at,
            "possible_year": item.get("possible_year"),
            "possible_deadline": self._date(item.get("possible_deadline")),
            "possible_organizer": item.get("possible_organizer"),
            "classification": item.get("classification", "unknown"),
            "verification_status": item.get(
                "verification_status",
                "verified_official"
                if is_national_authority_source(item.get("source_type", source_type))
                else "secondary_source_only",
            ),
            "matched_competition_id": competition.id if competition else None,
            "matched_edition_id": None,
            "needs_review": bool(item.get("needs_review", competition is None)),
            "notes": (
                "公开高校官网发现；赛事事实仍按字段记录来源。"
                if item.get("verification_status", "verified_official") == "verified_official"
                else "公开渠道线索，尚未回到学校或主办方页面核验。"
            ),
            "content_hash": self._hash((item.get("raw_content") or "") + item["source_url"]),
            "metadata_json": {
                "university": item.get("university"),
                "discovery_batch": item.get("discovery_batch", item.get("batch_name", "985-first-five-v0.4")),
                "batch_name": item.get("batch_name"),
                "source_scope": item.get("source_scope"),
                "channel": item.get("channel"),
            },
        }
        created = lead is None
        if created:
            lead = CompetitionLead(raw_title=item["raw_title"], source_url=item["source_url"], **payload)
            db.add(lead)
            db.flush()
        else:
            for field, value in payload.items():
                setattr(lead, field, value)
        return lead, created

    def _promote_official_record(self, db: Session, record: dict, observed_at: datetime) -> dict[str, bool]:
        record_source_type = str(
            record.get("source_type")
            or ("organizer_official_notice" if record.get("reliability_tier") == 1 else "university_official_notice")
        )
        national = record.get("reliability_tier") == 1 or is_national_authority_source(record_source_type)
        if not national:
            # School-level records can only enter the discovery pool; they must
            # not promote new Competition/Edition entities.
            existing = db.execute(
                select(CompetitionLead).where(
                    CompetitionLead.source_url == record.get("source_url"),
                    CompetitionLead.raw_title
                    == (record.get("source_name") or record["competition_name"]),
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    CompetitionLead(
                        raw_title=record.get("source_name") or record["competition_name"],
                        source_url=record.get("source_url") or "local://discovery-record",
                        source_type=record_source_type,
                        source_name=record.get("source_name"),
                        discovered_at=observed_at,
                        detected_competition_name=record["competition_name"],
                        classification="competition_notice",
                        review_status="pending",
                        verification_status="unverified",
                        needs_review=True,
                        notes="非国家级来源的 official_record 禁止自动晋升，等待 S/A 来源确认。",
                    )
                )
            return {
                "competition_created": False,
                "edition_created": False,
                "skipped_not_national": True,
            }
        normalization = self.normalizer.normalize(db, record["competition_name"])
        competition = (
            normalization.competition
            if normalization.competition and not normalization.needs_manual_review
            else None
        )
        competition_created = competition is None
        if competition is None:
            competition = Competition(
                name=record["competition_name"],
                status="active",
                is_demo=False,
                is_competition=True,
                entity_type="competition",
                verification_status="verified_official",
            )
            db.add(competition)
            db.flush()

        competition_fields = (
            "description", "organizer", "co_organizers", "guiding_organizations", "official_website",
            "official_account", "founded_year", "first_held_year", "frequency", "edition_count",
            "competition_format", "competition_scope", "country_or_region", "team_type", "min_team_size",
            "max_team_size", "target_students", "category",
        )
        for field in competition_fields:
            if field not in record or record[field] is None:
                continue
            self._apply_verified_fact(
                db,
                competition,
                field=field,
                value=record[field],
                record=record,
                observed_at=observed_at,
            )
        for alias in record.get("aliases", []):
            self.normalizer.ensure_alias(
                db, competition, alias, source="official_notice", confidence=1.0, is_verified=True
            )

        source = db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_id == competition.id,
                CompetitionSource.source_url == record["source_url"],
            )
        ).scalar_one_or_none()
        source_payload = {
            "source_type": "organizer_official_notice" if record.get("reliability_tier") == 1 else "university_official_notice",
            "source_name": record.get("source_name"),
            "source_platform": "official_website",
            "published_at": self._date(record.get("published_at")),
            "crawled_at": observed_at,
            "retrieved_at": observed_at,
            "is_official": True,
            "is_verified": True,
            "credibility_score": 100 if record.get("reliability_tier") == 1 else 90,
            "reliability_tier": int(record.get("reliability_tier", 2)),
            "verification_status": "verified_official",
            "raw_title": record.get("edition", {}).get("edition_name") or record["competition_name"],
            "metadata_json": {
                "discovery_batch": record.get("discovery_batch", record.get("batch_name", "985-first-five-v0.4")),
                "batch_name": record.get("batch_name"),
                "university": record.get("university"),
            },
            "is_demo": False,
        }
        if source is None:
            source = CompetitionSource(competition_id=competition.id, source_url=record["source_url"], **source_payload)
            db.add(source)
        else:
            for field, value in source_payload.items():
                setattr(source, field, value)

        edition_created = False
        edition_data = record.get("edition")
        if edition_data:
            edition = db.execute(
                select(CompetitionEdition).where(
                    CompetitionEdition.competition_id == competition.id,
                    CompetitionEdition.year == edition_data["year"],
                )
            ).scalar_one_or_none()
            edition_created = edition is None
            if edition is None:
                edition = CompetitionEdition(competition_id=competition.id, year=edition_data["year"])
                db.add(edition)
                db.flush()
            for field in (
                "edition_name", "edition_number", "registration_start", "registration_deadline",
                "official_registration_deadline", "university_registration_deadline",
                "submission_deadline", "competition_start", "competition_end", "official_registration_url",
                "current_status",
            ):
                if field not in edition_data:
                    continue
                value = self._date(edition_data[field]) if field.endswith(("start", "deadline", "end")) else edition_data[field]
                if value is None:
                    continue
                if field == "current_status" and value == "unknown" and edition.current_status != "unknown":
                    continue
                if field == "edition_name" and edition.edition_name and edition.edition_name != value:
                    continue
                self.freshness.update_edition_fact(
                    db,
                    edition,
                    field_name=field,
                    value=value,
                    changed_at=observed_at,
                    source_url=record["source_url"],
                    source_name=record.get("source_name"),
                )
                self._upsert_fact_source(
                    db,
                    competition=competition,
                    edition=edition,
                    field=field,
                    value=edition_data[field],
                    record=record,
                    observed_at=observed_at,
                )
            edition.official_url = record.get("official_website")
            edition.official_notice_url = record["source_url"]
            edition.source_url = record["source_url"]
            source.competition_edition_id = edition.id
            edition.is_verified = True
            edition.verification_status = "verified_official"
            self.freshness.mark_verified(
                edition,
                observed_at=observed_at,
                source_updated_at=self._date(record.get("published_at")),
            )

            lead = db.execute(
                select(CompetitionLead).where(CompetitionLead.source_url == record["source_url"])
            ).scalars().first()
            if lead:
                lead.matched_competition_id = competition.id
                lead.matched_edition_id = edition.id
                lead.needs_review = False
                lead.verification_status = "verified_official"

        competition.is_competition = True
        competition.entity_type = "competition"
        competition.verification_status = "verified_official"
        competition.is_official_verified = True
        return {"competition_created": competition_created, "edition_created": edition_created}

    def _apply_verified_fact(
        self,
        db: Session,
        competition: Competition,
        *,
        field: str,
        value: object,
        record: dict,
        observed_at: datetime,
    ) -> None:
        current = getattr(competition, field)
        if current not in (None, "", []) and current != value:
            self._record_conflict(db, competition, field, value, record)
            return
        setattr(competition, field, value)
        self._upsert_fact_source(
            db,
            competition=competition,
            edition=None,
            field=field,
            value=value,
            record=record,
            observed_at=observed_at,
        )

    def _upsert_fact_source(
        self,
        db: Session,
        *,
        competition: Competition,
        edition: CompetitionEdition | None,
        field: str,
        value: object,
        record: dict,
        observed_at: datetime,
    ) -> None:
        fact = db.execute(
            select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == competition.id,
                CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
                CompetitionFactSource.field_name == field,
                CompetitionFactSource.source_url == record["source_url"],
            )
        ).scalar_one_or_none()
        payload = {
            "fact_value": value,
            "source_type": "organizer_official_notice" if record.get("reliability_tier") == 1 else "university_official_notice",
            "source_name": record.get("source_name"),
            "reliability_tier": int(record.get("reliability_tier", 2)),
            "is_official": True,
            "verification_status": "verified_official",
            "published_at": self._date(record.get("published_at")),
            "observed_at": observed_at,
        }
        if fact is None:
            db.add(
                CompetitionFactSource(
                    competition_id=competition.id,
                    competition_edition_id=edition.id if edition else None,
                    field_name=field,
                    source_url=record["source_url"],
                    **payload,
                )
            )
        else:
            for key, item in payload.items():
                setattr(fact, key, item)

    def _record_conflict(self, db: Session, competition: Competition, field: str, value: object, record: dict) -> None:
        candidate = db.execute(
            select(CandidateFact).where(
                CandidateFact.lead_id.is_(None),
                CandidateFact.competition_id == competition.id,
                CandidateFact.field_name == field,
                CandidateFact.source_url == record["source_url"],
            )
        ).scalar_one_or_none()
        if candidate is None:
            candidate = CandidateFact(
                competition_id=competition.id,
                field_name=field,
                candidate_value=value,
                source_url=record["source_url"],
                source_type="university_official_notice",
                reliability_tier=int(record.get("reliability_tier", 2)),
                verification_status="conflicting",
                confidence=1.0,
                needs_review=True,
                conflict_notes=f"当前值：{getattr(competition, field)!r}",
            )
            db.add(candidate)
            db.flush()
        exists = db.execute(
            select(ReviewQueue).where(
                ReviewQueue.item_type == "candidate_fact",
                ReviewQueue.item_id == candidate.id,
                ReviewQueue.status == "pending",
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                ReviewQueue(
                    item_type="candidate_fact",
                    item_id=candidate.id,
                    competition_id=competition.id,
                    status="pending",
                    reason="field_value_conflict",
                    raw_value=repr(value),
                    suggested_value=repr(getattr(competition, field)),
                    source_url=record["source_url"],
                    confidence=1.0,
                    is_demo=False,
                )
            )

    def _candidate_facts_from_lead(self, db: Session, lead: CompetitionLead, item: dict, authority: int) -> None:
        candidates = {
            "organizer": item.get("organizer"),
            "registration_start": item.get("registration_start"),
            "registration_deadline": item.get("registration_deadline"),
            "submission_deadline": item.get("submission_deadline"),
            "competition_start": item.get("competition_start"),
            "competition_end": item.get("competition_end"),
        }
        for field, value in candidates.items():
            if value is None:
                continue
            fact = db.execute(
                select(CandidateFact).where(
                    CandidateFact.lead_id == lead.id,
                    CandidateFact.field_name == field,
                    CandidateFact.source_url == lead.source_url,
                )
            ).scalar_one_or_none()
            payload = {
                "competition_id": lead.matched_competition_id,
                "competition_edition_id": None,
                "candidate_value": value,
                "source_type": lead.source_type,
                "reliability_tier": 4 if authority <= 2 else 3,
                "verification_status": "secondary_source_only",
                "confidence": 0.45 if authority <= 2 else 0.7,
                "needs_review": True,
                "conflict_notes": "发现字段，尚未由主办方或高校官方通知独立核验。",
            }
            if fact is None:
                db.add(CandidateFact(lead_id=lead.id, field_name=field, source_url=lead.source_url, **payload))
            else:
                for key, item_value in payload.items():
                    setattr(fact, key, item_value)

    def _domains(self, urls: set[str]) -> set[str]:
        return {urlparse(url).netloc.lower() for url in urls if urlparse(url).netloc}

    def _year(self, item: dict) -> int | None:
        for key in ("registration_start", "registration_deadline", "competition_start", "competition_end"):
            value = self._date(item.get(key))
            if value:
                return value.year
        return None

    def _date(self, value: object) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
