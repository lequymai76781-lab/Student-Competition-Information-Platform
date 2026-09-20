"""Academic Conference V1 read service (basic internal APIs)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

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
    CONFERENCE_DISCIPLINES,
    CONFERENCE_SOURCE_TYPE_AUTHORITY,
    edition_actionable_status,
    edition_lifecycle_status,
    opportunity_status,
    recognition_summary,
    student_opportunity_tags,
    value_reason_type_for_opportunity,
)


class ConferenceService:
    @staticmethod
    def list_disciplines() -> list[dict[str, str]]:
        return [
            {"code": code, **CONFERENCE_DISCIPLINES[code]}
            for code in CONFERENCE_DISCIPLINES
        ]

    def list_series(
        self,
        db: Session,
        *,
        keyword: str | None = None,
        discipline: str | None = None,
        primary_discipline: str | None = None,
        is_international: bool | None = None,
        authority_status: str | None = None,
        verification_status: str | None = None,
        organization: str | None = None,
        year: int | None = None,
        country: str | None = None,
        student_value_tag: str | None = None,
        recognition_level: str | None = None,
        has_official_source: bool | None = None,
        has_submission: bool | None = None,
        has_student_track: bool | None = None,
        has_poster: bool | None = None,
        has_registration: bool | None = None,
        actionable: bool | None = None,
        has_opportunity: bool | None = None,
        opportunity_type: str | None = None,
        opportunity_audience: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if primary_discipline:
            resolved = self._resolve_discipline(primary_discipline)
            if resolved is None:
                return [], 0
            if discipline and discipline != resolved:
                return [], 0
            discipline = resolved
        stmt = select(ConferenceSeries)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    ConferenceSeries.name.ilike(pattern),
                    ConferenceSeries.english_name.ilike(pattern),
                    ConferenceSeries.short_name.ilike(pattern),
                    ConferenceSeries.organizer_summary.ilike(pattern),
                )
            )
        if discipline:
            stmt = stmt.where(ConferenceSeries.discipline == discipline)
        if is_international is not None:
            stmt = stmt.where(ConferenceSeries.is_international.is_(is_international))
        if authority_status:
            stmt = stmt.where(ConferenceSeries.authority_status == authority_status)
        if verification_status:
            stmt = stmt.where(ConferenceSeries.verification_status == verification_status)
        if organization:
            org_rows = list(db.execute(select(Organization)).scalars())
            matched_org_ids = [
                row.id
                for row in org_rows
                if organization.strip().casefold() in str(row.name).casefold()
                or any(
                    organization.strip().casefold() in str(alias).casefold()
                    for alias in (row.aliases or [])
                )
            ]
            if not matched_org_ids:
                return [], 0
            stmt = stmt.where(
                ConferenceSeries.conference_organizations.any(
                    ConferenceOrganization.organization_id.in_(matched_org_ids)
                )
            )
        if year is not None:
            stmt = stmt.where(ConferenceSeries.editions.any(ConferenceEdition.year == year))
        if country:
            pattern = f"%{country.strip()}%"
            stmt = stmt.where(
                ConferenceSeries.editions.any(
                    or_(
                        ConferenceEdition.country_or_region.ilike(pattern),
                        ConferenceEdition.city.ilike(pattern),
                    )
                )
            )
        if has_official_source:
            stmt = stmt.where(
                ConferenceSeries.sources.any(
                    ConferenceSource.authority_level.in_(("S", "A"))
                )
            )

        needs_python_filter = bool(
            student_value_tag
            or recognition_level
            or has_submission is not None
            or has_student_track is not None
            or has_poster is not None
            or has_registration is not None
            or actionable is not None
            or has_opportunity is not None
            or opportunity_type is not None
            or opportunity_audience is not None
        )
        if needs_python_filter:
            rows = list(db.execute(stmt.order_by(ConferenceSeries.id)).scalars())
        else:
            rows = list(
                db.execute(
                    stmt.order_by(ConferenceSeries.id).limit(limit).offset(offset)
                ).scalars()
            )
        series_ids = [row.id for row in rows]

        edition_stats: dict[int, tuple[int, int | None]] = {}
        source_counts: dict[int, int] = {}
        edition_tags: dict[int, list[str]] = {}
        if series_ids:
            for series_id, count, latest in db.execute(
                select(
                    ConferenceEdition.conference_series_id,
                    func.count(ConferenceEdition.id),
                    func.max(ConferenceEdition.year),
                )
                .where(ConferenceEdition.conference_series_id.in_(series_ids))
                .group_by(ConferenceEdition.conference_series_id)
            ).all():
                edition_stats[series_id] = (count, latest)
            for series_id, count in db.execute(
                select(
                    ConferenceSource.conference_series_id,
                    func.count(ConferenceSource.id),
                )
                .where(
                    ConferenceSource.conference_series_id.in_(series_ids),
                    ConferenceSource.authority_level.in_(("S", "A")),
                )
                .group_by(ConferenceSource.conference_series_id)
            ).all():
                source_counts[series_id] = count
            if student_value_tag:
                for series_id, tags in db.execute(
                    select(
                        ConferenceEdition.conference_series_id,
                        ConferenceEdition.student_value_tags,
                    )
                    .where(ConferenceEdition.conference_series_id.in_(series_ids))
                ).all():
                    edition_tags.setdefault(series_id, []).extend(tags or [])

        payload = []
        for row in rows:
            edition_count, latest_year = edition_stats.get(row.id, (0, None))
            payload.append(
                self._series_payload(
                    row,
                    edition_count=edition_count,
                    latest_edition_year=latest_year,
                    official_source_count=source_counts.get(row.id, 0),
                )
            )
        if student_value_tag:
            payload = [
                item
                for item in payload
                if student_value_tag in (item.get("student_value_tags") or [])
                or student_value_tag in edition_tags.get(item["id"], [])
            ]
        if recognition_level:
            wanted = recognition_level.strip().casefold()
            payload = [
                item
                for item in payload
                if any(
                    (
                        str(rec.get("level", "")).casefold() == wanted
                        or f"{rec.get('system')}-{rec.get('level')}".casefold() == wanted
                    )
                    for rec in item.get("recognition") or []
                )
            ]
        if (
            has_submission is not None
            or has_student_track is not None
            or has_poster is not None
            or has_registration is not None
            or actionable is not None
            or has_opportunity is not None
            or opportunity_type is not None
            or opportunity_audience is not None
        ):
            features = self._series_feature_map(db, [item["id"] for item in payload])
            opp_map = self._series_opportunity_map(db, [item["id"] for item in payload])
            filtered: list[dict[str, Any]] = []
            for item in payload:
                flags = features.get(item["id"], {})
                if has_submission is not None and bool(flags.get("has_submission")) != has_submission:
                    continue
                if (
                    has_student_track is not None
                    and bool(flags.get("has_student_track")) != has_student_track
                ):
                    continue
                if has_poster is not None and bool(flags.get("has_poster")) != has_poster:
                    continue
                if (
                    has_registration is not None
                    and bool(flags.get("has_registration")) != has_registration
                ):
                    continue
                if actionable is not None and bool(flags.get("actionable")) != actionable:
                    continue
                opp_info = opp_map.get(item["id"], {})
                if has_opportunity is not None and bool(opp_info.get("has_opportunity")) != has_opportunity:
                    continue
                if opportunity_type is not None and opportunity_type not in opp_info.get(
                    "types", []
                ):
                    continue
                if opportunity_audience is not None and opportunity_audience not in opp_info.get(
                    "audiences", []
                ):
                    continue
                filtered.append(item)
            payload = filtered
        if needs_python_filter:
            total = len(payload)
            return payload[offset : offset + limit], total
        return (
            payload,
            db.scalar(select(func.count()).select_from(stmt.subquery())) or 0,
        )

    def get_series(self, db: Session, series_id: int) -> dict[str, Any]:
        row = db.execute(
            select(ConferenceSeries)
            .where(ConferenceSeries.id == series_id)
            .options(
                selectinload(ConferenceSeries.editions),
                selectinload(ConferenceSeries.sources),
                selectinload(ConferenceSeries.conference_organizations).selectinload(
                    ConferenceOrganization.organization
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="会议系列不存在")
        school_count = db.scalar(
            select(func.count())
            .select_from(SchoolConference)
            .where(SchoolConference.conference_series_id == series_id)
        ) or 0
        payload = self._series_payload(
            row,
            edition_count=len(row.editions),
            latest_edition_year=max((e.year for e in row.editions), default=None),
            official_source_count=sum(
                1 for s in row.sources if s.authority_level in {"S", "A"}
            ),
        )
        payload["editions"] = [
            self._edition_payload(edition, series_name=row.name) for edition in row.editions
        ]
        payload["organizations"] = [
            {
                "id": link.id,
                "role": link.role,
                "display_name": link.display_name,
                "is_verified": link.is_verified,
                "source_url": link.source_url,
                "organization_name": link.organization.name if link.organization else None,
                "official_domain": link.organization.official_domain
                if link.organization
                else None,
            }
            for link in sorted(
                row.conference_organizations,
                key=lambda item: (item.role, item.id),
            )
        ]
        payload["sources"] = [
            {
                key: getattr(source, key)
                for key in (
                    "id",
                    "conference_series_id",
                    "conference_edition_id",
                    "source_type",
                    "authority_level",
                    "source_name",
                    "source_url",
                    "source_platform",
                    "official_domain",
                    "document_name",
                    "published_at",
                    "retrieved_at",
                    "is_official",
                    "is_verified",
                    "verification_status",
                    "raw_title",
                    "metadata_json",
                    "notes",
                )
            }
            for source in row.sources
        ]
        payload["school_relation_count"] = school_count
        return payload

    def list_editions(
        self,
        db: Session,
        *,
        series_id: int | None = None,
        year: int | None = None,
        discipline: str | None = None,
        primary_discipline: str | None = None,
        organization: str | None = None,
        country: str | None = None,
        verification_status: str | None = None,
        student_value_tag: str | None = None,
        recognition_level: str | None = None,
        has_cfp: bool | None = None,
        has_paper_deadline: bool | None = None,
        has_registration_deadline: bool | None = None,
        has_dates: bool | None = None,
        has_location: bool | None = None,
        has_submission: bool | None = None,
        has_student_track: bool | None = None,
        has_poster: bool | None = None,
        has_registration: bool | None = None,
        actionable: bool | None = None,
        has_opportunity: bool | None = None,
        opportunity_type: str | None = None,
        opportunity_audience: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if primary_discipline:
            resolved = self._resolve_discipline(primary_discipline)
            if resolved is None:
                return [], 0
            if discipline and discipline != resolved:
                return [], 0
            discipline = resolved
        stmt = (
            select(ConferenceEdition, ConferenceSeries)
            .join(ConferenceSeries, ConferenceEdition.conference_series_id == ConferenceSeries.id)
        )
        if series_id is not None:
            stmt = stmt.where(ConferenceEdition.conference_series_id == series_id)
        if year is not None:
            stmt = stmt.where(ConferenceEdition.year == year)
        if discipline:
            stmt = stmt.where(ConferenceSeries.discipline == discipline)
        if organization:
            org_rows = list(db.execute(select(Organization)).scalars())
            needle = organization.strip().casefold()
            matched_org_ids = [
                row.id
                for row in org_rows
                if needle in str(row.name).casefold()
                or any(needle in str(alias).casefold() for alias in (row.aliases or []))
            ]
            if not matched_org_ids:
                return [], 0
            stmt = stmt.where(
                ConferenceSeries.conference_organizations.any(
                    ConferenceOrganization.organization_id.in_(matched_org_ids)
                )
            )
        if country:
            pattern = f"%{country.strip()}%"
            stmt = stmt.where(
                or_(
                    ConferenceEdition.country_or_region.ilike(pattern),
                    ConferenceEdition.city.ilike(pattern),
                )
            )
        if verification_status:
            stmt = stmt.where(ConferenceEdition.verification_status == verification_status)
        if has_cfp:
            stmt = stmt.where(ConferenceEdition.call_for_papers_url.is_not(None))
        if has_paper_deadline:
            stmt = stmt.where(ConferenceEdition.paper_deadline.is_not(None))
        if has_registration_deadline:
            stmt = stmt.where(ConferenceEdition.registration_deadline.is_not(None))
        if has_dates:
            stmt = stmt.where(
                ConferenceEdition.start_date.is_not(None),
                ConferenceEdition.end_date.is_not(None),
            )
        if has_location:
            stmt = stmt.where(
                or_(
                    ConferenceEdition.city.is_not(None),
                    ConferenceEdition.venue.is_not(None),
                    ConferenceEdition.location.is_not(None),
                )
            )
        needs_python_filter = bool(
            student_value_tag
            or recognition_level
            or has_submission is not None
            or has_student_track is not None
            or has_poster is not None
            or has_registration is not None
            or actionable is not None
            or has_opportunity is not None
            or opportunity_type is not None
            or opportunity_audience is not None
        )
        if needs_python_filter:
            rows = db.execute(
                stmt.order_by(ConferenceEdition.year.desc(), ConferenceEdition.id.desc())
            ).all()
        else:
            rows = db.execute(
                stmt.order_by(ConferenceEdition.year.desc(), ConferenceEdition.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        payload = []
        for edition, series in rows:
            item = self._edition_payload(edition, series_name=series.name)
            if student_value_tag and student_value_tag not in (edition.student_value_tags or []):
                continue
            if recognition_level:
                wanted = recognition_level.strip().casefold()
                matches = any(
                    str(rec.get("level", "")).casefold() == wanted
                    or f"{rec.get('system')}-{rec.get('level')}".casefold() == wanted
                    for rec in recognition_summary(series.external_classifications)
                )
                if not matches:
                    continue
            flags = self._edition_flags(edition)
            if has_submission is not None and flags["has_submission"] != has_submission:
                continue
            if (
                has_student_track is not None
                and flags["has_student_track"] != has_student_track
            ):
                continue
            if has_poster is not None and flags["has_poster"] != has_poster:
                continue
            if has_registration is not None and flags["has_registration"] != has_registration:
                continue
            if actionable is not None:
                active = edition_actionable_status(edition) in {"open", "upcoming"} or (
                    self._edition_has_active_opportunity(db, edition)
                )
                if active != actionable:
                    continue
            opp_info = self._edition_opportunity_info(db, edition.id)
            if has_opportunity is not None and bool(
                opp_info.get("has_opportunity")
            ) != has_opportunity:
                continue
            if opportunity_type is not None and opportunity_type not in opp_info.get(
                "types", []
            ):
                continue
            if opportunity_audience is not None and opportunity_audience not in opp_info.get(
                "audiences", []
            ):
                continue
            payload.append(item)
        if needs_python_filter:
            total = len(payload)
            return payload[offset : offset + limit], total
        return (
            payload,
            db.scalar(select(func.count()).select_from(stmt.subquery())) or 0,
        )

    def get_edition(self, db: Session, edition_id: int) -> dict[str, Any]:
        row = db.execute(
            select(ConferenceEdition, ConferenceSeries.name)
            .join(ConferenceSeries, ConferenceEdition.conference_series_id == ConferenceSeries.id)
            .where(ConferenceEdition.id == edition_id)
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="会议届次不存在")
        edition, series_name = row
        return self._edition_payload(edition, series_name=series_name)

    @staticmethod
    def _resolve_discipline(value: str) -> str | None:
        """Accept a controlled code or its zh/en display name (primary alias)."""
        needle = value.strip().casefold()
        for code, meta in CONFERENCE_DISCIPLINES.items():
            if (
                needle == code.casefold()
                or needle == str(meta["name_zh"]).casefold()
                or needle == str(meta["name_en"]).casefold()
            ):
                return code
        return None

    @staticmethod
    def _edition_flags(edition: ConferenceEdition) -> dict[str, bool]:
        tags = list(edition.student_value_tags or [])
        opportunity = set(student_opportunity_tags(tags))
        return {
            "has_submission": bool(
                edition.abstract_deadline
                or edition.paper_deadline
                or edition.call_for_papers_url
                or "paper_submission" in tags
                or "student_paper" in tags
            ),
            "has_student_track": bool(opportunity),
            "has_poster": bool(edition.poster_deadline or "poster" in tags),
            "has_registration": bool(
                edition.registration_deadline or edition.registration_url
            ),
        }

    def _series_feature_map(
        self, db: Session, series_ids: list[int]
    ) -> dict[int, dict[str, bool]]:
        """Aggregate Edition-level opportunity flags onto their Series."""
        result: dict[int, dict[str, bool]] = {}
        if not series_ids:
            return result
        edition_rows = list(
            db.execute(
                select(ConferenceEdition).where(
                    ConferenceEdition.conference_series_id.in_(series_ids)
                )
            ).scalars()
        )
        for edition in edition_rows:
            series_id = edition.conference_series_id
            flags = result.setdefault(
                series_id,
                {
                    "has_submission": False,
                    "has_student_track": False,
                    "has_poster": False,
                    "has_registration": False,
                    "actionable": False,
                },
            )
            item = self._edition_flags(edition)
            for key in ("has_submission", "has_student_track", "has_poster", "has_registration"):
                flags[key] = flags[key] or item[key]
            if edition_actionable_status(edition) in {"open", "upcoming"}:
                flags["actionable"] = True
        edition_ids = [row.id for row in edition_rows]
        if edition_ids:
            opp_rows = list(
                db.execute(
                    select(ConferenceOpportunity, ConferenceEdition)
                    .join(
                        ConferenceEdition,
                        ConferenceOpportunity.conference_edition_id
                        == ConferenceEdition.id,
                    )
                    .where(ConferenceEdition.id.in_(edition_ids))
                ).all()
            )
            for opportunity, edition in opp_rows:
                if opportunity_status(
                    opportunity, edition=edition
                ) in {"open", "closing_soon", "upcoming"}:
                    result.setdefault(
                        edition.conference_series_id,
                        {
                            "has_submission": False,
                            "has_student_track": False,
                            "has_poster": False,
                            "has_registration": False,
                            "actionable": False,
                        },
                    )["actionable"] = True
        return result

    @staticmethod
    def _edition_opportunity_info(
        db: Session, edition_id: int
    ) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(ConferenceOpportunity).where(
                    ConferenceOpportunity.conference_edition_id == edition_id
                )
            ).scalars()
        )
        return {
            "has_opportunity": bool(rows),
            "types": sorted({row.opportunity_type for row in rows}),
            "audiences": sorted(
                {
                    audience
                    for row in rows
                    for audience in (row.audience or [])
                }
            ),
        }

    @staticmethod
    def _edition_has_active_opportunity(
        db: Session, edition: ConferenceEdition
    ) -> bool:
        rows = list(
            db.execute(
                select(ConferenceOpportunity).where(
                    ConferenceOpportunity.conference_edition_id == edition.id
                )
            ).scalars()
        )
        return any(
            opportunity_status(row, edition=edition)
            in {"open", "closing_soon", "upcoming"}
            for row in rows
        )

    def _series_opportunity_map(
        self, db: Session, series_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        if not series_ids:
            return result
        rows = list(
            db.execute(
                select(ConferenceOpportunity, ConferenceEdition)
                .join(
                    ConferenceEdition,
                    ConferenceOpportunity.conference_edition_id
                    == ConferenceEdition.id,
                )
                .where(ConferenceEdition.conference_series_id.in_(series_ids))
            ).all()
        )
        for opportunity, edition in rows:
            info = result.setdefault(
                edition.conference_series_id,
                {
                    "has_opportunity": False,
                    "types": set(),
                    "audiences": set(),
                },
            )
            info["has_opportunity"] = True
            info["types"].add(opportunity.opportunity_type)
            info["audiences"].update(opportunity.audience or [])
        for info in result.values():
            info["types"] = sorted(info["types"])
            info["audiences"] = sorted(info["audiences"])
        return result

    def list_opportunities(
        self,
        db: Session,
        *,
        edition_id: int | None = None,
        series_id: int | None = None,
        opportunity_type: str | None = None,
        audience: str | None = None,
        status: str | None = None,
        year: int | None = None,
        discipline: str | None = None,
        primary_discipline: str | None = None,
        actionable: bool | None = None,
        verified_only: bool | None = None,
        verified_after: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = (
            select(ConferenceOpportunity, ConferenceEdition, ConferenceSeries)
            .join(
                ConferenceEdition,
                ConferenceOpportunity.conference_edition_id == ConferenceEdition.id,
            )
            .join(
                ConferenceSeries,
                ConferenceEdition.conference_series_id == ConferenceSeries.id,
            )
        )
        if edition_id is not None:
            stmt = stmt.where(ConferenceOpportunity.conference_edition_id == edition_id)
        if series_id is not None:
            stmt = stmt.where(ConferenceSeries.id == series_id)
        if opportunity_type:
            stmt = stmt.where(ConferenceOpportunity.opportunity_type == opportunity_type)
        if year is not None:
            stmt = stmt.where(ConferenceEdition.year == year)
        if discipline:
            stmt = stmt.where(ConferenceSeries.discipline == discipline)
        if primary_discipline:
            resolved = self._resolve_discipline(primary_discipline)
            if resolved is None:
                return [], 0
            stmt = stmt.where(ConferenceSeries.discipline == resolved)
        rows = list(db.execute(stmt.order_by(ConferenceOpportunity.id)).all())
        payload: list[dict[str, Any]] = []
        for opportunity, edition, series in rows:
            opp_status = opportunity_status(opportunity, edition=edition)
            if status is not None and opp_status != status:
                continue
            if audience is not None and audience not in (opportunity.audience or []):
                continue
            if actionable is not None:
                active = opp_status in {"open", "closing_soon", "upcoming"}
                if active != actionable:
                    continue
            if verified_only is not None and opportunity.is_verified != verified_only:
                continue
            if verified_after is not None:
                last_verified = self._to_naive_utc(opportunity.last_verified_at)
                if last_verified is None or last_verified < self._to_naive_utc(
                    verified_after
                ):
                    continue
            item = self._opportunity_payload(
                opportunity,
                edition=edition,
                series=series,
                status=opp_status,
            )
            payload.append(item)
        total = len(payload)
        return payload[offset : offset + limit], total

    @staticmethod
    def _opportunity_payload(
        opportunity: ConferenceOpportunity,
        *,
        edition: ConferenceEdition | None = None,
        series: ConferenceSeries | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": opportunity.id,
            "conference_edition_id": opportunity.conference_edition_id,
            "edition_id": opportunity.conference_edition_id,
            "series_id": edition.conference_series_id if edition else None,
            "series_name": series.name if series else None,
            "year": edition.year if edition else None,
            "edition_name": edition.edition_name if edition else None,
            "opportunity_type": opportunity.opportunity_type,
            "title": opportunity.title,
            "official_label": opportunity.official_label,
            "description": opportunity.description,
            "audience": opportunity.audience,
            "open_date": opportunity.open_date,
            "deadline": opportunity.deadline,
            "participation_mode": opportunity.participation_mode,
            "official_url": opportunity.official_url,
            "source_id": opportunity.source_id,
            "evidence": opportunity.evidence,
            "evidence_status": opportunity.evidence_status,
            "verification_status": opportunity.verification_status,
            "is_verified": opportunity.is_verified,
            "risk_flags": opportunity.risk_flags,
            "needs_review": opportunity.needs_review,
            "notes": opportunity.notes,
            "status": status or opportunity_status(opportunity, edition=edition),
            "value_reason_type": value_reason_type_for_opportunity(
                opportunity.opportunity_type
            ),
            "last_verified_at": opportunity.last_verified_at,
            "status_hint": opportunity.status_hint,
            "created_at": opportunity.created_at,
            "updated_at": opportunity.updated_at,
        }

    @staticmethod
    def _to_naive_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def list_discipline_mappings(
        self,
        db: Session,
        *,
        major_alias: str | None = None,
        discipline: str | None = None,
        relationship_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(ConferenceDisciplineMapping)
        if major_alias:
            stmt = stmt.where(ConferenceDisciplineMapping.major_alias.ilike(f"%{major_alias}%"))
        if discipline:
            stmt = stmt.where(ConferenceDisciplineMapping.discipline == discipline)
        if relationship_type:
            stmt = stmt.where(
                ConferenceDisciplineMapping.relationship_type == relationship_type
            )
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(
            stmt.order_by(ConferenceDisciplineMapping.major_alias)
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "major_alias",
                    "discipline",
                    "relationship_type",
                    "mapping_basis",
                    "evidence",
                    "source_url",
                    "status",
                    "created_at",
                    "updated_at",
                )
            }
            for row in rows
        ], total

    def actionable_summary(
        self, db: Session, *, year: int | None = None
    ) -> dict[str, Any]:
        """Read-only aggregate counts for current/future opportunities."""
        today_year = year or self._current_year()
        stmt = (
            select(ConferenceOpportunity, ConferenceEdition, ConferenceSeries)
            .join(
                ConferenceEdition,
                ConferenceOpportunity.conference_edition_id == ConferenceEdition.id,
            )
            .join(
                ConferenceSeries,
                ConferenceEdition.conference_series_id == ConferenceSeries.id,
            )
            .where(ConferenceEdition.year == today_year)
        )
        rows = list(db.execute(stmt).all())
        status_counter: Counter[str] = Counter()
        type_counter: Counter[str] = Counter()
        audience_counter: Counter[str] = Counter()
        discipline_counter: Counter[str] = Counter()
        active_items: list[dict[str, Any]] = []
        for opportunity, edition, series in rows:
            opp_status = opportunity_status(opportunity, edition=edition)
            status_counter[opp_status] += 1
            type_counter[opportunity.opportunity_type] += 1
            for value in opportunity.audience or []:
                audience_counter[value] += 1
            discipline_counter[series.discipline] += 1
            if opp_status in {"open", "closing_soon", "upcoming"}:
                active_items.append(
                    {
                        "series_id": series.id,
                        "series_name": series.name,
                        "edition_id": edition.id,
                        "edition_name": edition.edition_name,
                        "year": edition.year,
                        "opportunity_id": opportunity.id,
                        "opportunity_type": opportunity.opportunity_type,
                        "title": opportunity.title,
                        "audience": opportunity.audience,
                        "status": opp_status,
                        "discipline": series.discipline,
                    }
                )
        edition_count = db.scalar(
            select(func.count())
            .select_from(ConferenceEdition)
            .where(ConferenceEdition.year == today_year)
        ) or 0
        return {
            "year": today_year,
            "editions_total": edition_count,
            "current_actionable_editions": len(
                {item["edition_id"] for item in active_items}
            ),
            "current_actionable_opportunities": len(active_items),
            "by_status": dict(sorted(status_counter.items())),
            "by_opportunity_type": dict(sorted(type_counter.items())),
            "by_audience": dict(sorted(audience_counter.items())),
            "by_discipline": dict(sorted(discipline_counter.items())),
            "items": active_items,
        }

    @staticmethod
    def _current_year() -> int:
        from datetime import date as _date

        return _date.today().year

    def list_actionable(
        self,
        db: Session,
        *,
        year: int | None = None,
        include_history: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Structured read-only bundle for the future student frontend."""
        current_year = year or self._current_year()
        stmt = (
            select(ConferenceOpportunity, ConferenceEdition, ConferenceSeries)
            .join(
                ConferenceEdition,
                ConferenceOpportunity.conference_edition_id == ConferenceEdition.id,
            )
            .join(
                ConferenceSeries,
                ConferenceEdition.conference_series_id == ConferenceSeries.id,
            )
            .where(ConferenceEdition.year == current_year)
        )
        rows = list(db.execute(stmt.order_by(ConferenceOpportunity.id)).all())
        by_edition: dict[int, dict[str, Any]] = {}
        for opportunity, edition, series in rows:
            opp_status = opportunity_status(opportunity, edition=edition)
            if not include_history and opp_status in {"closed", "held"}:
                continue
            bundle = by_edition.setdefault(
                edition.id,
                {
                    "series": {
                        "id": series.id,
                        "name": series.name,
                        "english_name": series.english_name,
                        "short_name": series.short_name,
                        "discipline": series.discipline,
                        "secondary_disciplines": series.secondary_disciplines,
                        "recognition": recognition_summary(
                            series.external_classifications
                        ),
                        "official_website": series.official_website,
                    },
                    "edition": {
                        "id": edition.id,
                        "year": edition.year,
                        "edition_name": edition.edition_name,
                        "start_date": edition.start_date,
                        "end_date": edition.end_date,
                        "city": edition.city,
                        "country_or_region": edition.country_or_region,
                        "edition_official_url": edition.edition_official_url,
                        "status": edition_lifecycle_status(edition),
                    },
                    "opportunities": [],
                    "disciplines": [series.discipline]
                    + list(series.secondary_disciplines or []),
                    "value_reasons": [],
                    "evidence": [],
                },
            )
            opp_payload = self._opportunity_payload(
                opportunity, edition=edition, series=series
            )
            bundle["opportunities"].append(opp_payload)
            reason_type = value_reason_type_for_opportunity(
                opportunity.opportunity_type
            )
            if reason_type and reason_type not in bundle["value_reasons"]:
                bundle["value_reasons"].append(
                    {
                        "type": reason_type,
                        "source_id": opportunity.source_id,
                        "source_url": opportunity.official_url,
                    }
                )
            evidence_entry = {
                "source_id": opportunity.source_id,
                "source_url": opportunity.official_url,
                "evidence_status": opportunity.evidence_status,
                "notes": opportunity.evidence,
            }
            if evidence_entry not in bundle["evidence"]:
                bundle["evidence"].append(evidence_entry)
        bundles = list(by_edition.values())
        total = len(bundles)
        return bundles[offset : offset + limit], total

    def list_sources(
        self,
        db: Session,
        *,
        series_id: int | None = None,
        edition_id: int | None = None,
        authority_level: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(ConferenceSource)
        if series_id is not None:
            stmt = stmt.where(ConferenceSource.conference_series_id == series_id)
        if edition_id is not None:
            stmt = stmt.where(ConferenceSource.conference_edition_id == edition_id)
        if authority_level:
            stmt = stmt.where(ConferenceSource.authority_level == authority_level)
        if source_type:
            stmt = stmt.where(ConferenceSource.source_type == source_type)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(
            stmt.order_by(ConferenceSource.id).limit(limit).offset(offset)
        ).scalars().all()
        payload = [
            {
                key: getattr(source, key)
                for key in (
                    "id",
                    "conference_series_id",
                    "conference_edition_id",
                    "source_type",
                    "authority_level",
                    "source_name",
                    "source_url",
                    "source_platform",
                    "official_domain",
                    "document_name",
                    "published_at",
                    "retrieved_at",
                    "is_official",
                    "is_verified",
                    "verification_status",
                    "raw_title",
                    "metadata_json",
                    "notes",
                )
            }
            for source in rows
        ]
        return payload, total

    def list_school_relations(
        self,
        db: Session,
        *,
        school_id: int | None = None,
        series_id: int | None = None,
        edition_id: int | None = None,
        relation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = (
            select(SchoolConference, University.name, ConferenceSeries.name, ConferenceEdition.year)
            .join(University, SchoolConference.school_id == University.id)
            .outerjoin(
                ConferenceSeries,
                SchoolConference.conference_series_id == ConferenceSeries.id,
            )
            .outerjoin(
                ConferenceEdition,
                SchoolConference.conference_edition_id == ConferenceEdition.id,
            )
        )
        if school_id is not None:
            stmt = stmt.where(SchoolConference.school_id == school_id)
        if series_id is not None:
            stmt = stmt.where(SchoolConference.conference_series_id == series_id)
        if edition_id is not None:
            stmt = stmt.where(SchoolConference.conference_edition_id == edition_id)
        if relation_type:
            stmt = stmt.where(SchoolConference.relation_type == relation_type)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(
            stmt.order_by(SchoolConference.id.desc()).limit(limit).offset(offset)
        ).all()
        payload = []
        for relation, school_name, series_name, edition_year in rows:
            payload.append(
                {
                    "id": relation.id,
                    "school_id": relation.school_id,
                    "school_name": school_name,
                    "conference_series_id": relation.conference_series_id,
                    "series_name": series_name,
                    "conference_edition_id": relation.conference_edition_id,
                    "edition_name": None,
                    "edition_year": edition_year,
                    "relation_type": relation.relation_type,
                    "responsible_department": relation.responsible_department,
                    "responsible_college": relation.responsible_college,
                    "notice_url": relation.notice_url,
                    "campus_deadline": relation.campus_deadline,
                    "notes": relation.notes,
                    "source_id": relation.source_id,
                    "is_verified": relation.is_verified,
                    "verification_status": relation.verification_status,
                    "verified_at": relation.verified_at,
                    "created_at": relation.created_at,
                }
            )
        return payload, total

    def list_candidates(
        self,
        db: Session,
        *,
        status: str | None = None,
        keyword: str | None = None,
        rejection_reason: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(ConferenceDiscoveryCandidate)
        if status:
            stmt = stmt.where(ConferenceDiscoveryCandidate.status == status)
        if rejection_reason:
            stmt = stmt.where(
                ConferenceDiscoveryCandidate.rejection_reason == rejection_reason
            )
        if keyword:
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(ConferenceDiscoveryCandidate.raw_name.ilike(pattern))
        if entity_type:
            stmt = stmt.where(ConferenceDiscoveryCandidate.entity_type == entity_type)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(
            stmt.order_by(ConferenceDiscoveryCandidate.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {
                key: getattr(row, key)
                for key in (
                    "id",
                    "raw_name",
                    "year",
                    "acronym",
                    "english_name",
                    "organizer_hint",
                    "discipline_hint",
                    "source_type",
                    "source_name",
                    "source_url",
                    "source_domain",
                    "status",
                    "matched_series_id",
                    "matched_edition_id",
                    "duplicate_of_id",
                    "needs_review",
                    "risk_flags",
                    "rejection_reason",
                    "notes",
                    "discovered_at",
                    "reviewed_at",
                    "review_notes",
                    "entity_type",
                    "metadata_json",
                )
            }
            payload.append(item)
        return payload, total

    @staticmethod
    def _series_payload(
        row: ConferenceSeries,
        *,
        edition_count: int,
        latest_edition_year: int | None,
        official_source_count: int,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "english_name": row.english_name,
            "short_name": row.short_name,
            "aliases": row.aliases,
            "discipline": row.discipline,
            "subdiscipline": row.subdiscipline,
            "organizer_summary": row.organizer_summary,
            "official_website": row.official_website,
            "first_held_year": row.first_held_year,
            "conference_frequency": row.conference_frequency,
            "conference_scope": row.conference_scope,
            "is_international": row.is_international,
            "description": row.description,
            "external_classifications": row.external_classifications,
            "recognition": recognition_summary(row.external_classifications),
            "student_value_tags": row.student_value_tags,
            "audience": row.audience,
            "status": row.status,
            "authority_status": row.authority_status,
            "verification_status": row.verification_status,
            "is_verified": row.is_verified,
            "risk_flags": row.risk_flags,
            "needs_review": row.needs_review,
            "last_verified_at": row.last_verified_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "edition_count": edition_count,
            "latest_edition_year": latest_edition_year,
            "official_source_count": official_source_count,
        }

    @staticmethod
    def _edition_payload(
        edition: ConferenceEdition,
        *,
        series_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": edition.id,
            "conference_series_id": edition.conference_series_id,
            "series_name": series_name,
            "year": edition.year,
            "edition_name": edition.edition_name,
            "edition_number": edition.edition_number,
            "start_date": edition.start_date,
            "end_date": edition.end_date,
            "location": edition.location,
            "country_or_region": edition.country_or_region,
            "city": edition.city,
            "venue": edition.venue,
            "notes": edition.notes,
            "online_status": edition.online_status,
            "abstract_deadline": edition.abstract_deadline,
            "paper_deadline": edition.paper_deadline,
            "notification_date": edition.notification_date,
            "camera_ready_deadline": edition.camera_ready_deadline,
            "registration_deadline": edition.registration_deadline,
            "poster_deadline": edition.poster_deadline,
            "workshop_deadline": edition.workshop_deadline,
            "call_for_papers_url": edition.call_for_papers_url,
            "edition_official_url": edition.edition_official_url,
            "registration_url": edition.registration_url,
            "publication_info": edition.publication_info,
            "publication_status": edition.publication_status,
            "publication_details": edition.publication_details,
            "indexing_info": edition.indexing_info,
            "indexing_claims": edition.indexing_claims,
            "indexing_claim_status": edition.indexing_claim_status,
            "submission_language": edition.submission_language,
            "participation_type": edition.participation_type,
            "student_value_tags": edition.student_value_tags,
            "audience": edition.audience,
            "participation_details": edition.participation_details,
            "paper_details": edition.paper_details,
            "edition_status": edition.edition_status,
            "authority_status": edition.authority_status,
            "verification_status": edition.verification_status,
            "is_verified": edition.is_verified,
            "risk_flags": edition.risk_flags,
            "needs_review": edition.needs_review,
            "last_verified_at": edition.last_verified_at,
            "source_url": edition.source_url,
            "created_at": edition.created_at,
            "updated_at": edition.updated_at,
        }


def source_authority_options() -> dict[str, str]:
    """Controlled source_type -> level map for API metadata."""
    return dict(CONFERENCE_SOURCE_TYPE_AUTHORITY)
