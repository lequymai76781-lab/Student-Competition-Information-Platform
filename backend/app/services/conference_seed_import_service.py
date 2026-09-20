"""Academic Conference V1 seed import & governance service.

Idempotent, additive importer for conference_series / conference_editions /
conference_sources / conference_organizations / school_conferences. It never
touches the competition module. Identity and risk rules live in
conference_authority_service; the importer only applies them.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConferenceDisciplineMapping,
    ConferenceDiscoveryCandidate,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceOrganization,
    ConferenceSeries,
    ConferenceSource,
    Organization,
    SchoolConference,
    University,
)
from app.services.conference_authority_service import (
    AUTHORITY_STATUSES,
    CONFERENCE_FREQUENCIES,
    CONFERENCE_ORGANIZATION_ROLES,
    CONFERENCE_SCOPES,
    CONFERENCE_SOURCE_TYPE_AUTHORITY,
    DISCOVERY_CANDIDATE_STATUSES,
    RISK_FLAG_VOCABULARY,
    authority_level_for,
    authority_status_from_sources,
    canonical_name_hint,
    is_discovery_only_source,
    summarize_indexing_claims,
    validate_audience,
    validate_discipline,
    validate_discipline_relationship,
    validate_discovery_entity_type,
    validate_opportunity_audience,
    validate_opportunity_evidence_status,
    validate_opportunity_status_hint,
    validate_opportunity_type,
    validate_recognition,
    validate_rejection_reason,
    validate_student_value_tags,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_org_name(name: str) -> str:
    normalized = name.strip().replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", normalized)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def validate_edition_payload(payload: dict[str, Any]) -> None:
    """Edition-level date guards: no inverted periods, no deadline after the
    conference period. Unknown fields stay NULL - this never invents dates."""
    start = _parse_date(payload.get("start_date"))
    end = _parse_date(payload.get("end_date"))
    if start and end and start > end:
        raise ValueError(
            f"Edition 会期倒置: start {payload.get('start_date')} > end {payload.get('end_date')}"
        )
    if end:
        for field in (
            "abstract_deadline",
            "paper_deadline",
            "notification_date",
            "camera_ready_deadline",
            "registration_deadline",
            "poster_deadline",
            "workshop_deadline",
        ):
            value = _parse_date(payload.get(field))
            if value and value > end:
                raise ValueError(
                    f"Edition 截止晚于会期: {field} {payload.get(field)} > end {payload.get('end_date')}"
                )


class ConferenceSeedImportService:
    """Reads data/seeds/conference_v1 JSON files and syncs them into the DB."""

    def __init__(self) -> None:
        self._org_created = False
        self._source_created = False
        self._school_created = 0
        self._school_updated = 0
        self._school_skipped: list[str] = []

    # ------------------------------------------------------------------ API
    def import_folder(self, db: Session, seed_dir: Path) -> dict[str, Any]:
        series_data = self._read_json(seed_dir / "series_seed.json")
        editions_data = self._read_json(seed_dir / "editions_seed.json")
        candidates_data = self._read_json(seed_dir / "discovery_candidates.json")
        mappings_data = self._read_json(seed_dir / "discipline_mappings.json")
        org_catalog = self._read_json(seed_dir / "organizations_catalog.json")

        series_stats = self.import_series(
            db,
            series_data["series"],
            org_catalog=org_catalog,
        )
        series_by_key: dict[str, ConferenceSeries] = {}
        for row in series_data["series"]:
            series = self._find_series(db, payload=row, exact_name=row["name"].strip())
            if series is None:
                raise ValueError(f"系列未导入成功，无法建立 key 映射: {row.get('key')!r}")
            series_by_key[row["key"]] = series
        edition_stats = self.import_editions(
            db,
            editions_data["editions"],
            series_by_key=series_by_key,
        )
        candidate_stats = self.import_candidates(
            db,
            candidates_data.get("candidates", []),
            org_catalog=org_catalog,
        )
        mapping_stats = self.import_discipline_mappings(
            db,
            mappings_data.get("mappings", []),
        )
        # Editions may have added S/A sources to Series; recompute identity once.
        for series in series_by_key.values():
            self._refresh_series_authority(db, series)
        stats: dict[str, Any] = {
            "series": series_stats,
            "editions": edition_stats,
            "candidates": candidate_stats,
            "discipline_mappings": mapping_stats,
        }
        db.commit()
        return stats

    # ----------------------------------------------------------------- read
    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"series": [], "editions": [], "candidates": [], "entries": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    # ------------------------------------------------------------- series
    def import_series(
        self,
        db: Session,
        rows: list[dict[str, Any]],
        *,
        org_catalog: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for payload in rows:
            name = payload["name"].strip()
            sources = payload.get("sources", [])
            for source in sources:
                source["_target"] = "series"

            series = self._find_series(db, payload=payload, exact_name=name)
            if series is None:
                series = ConferenceSeries(name=name)
                db.add(series)
                db.flush()
                counter["created"] += 1
            else:
                counter["updated"] += 1
                if series.name != name:
                    aliases = list(series.aliases or [])
                    if name not in aliases:
                        aliases.append(name)
                        series.aliases = aliases
                    counter["alias_linked"] += 1

            self._apply_series_fields(series, payload)
            for source in sources:
                self._upsert_source(db, series_id=series.id, edition_id=None, payload=source)
            self._sync_organizations(
                db,
                series_id=series.id,
                organizations=payload.get("organizations", []),
                org_catalog=org_catalog,
            )
            db.flush()
            self._refresh_series_authority(db, series)
        db.flush()
        return {
            "created": counter.get("created", 0),
            "updated": counter.get("updated", 0),
            "alias_linked": counter.get("alias_linked", 0),
            "series_key_unresolved": counter.get("series_key_unresolved", 0),
        }

    @staticmethod
    def _find_series(
        db: Session,
        *,
        payload: dict[str, Any],
        exact_name: str,
    ) -> ConferenceSeries | None:
        """Exact name first; then curated canonical alias groups (no fuzzy merge)."""
        series = db.execute(
            select(ConferenceSeries).where(ConferenceSeries.name == exact_name)
        ).scalar_one_or_none()
        if series is not None:
            return series
        canonical = canonical_name_hint(
            name=payload.get("name"),
            english_name=payload.get("english_name"),
            short_name=payload.get("short_name"),
            aliases=payload.get("aliases"),
        )
        if canonical is None:
            return None
        candidates = list(db.execute(select(ConferenceSeries)).scalars())
        for row in candidates:
            if row.name == canonical:
                return row
            group_tokens = {
                str(token).casefold()
                for token in [row.name, row.english_name, row.short_name, *(row.aliases or [])]
                if token and str(token).strip()
            }
            if canonical.casefold() in group_tokens:
                return row
        return None

    @staticmethod
    def _apply_series_fields(series: ConferenceSeries, payload: dict[str, Any]) -> None:
        discipline = validate_discipline(payload.get("discipline"))
        if "secondary_disciplines" in payload:
            secondary = []
            for code in payload.get("secondary_disciplines") or []:
                validated = validate_discipline(code)
                if validated and validated not in secondary and validated != discipline:
                    secondary.append(validated)
            series.secondary_disciplines = secondary or None
        if "discipline_evidence" in payload:
            series.discipline_evidence = payload.get("discipline_evidence") or None
        frequency = payload.get("conference_frequency") or None
        if frequency is not None and frequency not in CONFERENCE_FREQUENCIES:
            raise ValueError(f"未知会议频率: {frequency!r}")
        scope = payload.get("conference_scope") or None
        if scope is not None and scope not in CONFERENCE_SCOPES:
            raise ValueError(f"未知会议范围: {scope!r}")
        first_held = payload.get("first_held_year")
        if first_held is not None and (not isinstance(first_held, int) or first_held < 1900):
            raise ValueError(f"非法的首届年份: {first_held!r}")

        for field in (
            "english_name",
            "short_name",
            "subdiscipline",
            "organizer_summary",
            "official_website",
            "conference_frequency",
            "conference_scope",
            "description",
        ):
            setattr(series, field, payload.get(field))
        payload_aliases = [
            str(alias).strip()
            for alias in (payload.get("aliases") or [])
            if alias and str(alias).strip()
        ]
        merged_aliases = list(
            dict.fromkeys([*(series.aliases or []), *payload_aliases])
        )
        series.aliases = merged_aliases or None
        raw_classifications = payload.get("external_classifications") or []
        validated_classifications = [
            item
            for raw in raw_classifications
            if (item := validate_recognition(raw)) is not None
        ]
        series.external_classifications = validated_classifications or None
        if "student_value_tags" in payload:
            series.student_value_tags = validate_student_value_tags(
                payload.get("student_value_tags")
            ) or None
        if "audience" in payload:
            series.audience = validate_audience(payload.get("audience")) or None
        series.discipline = discipline
        series.is_international = bool(payload.get("is_international", False))
        series.first_held_year = first_held
        series.status = payload.get("status", "active")

    def _refresh_series_authority(self, db: Session, series: ConferenceSeries) -> None:
        sources = list(
            db.execute(
                select(ConferenceSource).where(
                    ConferenceSource.conference_series_id == series.id,
                    ConferenceSource.conference_edition_id.is_(None),
                )
            ).scalars()
        )
        # Edition sources are also attached to the series (series_id set), so
        # they contribute to Series identity only after editions are imported.
        edition_sources = list(
            db.execute(
                select(ConferenceSource).where(
                    ConferenceSource.conference_series_id == series.id,
                    ConferenceSource.conference_edition_id.is_not(None),
                )
            ).scalars()
        )
        all_sources = sources + edition_sources
        verified_types = [
            source.source_type
            for source in all_sources
            if authority_level_for(source.source_type) in {"S", "A"}
        ]
        status = authority_status_from_sources(verified_types, has_any_source=bool(all_sources))
        series.authority_status = status
        series.verification_status = status
        series.is_verified = status in {"verified_official", "authority_confirmed"}

        flags: list[str] = []
        if not any(
            authority_level_for(source.source_type) in {"S", "A"} for source in all_sources
        ):
            flags.append("official_site_missing" if not series.official_website else "official_org_missing")
        series.risk_flags = flags
        series.needs_review = bool(flags)
        series.last_verified_at = _utcnow() if series.is_verified else None

    # ------------------------------------------------------------ editions
    def import_editions(
        self,
        db: Session,
        rows: list[dict[str, Any]],
        *,
        series_by_key: dict[str, ConferenceSeries],
    ) -> dict[str, int]:
        self._school_created = 0
        self._school_updated = 0
        self._school_skipped = []
        counter: Counter[str] = Counter()
        for payload in rows:
            validate_edition_payload(payload)
            series_key = payload["series_key"]
            series = series_by_key.get(series_key)
            if series is None:
                counter["series_key_unresolved"] += 1
                continue

            year = int(payload["year"])
            edition = db.execute(
                select(ConferenceEdition).where(
                    ConferenceEdition.conference_series_id == series.id,
                    ConferenceEdition.year == year,
                )
            ).scalar_one_or_none()
            if edition is None:
                edition = ConferenceEdition(conference_series_id=series.id, year=year)
                db.add(edition)
                db.flush()
                counter["created"] += 1
            else:
                counter["updated"] += 1

            self._apply_edition_fields(edition, payload)
            for source in payload.get("sources", []):
                source["_target"] = "edition"
                self._upsert_source(
                    db,
                    series_id=series.id,
                    edition_id=edition.id,
                    payload=source,
                )
            db.flush()
            self._sync_school_relations(db, series, edition, payload.get("school_relations", []))
            self._sync_opportunities(db, edition, payload.get("opportunities", []))
            db.flush()
            self._refresh_edition_authority(db, edition)
            self._refresh_series_authority(db, series)
        db.flush()
        result = {
            "created": counter.get("created", 0),
            "updated": counter.get("updated", 0),
            "series_key_unresolved": counter.get("series_key_unresolved", 0),
        }
        result["school_relations_created"] = self._school_created
        result["school_relations_updated"] = self._school_updated
        result["school_relations_skipped"] = len(self._school_skipped)
        return result

    @staticmethod
    def _apply_edition_fields(edition: ConferenceEdition, payload: dict[str, Any]) -> None:
        for field in (
            "edition_name",
            "edition_number",
            "country_or_region",
            "city",
            "venue",
            "online_status",
            "call_for_papers_url",
            "edition_official_url",
            "registration_url",
            "publication_info",
            "publication_status",
            "publication_details",
            "indexing_info",
            "indexing_claims",
            "submission_language",
            "participation_type",
            "edition_status",
            "notes",
        ):
            value = payload.get(field)
            if field == "publication_status":
                value = value or "unknown"
            elif field == "edition_status":
                value = value or "unknown"
            setattr(edition, field, value)
        if "student_value_tags" in payload:
            edition.student_value_tags = validate_student_value_tags(
                payload.get("student_value_tags")
            ) or None
        if "audience" in payload:
            edition.audience = validate_audience(payload.get("audience")) or None
        if "participation_details" in payload:
            edition.participation_details = payload.get("participation_details")
        if "paper_details" in payload:
            edition.paper_details = payload.get("paper_details")
        for field in (
            "start_date",
            "end_date",
            "abstract_deadline",
            "paper_deadline",
            "notification_date",
            "camera_ready_deadline",
            "registration_deadline",
            "poster_deadline",
            "workshop_deadline",
        ):
            setattr(edition, field, _parse_date(payload.get(field)))
        edition.source_url = payload.get("edition_official_url")

    def _refresh_edition_authority(self, db: Session, edition: ConferenceEdition) -> None:
        sources = list(
            db.execute(
                select(ConferenceSource).where(
                    ConferenceSource.conference_edition_id == edition.id
                )
            ).scalars()
        )
        verified_types = [
            source.source_type
            for source in sources
            if authority_level_for(source.source_type) in {"S", "A"}
        ]
        status = authority_status_from_sources(verified_types, has_any_source=bool(sources))
        edition.authority_status = status
        edition.verification_status = status
        edition.is_verified = status in {"verified_official", "authority_confirmed"}

        flags: list[str] = []
        if not verified_types:
            flags.append("official_site_missing" if not edition.edition_official_url else "official_org_missing")
        edition.risk_flags = flags
        edition.needs_review = bool(flags)
        edition.last_verified_at = _utcnow() if edition.is_verified else None
        edition.indexing_claim_status = summarize_indexing_claims(edition.indexing_claims or [])
        if not edition.publication_status:
            edition.publication_status = "unknown"

    # ------------------------------------------------------------ sources
    def _upsert_source(
        self,
        db: Session,
        *,
        series_id: int,
        edition_id: int | None,
        payload: dict[str, Any],
    ) -> ConferenceSource:
        url = str(payload["source_url"]).strip()
        source_type = str(payload["source_type"]).strip()
        if source_type not in CONFERENCE_SOURCE_TYPE_AUTHORITY:
            raise ValueError(f"未知会议来源类型: {source_type!r}")
        level = authority_level_for(source_type)
        is_official = level in {"S", "A"}
        is_verified = is_official
        verification_status = {
            "S": "verified_official",
            "A": "authority_confirmed",
            "B": "pending_verification",
            "C": "discovery_only",
        }[level]

        existing = db.execute(
            select(ConferenceSource).where(
                ConferenceSource.source_url == url,
                ConferenceSource.conference_series_id == series_id,
            )
        ).scalars().all()
        row = next(
            (item for item in existing if item.conference_edition_id == edition_id),
            None,
        )
        if row is None and existing:
            row = existing[0]
        if row is None:
            row = ConferenceSource(
                conference_series_id=series_id,
                conference_edition_id=edition_id,
                source_url=url,
                source_type=source_type,
            )
            db.add(row)

        row.conference_series_id = series_id
        row.conference_edition_id = edition_id
        row.source_type = source_type
        row.authority_level = level
        row.source_name = payload.get("source_name")
        row.source_platform = payload.get("source_platform")
        row.official_domain = payload.get("official_domain")
        row.document_name = payload.get("document_name")
        row.published_at = _parse_date(payload.get("published_at"))
        row.retrieved_at = _parse_date(payload.get("retrieved_at")) or _utcnow()
        row.is_official = is_official
        row.is_verified = is_verified
        row.verification_status = verification_status
        row.raw_title = payload.get("raw_title")
        row.raw_content = payload.get("raw_content")
        row.metadata_json = payload.get("metadata_json")
        row.notes = payload.get("notes")
        row.content_hash = payload.get("content_hash")
        return row

    # ------------------------------------------------------ organizations
    def _sync_organizations(
        self,
        db: Session,
        *,
        series_id: int,
        organizations: list[dict[str, Any]],
        org_catalog: dict[str, Any] | None,
    ) -> None:
        entries = org_catalog.get("entries", []) if org_catalog else []
        by_name = {item["name"]: item for item in entries}
        for item in organizations:
            organization = self._upsert_organization(db, item["name"], catalog=by_name)
            if organization is None:
                continue
            role = str(item["role"]).strip()
            if role not in CONFERENCE_ORGANIZATION_ROLES:
                raise ValueError(f"未知会议组织机构角色: {role!r}")
            link = db.execute(
                select(ConferenceOrganization).where(
                    ConferenceOrganization.conference_series_id == series_id,
                    ConferenceOrganization.organization_id == organization.id,
                    ConferenceOrganization.role == role,
                )
            ).scalar_one_or_none()
            payload = {
                "display_name": item.get("display_name", item["name"]),
                "is_verified": bool(organization.is_verified),
                "source_url": item.get("source_url"),
            }
            if link is None:
                db.add(
                    ConferenceOrganization(
                        conference_series_id=series_id,
                        organization_id=organization.id,
                        role=role,
                        **payload,
                    )
                )
            else:
                for key, value in payload.items():
                    setattr(link, key, value)

    def _upsert_organization(
        self,
        db: Session,
        name: str,
        *,
        catalog: dict[str, Any],
    ) -> Organization | None:
        display_name = name.strip().strip("（）()[]")
        if not display_name:
            return None
        self._org_created = False
        organization = db.execute(
            select(Organization).where(Organization.name == display_name)
        ).scalar_one_or_none()
        if organization is None:
            rows = list(db.execute(select(Organization)).scalars())
            normalized = _normalize_org_name(display_name)
            organization = next(
                (row for row in rows if _normalize_org_name(row.name) == normalized),
                None,
            )
        catalog_item = catalog.get(display_name, {})
        org_type = catalog_item.get("org_type") or "other"
        website = catalog_item.get("official_website")
        domain = catalog_item.get("official_domain")
        if organization is None:
            organization = Organization(
                name=display_name,
                aliases=[] if display_name == name else [name],
                org_type=org_type,
                country_or_region=catalog_item.get("country_or_region"),
                official_website=website,
                official_domain=domain,
                is_verified=bool(website),
                is_demo=False,
            )
            db.add(organization)
            db.flush()
            self._org_created = True
        else:
            aliases = list(organization.aliases or [])
            if display_name != name and name not in aliases:
                aliases.append(name)
                organization.aliases = aliases
            if website and not organization.official_website:
                organization.official_website = website
            if domain and not organization.official_domain:
                organization.official_domain = domain
            if website and not organization.is_verified:
                organization.is_verified = True
            if catalog_item.get("org_type") and organization.org_type in {"other", None}:
                organization.org_type = catalog_item["org_type"]
        return organization

    # -------------------------------------------------- school relations
    def _sync_opportunities(
        self,
        db: Session,
        edition: ConferenceEdition,
        rows: list[dict[str, Any]],
    ) -> None:
        """Idempotent per-Edition opportunity sync (V1.2)."""
        for payload in rows:
            opportunity_type = validate_opportunity_type(payload.get("opportunity_type"))
            if opportunity_type is None:
                continue
            official_url = str(payload.get("official_url") or "").strip()
            if not official_url:
                raise ValueError(
                    f"Opportunity 缺少 official_url: edition={edition.id} type={opportunity_type}"
                )
            audience = validate_opportunity_audience(payload.get("audience"))
            evidence_status = validate_opportunity_evidence_status(
                payload.get("evidence_status")
            )
            source = self._opportunity_source(
                db, edition, payload.get("source"), official_url
            )
            row = db.execute(
                select(ConferenceOpportunity).where(
                    ConferenceOpportunity.conference_edition_id == edition.id,
                    ConferenceOpportunity.opportunity_type == opportunity_type,
                    ConferenceOpportunity.official_url == official_url,
                )
            ).scalar_one_or_none()
            if row is None:
                row = ConferenceOpportunity(
                    conference_edition_id=edition.id,
                    opportunity_type=opportunity_type,
                    official_url=official_url,
                )
                db.add(row)
            row.title = payload.get("title")
            row.official_label = payload.get("official_label")
            row.description = payload.get("description")
            row.audience = audience or None
            row.open_date = _parse_date(payload.get("open_date"))
            row.deadline = _parse_date(payload.get("deadline"))
            row.participation_mode = payload.get("participation_mode")
            row.evidence = payload.get("evidence")
            row.evidence_status = evidence_status
            row.notes = payload.get("notes")
            row.status_hint = validate_opportunity_status_hint(payload.get("status_hint"))
            if source is not None:
                row.source_id = source.id
            level = source.authority_level if source is not None else "C"
            full_evidence = evidence_status == "full_page_verified"
            if level in {"S", "A"} and full_evidence:
                row.verification_status = (
                    "verified_official" if level == "S" else "authority_confirmed"
                )
                row.is_verified = True
                row.needs_review = False
            elif level in {"S", "A"}:
                row.verification_status = "pending_verification"
                row.is_verified = False
                row.needs_review = True
            elif level == "B":
                row.verification_status = "pending_verification"
                row.is_verified = False
                row.needs_review = True
            else:
                row.verification_status = "discovery_only"
                row.is_verified = False
                row.needs_review = True
            last_verified = _parse_date(payload.get("last_verified_at"))
            if last_verified is not None:
                row.last_verified_at = last_verified
            elif row.last_verified_at is None and row.is_verified:
                row.last_verified_at = (
                    source.retrieved_at if source is not None else None
                ) or _utcnow()
            row.risk_flags = [
                flag
                for flag in (payload.get("risk_flags") or [])
                if flag in RISK_FLAG_VOCABULARY
            ] or None
            db.flush()

    def _opportunity_source(
        self,
        db: Session,
        edition: ConferenceEdition,
        source_payload: dict[str, Any] | None,
        official_url: str,
    ) -> ConferenceSource | None:
        if isinstance(source_payload, dict) and source_payload.get("source_url"):
            payload = {
                "source_type": source_payload.get("source_type", "conference_official_site"),
                "source_name": source_payload.get("source_name", "机会官方来源"),
                "source_url": source_payload["source_url"],
                "official_domain": source_payload.get("official_domain"),
                "notes": source_payload.get("notes"),
            }
            return self._upsert_source(
                db,
                series_id=edition.conference_series_id,
                edition_id=edition.id,
                payload=payload,
            )
        row = db.execute(
            select(ConferenceSource).where(
                ConferenceSource.conference_edition_id == edition.id,
                ConferenceSource.source_url == official_url,
            )
        ).scalars().first()
        return row

    def import_discipline_mappings(
        self,
        db: Session,
        rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for payload in rows:
            major_alias = str(payload.get("major_alias") or "").strip()
            discipline = validate_discipline(payload.get("discipline"))
            relationship_type = validate_discipline_relationship(
                payload.get("relationship_type") or "direct"
            )
            if not major_alias or discipline is None:
                continue
            row = db.execute(
                select(ConferenceDisciplineMapping).where(
                    ConferenceDisciplineMapping.major_alias == major_alias,
                    ConferenceDisciplineMapping.discipline == discipline,
                )
            ).scalar_one_or_none()
            if row is None:
                row = ConferenceDisciplineMapping(
                    major_alias=major_alias,
                    discipline=discipline,
                )
                db.add(row)
                counter["created"] += 1
            else:
                counter["updated"] += 1
            row.relationship_type = relationship_type
            row.mapping_basis = payload.get("mapping_basis")
            row.evidence = payload.get("evidence")
            row.source_url = payload.get("source_url")
            row.status = payload.get("status", "active")
        db.flush()
        return {
            "created": counter.get("created", 0),
            "updated": counter.get("updated", 0),
        }

    def _sync_school_relations(
        self,
        db: Session,
        series: ConferenceSeries,
        edition: ConferenceEdition,
        relations: list[dict[str, Any]],
    ) -> None:
        if not relations:
            return
        for item in relations:
            school = db.execute(
                select(University).where(University.name == item["school_name"])
            ).scalar_one_or_none()
            if school is None:
                if item["school_name"] not in self._school_skipped:
                    self._school_skipped.append(item["school_name"])
                continue
            notice_url = item.get("notice_url")
            source_type = item.get("source_type", "university_official")
            if notice_url:
                source = self._upsert_source(
                    db,
                    series_id=series.id,
                    edition_id=edition.id,
                    payload={
                        "source_type": source_type,
                        "source_url": notice_url,
                        "official_domain": _domain_of(notice_url),
                        "source_name": item.get("source_name", "高校官网通知"),
                        "notes": item.get("notes"),
                    },
                )
            else:
                source = db.execute(
                    select(ConferenceSource).where(
                        ConferenceSource.conference_edition_id == edition.id,
                        ConferenceSource.authority_level.in_(("S", "A")),
                    )
                ).scalars().first()
            if source is None and notice_url is None:
                continue

            existing = db.execute(
                select(SchoolConference).where(
                    SchoolConference.school_id == school.id,
                    SchoolConference.conference_edition_id == edition.id,
                    SchoolConference.notice_url.is_(None)
                    if notice_url is None
                    else SchoolConference.notice_url == notice_url,
                )
            ).scalars().first()
            if existing is None and notice_url is None:
                existing = db.execute(
                    select(SchoolConference).where(
                        SchoolConference.school_id == school.id,
                        SchoolConference.conference_edition_id == edition.id,
                        SchoolConference.relation_type == item["relation_type"],
                    )
                ).scalars().first()
            payload = {
                "conference_series_id": series.id,
                "relation_type": item["relation_type"],
                "responsible_department": item.get("responsible_department"),
                "responsible_college": item.get("responsible_college"),
                "notice_url": notice_url,
                "notes": item.get("notes"),
                "source_id": source.id if source else None,
                "is_verified": True,
                "verification_status": "school_confirmed",
                "verified_at": _utcnow(),
            }
            if existing is None:
                db.add(
                    SchoolConference(
                        school_id=school.id,
                        conference_edition_id=edition.id,
                        **payload,
                    )
                )
                self._school_created += 1
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                self._school_updated += 1

    # ----------------------------------------------------------- candidates
    def import_candidates(
        self,
        db: Session,
        rows: list[dict[str, Any]],
        *,
        org_catalog: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for payload in rows:
            url = str(payload["source_url"]).strip()
            existing = db.execute(
                select(ConferenceDiscoveryCandidate).where(
                    ConferenceDiscoveryCandidate.raw_name == payload["raw_name"],
                    ConferenceDiscoveryCandidate.source_url == url,
                )
            ).scalar_one_or_none()
            if existing is None:
                source_type = payload["source_type"]
                if source_type not in CONFERENCE_SOURCE_TYPE_AUTHORITY:
                    raise ValueError(f"未知来源类型: {source_type!r}")
                if not is_discovery_only_source(source_type):
                    raise ValueError("正式来源候选请走 Series/Edition 导入，不进发现池")
                status = payload.get("status", "pending")
                if status not in DISCOVERY_CANDIDATE_STATUSES:
                    raise ValueError(f"未知候选状态: {status!r}")
                rejection_reason = validate_rejection_reason(payload.get("rejection_reason"))
                if status == "rejected" and not rejection_reason:
                    raise ValueError("rejected 候选必须提供 rejection_reason")
                db.add(
                    ConferenceDiscoveryCandidate(
                        raw_name=payload["raw_name"],
                        year=payload.get("year"),
                        acronym=payload.get("acronym"),
                        english_name=payload.get("english_name"),
                        organizer_hint=payload.get("organizer_hint"),
                        discipline_hint=payload.get("discipline_hint"),
                        source_type=source_type,
                        source_name=payload.get("source_name"),
                        source_url=url,
                        source_domain=payload.get("source_domain"),
                        status=status,
                        needs_review=payload.get("needs_review", True),
                        risk_flags=self._validate_risk_flags(payload.get("risk_flags")),
                        rejection_reason=rejection_reason,
                        notes=payload.get("notes"),
                        discovered_at=_utcnow(),
                        entity_type=validate_discovery_entity_type(
                            payload.get("entity_type")
                        ),
                        metadata_json=payload.get("metadata_json"),
                    )
                )
                counter["created"] += 1
            else:
                status = payload.get("status", existing.status)
                if status not in DISCOVERY_CANDIDATE_STATUSES:
                    raise ValueError(f"未知候选状态: {status!r}")
                rejection_reason = validate_rejection_reason(
                    payload.get("rejection_reason", existing.rejection_reason)
                )
                if status == "rejected" and not rejection_reason:
                    raise ValueError("rejected 候选必须提供 rejection_reason")
                existing.status = status
                existing.rejection_reason = rejection_reason
                existing.entity_type = validate_discovery_entity_type(
                    payload.get("entity_type", existing.entity_type)
                )
                if payload.get("metadata_json") is not None:
                    existing.metadata_json = payload["metadata_json"]
                existing.needs_review = bool(
                    payload.get("needs_review", status in {"pending", "reviewing"})
                )
                counter["updated"] += 1
        db.flush()
        return {
            "created": counter.get("created", 0),
            "updated": counter.get("updated", 0),
        }

    @staticmethod
    def _validate_risk_flags(flags: list[str] | None) -> list[str] | None:
        if not flags:
            return None
        unknown = [flag for flag in flags if flag not in RISK_FLAG_VOCABULARY]
        if unknown:
            raise ValueError(f"未知风险标记: {unknown}")
        return list(dict.fromkeys(flags))


def _domain_of(url: str) -> str | None:
    match = re.match(r"https?://([^/:?#]+)", url)
    if not match:
        return None
    return match.group(1).lower()


def authority_status_values() -> list[str]:
    return list(AUTHORITY_STATUSES)
