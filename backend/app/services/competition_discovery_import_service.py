from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionLead,
    CompetitionSource,
    University,
    UniversityCompetitionDiscoveryReport,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.source_authority_service import (
    authority_level_for,
    is_national_authority_source,
)

EXPECTED_985_COUNT = 39


class CompetitionDiscoveryImportService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()
        self.freshness = CompetitionFreshnessService()
        self.fact_service = FactIntelligenceService()

    def import_json(
        self,
        db: Session,
        seed_path: Path,
        universities_path: Path,
        *,
        batch_name: str | None = None,
    ) -> dict[str, Any]:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        university_payload = json.loads(universities_path.read_text(encoding="utf-8"))
        if isinstance(university_payload, dict):
            university_rows = university_payload.get("universities", [])
            expected_count = int(university_payload.get("expected_count", len(university_rows)))
            scope = university_payload.get("scope")
        else:
            university_rows = university_payload
            expected_count = EXPECTED_985_COUNT
            scope = "985"
        self._validate_universities(university_rows, expected_count=expected_count, scope=scope)
        batches = self._selected_batches(payload, batch_name)
        batch_names = {batch["name"] for batch in batches}
        observed_at = self._date(payload.get("retrieved_at")) or datetime.now(timezone.utc)

        stats: dict[str, Any] = {
            "batch_names": sorted(batch_names),
            "universities_seeded": 0,
            "universities_updated": 0,
            "reports_created": 0,
            "reports_updated": 0,
            "leads_created": 0,
            "leads_updated": 0,
            "official_records_promoted": 0,
            "competitions_created": 0,
            "editions_created": 0,
            "relations_created": 0,
            "relations_updated": 0,
            "sources_created": 0,
            "sources_updated": 0,
        }

        created, updated = self._upsert_universities(db, university_rows)
        stats["universities_seeded"] = created
        stats["universities_updated"] = updated

        for item in self._filter(payload.get("discovery_reports", []), batch_names):
            report, created_report = self._upsert_report(db, item, observed_at)
            key = "reports_created" if created_report else "reports_updated"
            stats[key] = int(stats[key]) + 1
            self._apply_report_to_university(report)

        for item in self._filter(payload.get("leads", []), batch_names):
            lead, created_lead = self.fact_service._upsert_lead(
                db,
                item,
                discovered_at=observed_at,
                source_type=item.get("source_type", "university_official"),
                source_platform=item.get("source_platform", "university_website"),
            )
            key = "leads_created" if created_lead else "leads_updated"
            stats[key] = int(stats[key]) + 1
            if lead.metadata_json is None:
                lead.metadata_json = {}
            lead.metadata_json.update(
                {
                    "university": item.get("university"),
                    "batch_name": item.get("batch_name"),
                    "discovery_batch": item.get("discovery_batch", item.get("batch_name")),
                    "source_scope": item.get("source_scope"),
                    "channel": item.get("channel"),
                }
            )

        for record in self._filter(payload.get("official_records", []), batch_names):
            before_ids = set(db.execute(select(Competition.id)).scalars().all())
            result = self.fact_service._promote_official_record(db, record, observed_at)
            stats["official_records_promoted"] = int(stats["official_records_promoted"]) + 1
            stats["competitions_created"] = int(stats["competitions_created"]) + int(result["competition_created"])
            stats["editions_created"] = int(stats["editions_created"]) + int(result["edition_created"])
            self._link_matching_leads(db, record)
            if result["competition_created"]:
                after_ids = set(db.execute(select(Competition.id)).scalars().all())
                created_ids = after_ids - before_ids
                for competition_id in created_ids:
                    competition = db.get(Competition, competition_id)
                    if competition:
                        competition.competition_level = competition.competition_level or record.get("competition_level")
                        competition.category = competition.category or record.get("category")

        for item in self._filter(payload.get("edition_relations", []), batch_names):
            result = self._upsert_relation(db, item, observed_at)
            if not result:
                continue
            stats["relations_created"] = int(stats["relations_created"]) + int(result["relation_created"])
            stats["relations_updated"] = int(stats["relations_updated"]) + int(not result["relation_created"])
            stats["sources_created"] = int(stats["sources_created"]) + int(result["source_created"])
            stats["sources_updated"] = int(stats["sources_updated"]) + int(not result["source_created"])

        if int(stats["relations_created"]) + int(stats["relations_updated"]) > 0:
            from app.services.school_competition_service import SchoolCompetitionService

            stats["school_competitions_rebuilt"] = SchoolCompetitionService().rebuild(db)

        db.flush()
        return stats

    def _selected_batches(self, payload: dict[str, Any], batch_name: str | None) -> list[dict[str, Any]]:
        batches = payload.get("batches", [])
        if batch_name is None:
            return batches
        selected = [batch for batch in batches if batch.get("name") == batch_name]
        if not selected:
            raise ValueError(f"Batch not found: {batch_name}")
        return selected

    def _filter(self, rows: list[dict[str, Any]], batch_names: set[str]) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("batch_name") in batch_names]

    def _validate_universities(
        self,
        rows: list[dict[str, Any]],
        *,
        expected_count: int,
        scope: str | None,
    ) -> None:
        names = [item["name"] for item in rows]
        domains = [item.get("official_domain") for item in rows if item.get("official_domain")]
        if len(rows) != expected_count:
            raise ValueError(f"Expected {expected_count} universities, got {len(rows)}")
        if len(set(names)) != len(names):
            raise ValueError("University seed contains duplicate names")
        if len(set(domains)) != len(domains):
            raise ValueError("University seed contains duplicate official domains")
        if scope == "211_non_985" and any(not item.get("is_211") or item.get("is_985") for item in rows):
            raise ValueError("211 non-985 seed contains an out-of-scope university")

    def _upsert_universities(self, db: Session, rows: list[dict[str, Any]]) -> tuple[int, int]:
        created = 0
        updated = 0
        for row in rows:
            university = db.execute(select(University).where(University.name == row["name"])).scalar_one_or_none()
            payload = {
                "short_name": row.get("short_name"),
                "english_name": row.get("english_name"),
                "aliases": row.get("aliases", []),
                "province": row.get("province"),
                "city": row.get("city"),
                "university_type": row.get("university_type", "综合类"),
                "is_985": bool(row.get("is_985", True)),
                "is_211": bool(row.get("is_211", True)),
                "is_double_first_class": bool(
                    row.get(
                        "is_double_first_class",
                        university.is_double_first_class if university is not None else False,
                    )
                ),
                "official_website": row.get("official_website"),
                "official_domain": row.get("official_domain"),
                "is_demo": False,
            }
            if university is None:
                db.add(University(name=row["name"], **payload))
                created += 1
            else:
                for key, value in payload.items():
                    setattr(university, key, value)
                updated += 1
        db.flush()
        return created, updated

    def _upsert_report(
        self,
        db: Session,
        item: dict[str, Any],
        observed_at: datetime,
    ) -> tuple[UniversityCompetitionDiscoveryReport, bool]:
        university = self._university(db, item["university"])
        report = db.execute(
            select(UniversityCompetitionDiscoveryReport).where(
                UniversityCompetitionDiscoveryReport.university_id == university.id,
                UniversityCompetitionDiscoveryReport.batch_name == item["batch_name"],
            )
        ).scalar_one_or_none()
        payload = {
            "status": item.get("status", "not_started"),
            "methods_attempted": item.get("methods_attempted") or [],
            "methods_successful": item.get("methods_successful") or [],
            "pages_examined": int(item.get("pages_examined", 0)),
            "candidate_articles": int(item.get("candidate_articles", 0)),
            "pages_searched": int(item.get("pages_searched", 0)),
            "competition_leads": int(item.get("competition_leads", 0)),
            "matched_competitions": int(item.get("matched_competitions", 0)),
            "new_competitions": int(item.get("new_competitions", 0)),
            "new_editions": int(item.get("new_editions", 0)),
            "internal_deadlines": int(item.get("internal_deadlines", 0)),
            "official_sources": int(item.get("official_sources", 0)),
            "university_notice_count": int(item.get("university_notice_count", 0)),
            "college_notice_count": int(item.get("college_notice_count", 0)),
            "current_registration_count": int(item.get("current_registration_count", 0)),
            "edition_2026_count": int(item.get("edition_2026_count", 0)),
            "wechat_leads": int(item.get("wechat_leads", 0)),
            "duplicate_leads": int(item.get("duplicate_leads", 0)),
            "errors_count": int(item.get("errors_count", 0)),
            "last_crawled_at": self._date(item.get("last_crawled_at")) or observed_at,
            "reason": item.get("reason"),
            "channel_stats": item.get("channel_stats") or {},
            "metadata_json": {
                "search_queries": item.get("search_queries", []),
                "source_domains": item.get("source_domains", []),
                "seed_version": item.get("seed_version", "v0.6"),
                "errors": item.get("errors", []),
            },
        }
        created = report is None
        if created:
            report = UniversityCompetitionDiscoveryReport(
                university_id=university.id,
                batch_name=item["batch_name"],
                **payload,
            )
            db.add(report)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(report, key, value)
        return report, created

    def _apply_report_to_university(self, report: UniversityCompetitionDiscoveryReport) -> None:
        university = report.university
        university.competition_discovery_status = report.status
        university.competition_discovery_started_at = university.competition_discovery_started_at or report.last_crawled_at
        university.last_competition_discovery_at = report.last_crawled_at
        university.competition_discovery_error = report.reason if report.status in {"failed", "blocked"} else None

    def _upsert_relation(
        self,
        db: Session,
        item: dict[str, Any],
        observed_at: datetime,
    ) -> dict[str, bool] | None:
        university = self._university(db, item["university"])
        competition = self._competition(db, item["competition_name"])
        if competition is None:
            self._ensure_pending_lead(db, item)
            return None
        official_proof = self._is_official_proof(item)
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == int(item.get("year", 2026)),
            )
        ).scalar_one_or_none()
        if edition is None and not official_proof:
            # A university notice cannot promote a new edition to the official
            # layer. Keep the discovery lead pending until S/A evidence exists.
            self._ensure_pending_lead(db, item, competition=competition)
            return None
        if edition is None:
            edition = CompetitionEdition(
                competition_id=competition.id,
                year=int(item.get("year", 2026)),
                edition_name=item.get("edition_name"),
                is_verified=True,
                verification_status="verified_official",
            )
            db.add(edition)
            db.flush()

        college = None
        if item.get("college_name"):
            college = self._upsert_college(db, university, item["college_name"], item.get("internal_notice_url"))

        internal_deadline = self._date(item.get("internal_registration_deadline"))
        official_deadline = self._date(item.get("official_registration_deadline"))
        notice_type = item.get("notice_type") or self._notice_type(item)
        current_status = item.get("current_status")
        if current_status in {"registration_open", "submission_open"} and internal_deadline is not None:
            self.freshness.update_edition_fact(
                db,
                edition,
                field_name="current_status",
                value=current_status,
                changed_at=observed_at,
                source_url=item["internal_notice_url"],
                source_name=item.get("source_name"),
            )
        relation = db.execute(
            select(UniversityCompetitionEditionRelation).where(
                UniversityCompetitionEditionRelation.university_id == university.id,
                UniversityCompetitionEditionRelation.competition_edition_id == edition.id,
                UniversityCompetitionEditionRelation.internal_notice_url == item["internal_notice_url"],
            )
        ).scalar_one_or_none()
        payload = {
            "college_id": college.id if college else None,
            "source_type": item.get("source_type", "university_official_notice"),
            "source_platform": item.get("source_platform", "university_website"),
            "source_name": item.get("source_name"),
            "notice_type": notice_type,
            "notice_title": item.get("notice_title") or item.get("raw_title") or item.get("edition_name"),
            "organizing_department": item.get("organizing_department"),
            "internal_contact": item.get("internal_contact"),
            "contact_person": item.get("contact_person"),
            "contact_method": item.get("contact_method") or item.get("internal_contact"),
            "internal_registration_start": self._date(item.get("internal_registration_start")),
            "internal_registration_deadline": internal_deadline,
            "internal_submission_deadline": self._date(item.get("internal_submission_deadline")),
            "college_registration_start": self._date(item.get("college_registration_start")),
            "college_registration_deadline": (
                self._date(item.get("college_registration_deadline"))
                or (internal_deadline if college is not None else None)
            ),
            "college_submission_deadline": self._date(item.get("college_submission_deadline")),
            "official_registration_deadline": official_deadline if official_proof else None,
            "published_at": self._date(item.get("published_at")),
            "observed_at": self._date(item.get("observed_at")) or observed_at,
            "last_verified_at": self._date(item.get("last_verified_at")) or observed_at,
            "last_seen_at": self._date(item.get("last_seen_at")) or observed_at,
            "source_hash": self._hash(json.dumps(item, ensure_ascii=False, sort_keys=True)),
            "verification_status": (
                "verified_official" if official_proof else "school_confirmed"
            ),
            "is_verified": bool(item.get("is_verified", True)),
            "is_demo": False,
            "metadata_json": {
                "batch_name": item.get("batch_name"),
                "discovery_batch": item.get("discovery_batch", item.get("batch_name")),
                "notes": item.get("notes"),
            },
        }
        relation_created = relation is None
        if relation_created:
            relation = UniversityCompetitionEditionRelation(
                university_id=university.id,
                competition_edition_id=edition.id,
                internal_notice_url=item["internal_notice_url"],
                **payload,
            )
            db.add(relation)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(relation, key, value)

        self._apply_relation_deadlines(
            db,
            edition,
            internal_deadline if college is None else None,
            official_deadline if official_proof else None,
            notice_type,
            official_proof,
            item,
            observed_at,
        )
        source_created = self._upsert_relation_source(
            db,
            competition,
            edition,
            item,
            observed_at,
            official_proof=official_proof,
        )
        self.freshness.mark_verified(
            edition,
            observed_at=observed_at,
            source_updated_at=self._date(item.get("published_at")),
        )
        self._link_lead_by_url(db, item.get("internal_notice_url"), competition, edition)
        return {"relation_created": relation_created, "source_created": source_created}

    def _apply_relation_deadlines(
        self,
        db: Session,
        edition: CompetitionEdition,
        internal_deadline: datetime | None,
        official_deadline: datetime | None,
        notice_type: str,
        official_proof: bool,
        item: dict[str, Any],
        observed_at: datetime,
    ) -> None:
        if notice_type not in {"registration_notice", "internal_selection", "submission_notice"}:
            return
        if official_deadline is not None and official_proof:
            self.freshness.update_edition_fact(
                db,
                edition,
                field_name="official_registration_deadline",
                value=official_deadline,
                changed_at=observed_at,
                source_url=item["internal_notice_url"],
                source_name=item.get("source_name"),
            )
        if internal_deadline is not None:
            if edition.university_registration_deadline is None:
                self.freshness.update_edition_fact(
                    db,
                    edition,
                    field_name="university_registration_deadline",
                    value=internal_deadline,
                    changed_at=observed_at,
                    source_url=item["internal_notice_url"],
                    source_name=item.get("source_name"),
                )
            elif internal_deadline < self._aware(edition.university_registration_deadline):
                self.freshness.update_edition_fact(
                    db,
                    edition,
                    field_name="university_registration_deadline",
                    value=internal_deadline,
                    changed_at=observed_at,
                    source_url=item["internal_notice_url"],
                    source_name=item.get("source_name"),
                )

    def _upsert_relation_source(
        self,
        db: Session,
        competition: Competition,
        edition: CompetitionEdition,
        item: dict[str, Any],
        observed_at: datetime,
        *,
        official_proof: bool,
    ) -> bool:
        source_url = item["internal_notice_url"]
        source = db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_id == competition.id,
                CompetitionSource.competition_edition_id == edition.id,
                CompetitionSource.source_url == source_url,
            )
        ).scalar_one_or_none()
        payload = {
            "source_type": item.get("source_type", "university_official_notice"),
            "source_name": item.get("source_name"),
            "source_platform": item.get("source_platform", "university_website"),
            "published_at": self._date(item.get("published_at")),
            "crawled_at": observed_at,
            "retrieved_at": observed_at,
            "authority_level": authority_level_for(
                item.get("source_type", "university_official_notice")
            ),
            "is_official": bool(official_proof),
            "is_verified": bool(item.get("is_verified", True)),
            "credibility_score": 100 if official_proof else 90,
            "reliability_tier": 1 if official_proof else 2,
            "verification_status": (
                "verified_official" if official_proof else "school_confirmed"
            ),
            "raw_title": item.get("raw_title") or item.get("edition_name") or competition.name,
            "content_hash": self._hash(json.dumps(item, ensure_ascii=False, sort_keys=True)),
            "metadata_json": {
                "university": item.get("university"),
                "batch_name": item.get("batch_name"),
                "source_scope": "official_notice" if official_proof else "university_notice",
                "proof_note": (
                    "S/A 官方来源，可证明全国赛事事实"
                    if official_proof
                    else "高校来源只能证明本校参赛事实，全国赛事事实需更高权威来源确认"
                ),
            },
            "is_demo": False,
        }
        created = source is None
        if created:
            db.add(
                CompetitionSource(
                    competition_id=competition.id,
                    competition_edition_id=edition.id,
                    source_url=source_url,
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(source, key, value)
        return created

    def _link_matching_leads(self, db: Session, record: dict[str, Any]) -> None:
        competition = self._competition(db, record["competition_name"])
        if competition is None:
            return
        edition_data = record.get("edition") or {}
        edition = None
        if edition_data.get("year"):
            edition = db.execute(
                select(CompetitionEdition).where(
                    CompetitionEdition.competition_id == competition.id,
                    CompetitionEdition.year == edition_data["year"],
                )
            ).scalar_one_or_none()
        self._link_lead_by_url(db, record.get("source_url"), competition, edition)

    def _link_lead_by_url(
        self,
        db: Session,
        source_url: str | None,
        competition: Competition,
        edition: CompetitionEdition | None,
    ) -> None:
        if not source_url:
            return
        leads = list(db.execute(select(CompetitionLead).where(CompetitionLead.source_url == source_url)).scalars())
        for lead in leads:
            lead.matched_competition_id = competition.id
            lead.matched_edition_id = edition.id if edition else None
            official = (
                competition.verification_status in {"verified_official", "authority_confirmed"}
                or (edition is not None and edition.verification_status == "verified_official")
            )
            lead.needs_review = not official
            lead.review_status = "verified" if official else "matched"
            lead.verification_status = "verified_official" if official else "secondary_source_only"

    def _is_official_proof(self, item: dict[str, Any]) -> bool:
        source_type = str(item.get("source_type") or "university_official_notice")
        return is_national_authority_source(source_type)

    def _ensure_pending_lead(
        self,
        db: Session,
        item: dict[str, Any],
        *,
        competition: Competition | None = None,
    ) -> None:
        """Keep unmatched / unverified discoveries in the discovery pool."""
        url = item.get("internal_notice_url") or item.get("source_url")
        title = (
            item.get("notice_title")
            or item.get("raw_title")
            or item.get("edition_name")
            or item.get("competition_name")
        )
        if not url or not title:
            return
        observed_at = self._date(item.get("observed_at")) or datetime.now(timezone.utc)
        lead = db.execute(
            select(CompetitionLead).where(
                CompetitionLead.source_url == url,
                CompetitionLead.raw_title == title,
            )
        ).scalar_one_or_none()
        payload = {
            "source_type": item.get("source_type", "university_official_notice"),
            "source_platform": item.get("source_platform", "university_website"),
            "source_name": item.get("source_name"),
            "published_at": self._date(item.get("published_at")),
            "discovered_at": observed_at,
            "detected_competition_name": item.get("competition_name"),
            "classification": item.get("notice_type") or "unknown",
            "review_status": "matched" if competition is not None else "pending",
            "verification_status": "unverified",
            "matched_competition_id": competition.id if competition is not None else None,
            "matched_edition_id": None,
            "needs_review": True,
            "notes": "高校通知只能作为发现线索；无官方来源确认前不得晋升为 verified_official。",
            "metadata_json": {
                "university": item.get("university"),
                "batch_name": item.get("batch_name"),
            },
        }
        if lead is None:
            db.add(CompetitionLead(raw_title=title, source_url=url, **payload))
            db.flush()
        else:
            for key, value in payload.items():
                setattr(lead, key, value)

    def _university(self, db: Session, name: str) -> University:
        university = db.execute(select(University).where(University.name == name)).scalar_one_or_none()
        if university is None:
            raise ValueError(f"University not seeded: {name}")
        return university

    def _competition(self, db: Session, name: str) -> Competition | None:
        normalization = self.normalizer.normalize(db, name)
        if normalization.competition is not None:
            return normalization.competition
        return db.execute(select(Competition).where(Competition.name == name)).scalar_one_or_none()

    def _upsert_college(self, db: Session, university: University, name: str, source_url: str | None) -> College:
        college = db.execute(
            select(College).where(College.university_id == university.id, College.name == name)
        ).scalar_one_or_none()
        payload = {"source_url": source_url, "is_verified": True, "is_demo": False}
        if college is None:
            college = College(university_id=university.id, name=name, **payload)
            db.add(college)
            db.flush()
        else:
            for key, value in payload.items():
                setattr(college, key, value)
        return college

    def _date(self, value: object) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _notice_type(self, item: dict[str, Any]) -> str:
        title = str(item.get("raw_title") or item.get("notice_title") or item.get("edition_name") or "")
        if any(token in title for token in ("获奖", "结果", "名单", "表彰")):
            return "award_news" if "获奖" in title or "表彰" in title else "result_notice"
        if any(token in title for token in ("培训", "训练营", "讲座")):
            return "training_notice"
        if any(token in title for token in ("招募", "组队", "队员")):
            return "team_recruitment"
        if any(token in title for token in ("作品提交", "提交作品", "投稿")):
            return "submission_notice"
        if any(token in title for token in ("校内选拔", "选拔赛", "校赛")):
            return "internal_selection"
        if any(token in title for token in ("报名", "组织参加", "参赛通知")):
            return "registration_notice"
        if any(token in title for token in ("公示", "公告", "通知")):
            return "competition_announcement"
        return "other"
