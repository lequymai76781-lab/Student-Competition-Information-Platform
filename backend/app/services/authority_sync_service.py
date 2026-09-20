"""Repeatable authority-source sync pipeline (V1).

Flow: authority registry (JSON seeds)
    -> collect/match (existing Competition entities)
    -> bind CompetitionSource + CompetitionFactSource rows
    -> create/link CompetitionEdition rows when a year is provable
    -> record conflicts / revisions instead of silent overwrites
    -> recompute verification statuses with authority rules

The same registry can be re-run; bindings are idempotent (URL dedupe).
Use dry_run=True for a no-write report and dry_run=False to apply.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionSource,
    Organization,
)
from app.services.authority_match_service import (
    AuthorityMatchService,
    extract_year,
)
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.source_authority_service import AUTHORITY_ORDER, can_prove


REGISTRY_DIR_DEFAULT = Path(__file__).resolve().parents[3] / "data" / "seeds" / "authority_registry"


def load_registry_entries(registry_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not registry_dir.exists():
        return entries
    for path in sorted(registry_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            entry = json.load(handle)
        if entry.get("enabled", True):
            entries.append(entry)
    return entries


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _field_for_source(source_type: str) -> str:
    return "verified_official" if source_type and source_type.startswith(("government", "official", "organizer", "ministry")) else "authority_confirmed"


class AuthoritySyncService:
    def __init__(self, matcher: AuthorityMatchService | None = None) -> None:
        self.matcher = matcher or AuthorityMatchService()

    def run(
        self,
        db: Session,
        *,
        registry_dir: Path = REGISTRY_DIR_DEFAULT,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now(timezone.utc)
        entries = load_registry_entries(registry_dir)
        report: dict[str, Any] = {
            "pipeline": "authority-main-library-v1",
            "dry_run": dry_run,
            "generated_at": stamp.isoformat(),
            "registry_dir": str(registry_dir),
            "counters": Counter(),
            "matches": [],
            "conflicts": [],
            "manual_review": [],
            "unmatched": [],
            "organizations": [],
        }
        if not dry_run:
            report["status_before"] = self._status_snapshot(db)
        for entry in entries:
            counters = report["counters"]
            counters["registry_entries"] += 1
            row = self._process_entry(db, entry, stamp, dry_run, report)
            report["matches"].append(row)
        if not dry_run:
            fact_service = FactIntelligenceService()
            db.flush()
            db.expire_all()
            fact_service.refresh_source_tiers(db)
            fact_service.refresh_verification(db)
            report["status_after"] = self._status_snapshot(db)
            report["status_deltas"] = self._status_deltas(
                report.get("status_before", {}), report["status_after"]
            )
        self._normalize_report(report)
        return report

    @staticmethod
    def _status_snapshot(db: Session) -> dict[str, dict[str, int]]:
        def one(table: str) -> dict[str, int]:
            rows = db.execute(
                select(Competition).where(Competition.is_demo.is_(False))
                if table == "competitions"
                else select(CompetitionEdition)
            ).scalars()
            out: dict[str, int] = {}
            for row in rows:
                status = row.verification_status
                out[status] = out.get(status, 0) + 1
            return out

        return {"competitions": one("competitions"), "editions": one("editions")}

    @staticmethod
    def _status_deltas(
        before: dict[str, dict[str, int]],
        after: dict[str, dict[str, int]],
    ) -> dict[str, dict[str, int]]:
        deltas: dict[str, dict[str, int]] = {}
        for layer in ("competitions", "editions"):
            b = before.get(layer, {})
            a = after.get(layer, {})
            keys = set(b) | set(a)
            deltas[layer] = {
                status: a.get(status, 0) - b.get(status, 0)
                for status in sorted(keys)
                if a.get(status, 0) != b.get(status, 0)
            }
        return deltas

    # ------------------------------------------------------------------ #
    def _process_entry(
        self,
        db: Session,
        entry: dict[str, Any],
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        counters = report["counters"]
        expected = entry.get("expected") or {}
        raw_name = expected.get("competition_name")
        year = expected.get("edition_year") or extract_year(entry.get("title") or entry.get("source_name"))
        row: dict[str, Any] = {
            "registry_id": entry.get("registry_id"),
            "title": entry.get("title") or entry.get("source_name"),
            "authority_level": entry.get("authority_level"),
            "competition": None,
            "edition": None,
            "method": "none",
            "needs_manual_review": True,
        }
        self._ensure_organization(db, entry, dry_run, report)
        if not raw_name:
            row["method"] = "no_competition_name"
            row["needs_manual_review"] = True
            report["unmatched"].append(
                {
                    "registry_id": entry.get("registry_id"),
                    "reason": "registry entry has no expected competition name",
                    "notes": entry.get("notes"),
                }
            )
            counters["no_name_discovery"] += 1
            return row

        match = self.matcher.match(
            db,
            raw_name,
            year=year,
            aliases=expected.get("aliases") or [],
            organizer_hint=expected.get("organizer_hint"),
            domain_hint=expected.get("domain_hint"),
        )
        competition = match.competition
        row["competition"] = competition.name if competition else None
        row["method"] = match.method
        row["confidence"] = round(match.confidence, 3)
        row["reasons"] = match.reasons
        if not competition:
            row["needs_manual_review"] = True
            report["unmatched"].append(
                {
                    "registry_id": entry.get("registry_id"),
                    "name": raw_name,
                    "reasons": match.reasons,
                }
            )
            counters["unmatched"] += 1
            return row
        if match.needs_manual_review:
            row["needs_manual_review"] = True
            report["manual_review"].append(
                {
                    "registry_id": entry.get("registry_id"),
                    "name": raw_name,
                    "matched_competition": competition.name,
                    "confidence": round(match.confidence, 3),
                }
            )
            counters["manual_review"] += 1
            return row
        counters["matched"] += 1
        row["needs_manual_review"] = False

        source = self._bind_source(db, entry, competition, year, stamp, dry_run, report)
        if source is None:
            source = self._find_source(db, entry, competition.id, year)
        if source is None:
            source = SimpleNamespace(
                source_type=entry.get("source_type") or "official_notice",
                authority_level=entry.get("authority_level") or "S",
                source_name=entry.get("source_name") or entry.get("title"),
                source_url=(
                    entry.get("canonical_source_url")
                    or entry.get("existing_source_url")
                    or entry.get("source_url")
                ),
                published_at=_parse_dt(entry.get("published_at")),
                competition_edition_id=None,
            )

        edition = self._sync_edition(
            db,
            entry,
            competition,
            source,
            stamp,
            dry_run,
            report,
        )
        if edition is not None:
            row["edition"] = edition.year
        self._apply_competition_facts(
            db,
            competition,
            entry.get("competition_facts") or {},
            source,
            stamp,
            dry_run,
            report,
        )
        return row

    # ------------------------------------------------------------------ #
    def _ensure_organization(
        self,
        db: Session,
        entry: dict[str, Any],
        dry_run: bool,
        report: dict[str, Any],
    ) -> None:
        name = entry.get("organization_name")
        if not name:
            return
        # Only register organizations that are not already represented by an
        # existing canonical row. Government/committee names already covered by
        # existing organization rows are skipped to avoid near-duplicates.
        if entry.get("authority_level") != "A":
            return
        org = db.execute(select(Organization).where(Organization.name == name)).scalar_one_or_none()
        if org:
            return
        domain = entry.get("source_url") or entry.get("canonical_source_url") or ""
        payload = {
            "name": name,
            "org_type": "academic_association"
            if entry.get("source_type") == "higher_education_association"
            else "government_agency"
            if entry.get("authority_level") == "S"
            else "association",
            "official_website": domain,
            "is_verified": True,
            "is_demo": False,
        }
        if dry_run:
            report["organizations"].append({**payload, "action": "would_create"})
            report["counters"]["organizations_would_create"] += 1
            return
        db.add(Organization(**payload))
        db.flush()
        report["organizations"].append({**payload, "action": "created"})
        report["counters"]["organizations_created"] += 1

    def _find_source(
        self,
        db: Session,
        entry: dict[str, Any],
        competition_id: int,
        year: int | None,
    ) -> CompetitionSource | None:
        urls = {
            entry.get("existing_source_url"),
            entry.get("canonical_source_url"),
            entry.get("source_url"),
        }
        urls.discard(None)
        if not urls:
            return None
        query = select(CompetitionSource).where(
            CompetitionSource.competition_id == competition_id,
            CompetitionSource.source_url.in_(list(urls)),
        )
        row = db.execute(query).scalars().first()
        return row

    def _bind_source(
        self,
        db: Session,
        entry: dict[str, Any],
        competition: Competition,
        year: int | None,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> CompetitionSource | None:
        counters = report["counters"]
        source_url = (
            entry.get("canonical_source_url")
            or entry.get("existing_source_url")
            or entry.get("source_url")
        )
        existing = self._find_source(db, entry, competition.id, year)
        if existing is not None:
            counters["source_exists"] += 1
            return existing
        if dry_run:
            counters["sources_would_add"] += 1
            return None
        published_at = _parse_dt(entry.get("published_at"))
        metadata: dict[str, Any] = {
            "registry_id": entry.get("registry_id"),
            "doc_number": entry.get("doc_number"),
            "role": entry.get("relation_role"),
            "scope": entry.get("relationship_scope"),
            "evidence_file": entry.get("local_content_path"),
            "authority_level": entry.get("authority_level"),
        }
        source = CompetitionSource(
            competition_id=competition.id,
            source_type=entry.get("source_type") or "official_notice",
            authority_level=entry.get("authority_level") or "S",
            source_name=entry.get("source_name") or entry.get("title"),
            source_url=source_url,
            source_repository="authority-registry",
            source_platform="official_website",
            published_at=published_at,
            crawled_at=stamp,
            retrieved_at=stamp,
            is_official=True,
            is_verified=bool(entry.get("mark_verified", True)),
            credibility_score=100,
            reliability_tier=1,
            verification_status=_field_for_source(entry.get("source_type") or "official_notice"),
            raw_title=entry.get("title") or entry.get("source_name"),
            metadata_json=metadata,
            is_demo=False,
        )
        db.add(source)
        db.flush()
        counters["sources_added"] += 1
        counters[f"sources_added_level_{source.authority_level}"] += 1
        return source

    # ------------------------------------------------------------------ #
    def _sync_edition(
        self,
        db: Session,
        entry: dict[str, Any],
        competition: Competition,
        source: CompetitionSource,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> CompetitionEdition | None:
        edition_block = entry.get("edition")
        if not edition_block:
            return None
        year = edition_block.get("year")
        if not year:
            return None
        counters = report["counters"]
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == year,
            )
        ).scalars().first()
        if edition is None:
            if dry_run:
                counters["editions_would_create"] += 1
                return None
            edition = CompetitionEdition(
                competition_id=competition.id,
                year=year,
                edition_name=edition_block.get("edition_name"),
                verification_status="unverified",
                current_status="unknown",
                edition_status="unknown",
                freshness_status="unknown",
            )
            db.add(edition)
            db.flush()
            counters["editions_created"] += 1
        if source.competition_edition_id is None:
            if dry_run:
                counters["edition_source_links_would_add"] += 1
            else:
                source.competition_edition_id = edition.id
                counters["edition_source_links_added"] += 1
        self._apply_edition_fields(
            db,
            edition,
            edition_block,
            source,
            stamp,
            dry_run,
            report,
        )
        self._record_edition_facts(
            db,
            edition,
            edition_block.get("facts") or {},
            source,
            stamp,
            dry_run,
            report,
        )
        return edition

    _EDITION_COLUMN_MAP = {
        "edition_name": "edition_name",
        "registration_start": "registration_start",
        "official_registration_deadline": "official_registration_deadline",
        "competition_start": "competition_start",
        "competition_end": "competition_end",
    }

    def _apply_edition_fields(
        self,
        db: Session,
        edition: CompetitionEdition,
        block: dict[str, Any],
        source: CompetitionSource,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> None:
        for raw_field, attr in self._EDITION_COLUMN_MAP.items():
            incoming = block.get(raw_field)
            if incoming is None:
                continue
            incoming_dt = _parse_dt(incoming)
            value = incoming_dt if incoming_dt else incoming
            current = getattr(edition, attr)
            current_dt = _parse_dt(current)
            current_value = current_dt if current_dt else current
            if current_value is not None and self._values_equal(current_value, value):
                continue
            if not can_prove(source.source_type, raw_field):
                report["counters"]["field_not_provable"] += 1
                continue
            current_level = self._field_source_level(db, edition.competition_id, edition.id, raw_field)
            incoming_level = (source.authority_level or "D").upper()
            if current_value is not None and current_level is not None:
                if AUTHORITY_ORDER.get(incoming_level, 99) >= AUTHORITY_ORDER.get(current_level, 99):
                    report["conflicts"].append(
                        {
                            "competition_id": edition.competition_id,
                            "edition_id": edition.id,
                            "field": raw_field,
                            "current_value": _json_safe(current_value),
                            "incoming_value": _json_safe(value),
                            "current_authority": current_level,
                            "incoming_authority": incoming_level,
                            "reason": "equal-or-lower authority conflict, no silent overwrite",
                        }
                    )
                    report["counters"]["conflicts"] += 1
                    continue
            if dry_run:
                report["counters"]["edition_fields_would_change"] += 1
                continue
            self._write_revision(
                db,
                edition=edition,
                field=raw_field,
                old_value=_json_safe(current_value),
                new_value=_json_safe(value),
                source=source,
                stamp=stamp,
                note="official registry value applied (higher authority than previous source)",
            )
            setattr(edition, attr, value)
            self._upsert_fact_row(
                db,
                competition_id=edition.competition_id,
                edition=edition,
                field_name=raw_field,
                value=_json_safe(value),
                source=source,
                stamp=stamp,
                dry_run=False,
            )
            report["counters"]["edition_fields_changed"] += 1

    def _field_source_level(
        self,
        db: Session,
        competition_id: int,
        edition_id: int | None,
        field_name: str,
    ) -> str | None:
        rows = list(
            db.execute(
                select(CompetitionFactSource)
                .where(
                    CompetitionFactSource.competition_id == competition_id,
                    CompetitionFactSource.field_name == field_name,
                )
                .order_by(CompetitionFactSource.id.desc())
                .limit(1)
            ).scalars()
        )
        if not rows:
            return None
        from app.services.source_authority_service import authority_level_for

        return authority_level_for(rows[0].source_type)

    def _record_edition_facts(
        self,
        db: Session,
        edition: CompetitionEdition,
        facts: dict[str, Any],
        source: CompetitionSource,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> None:
        if not facts:
            return
        for field_name, value in facts.items():
            if value is None:
                continue
            if dry_run:
                existing = db.execute(
                    select(CompetitionFactSource).where(
                        CompetitionFactSource.competition_id == edition.competition_id,
                        CompetitionFactSource.competition_edition_id == edition.id,
                        CompetitionFactSource.field_name == field_name,
                        CompetitionFactSource.source_url == source.source_url,
                    )
                ).scalars().first()
                if existing is not None:
                    report["counters"]["fact_rows_exist"] += 1
                else:
                    report["counters"]["fact_rows_would_add"] += 1
                continue
            created = self._upsert_fact_row(
                db,
                competition_id=edition.competition_id,
                edition=edition,
                field_name=field_name,
                value=_json_safe(value),
                source=source,
                stamp=stamp,
                dry_run=False,
            )
            if created:
                report["counters"]["fact_rows_added"] += 1

    _COMPETITION_ALLOWED_FACTS = {"official_website"}

    def _apply_competition_facts(
        self,
        db: Session,
        competition: Competition,
        facts: dict[str, Any],
        source: Any,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> None:
        if not facts:
            return
        for field, incoming in facts.items():
            if incoming is None:
                continue
            if field not in self._COMPETITION_ALLOWED_FACTS:
                report["counters"]["disallowed_competition_facts"] += 1
                continue
            if not can_prove(source.source_type, field):
                report["counters"]["field_not_provable"] += 1
                continue
            current = getattr(competition, field)
            if current is not None and self._values_equal(current, incoming):
                continue
            if current is not None:
                report["counters"]["conflicts"] += 1
                report["conflicts"].append(
                    {
                        "competition_id": competition.id,
                        "field": field,
                        "current_value": current,
                        "incoming_value": incoming,
                        "reason": "competition-level fact conflict, no silent overwrite",
                    }
                )
                continue
            if dry_run:
                report["counters"]["competition_fields_would_change"] += 1
                continue
            setattr(competition, field, incoming)
            report["counters"]["competition_fields_changed"] += 1

    def _upsert_fact_row(
        self,
        db: Session,
        *,
        competition_id: int,
        edition: CompetitionEdition | None,
        field_name: str,
        value: Any,
        source: CompetitionSource,
        stamp: datetime,
        dry_run: bool,
    ) -> bool:
        if dry_run:
            return False
        existing = db.execute(
            select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == competition_id,
                CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
                CompetitionFactSource.field_name == field_name,
                CompetitionFactSource.source_url == source.source_url,
            )
        ).scalars().first()
        if existing is not None:
            existing.fact_value = value
            existing.last_verified_at = stamp
            existing.observed_at = existing.observed_at or stamp
            return False
        db.add(
            CompetitionFactSource(
                competition_id=competition_id,
                competition_edition_id=edition.id if edition else None,
                field_name=field_name,
                fact_value=value,
                source_type=source.source_type,
                source_name=source.source_name,
                source_url=source.source_url,
                reliability_tier=1,
                source_level="LEVEL_1",
                is_official=True,
                verification_status=_field_for_source(source.source_type),
                published_at=source.published_at,
                observed_at=stamp,
                last_verified_at=stamp,
                notes=None,
            )
        )
        return True

    def _write_revision(
        self,
        db: Session,
        *,
        edition: CompetitionEdition,
        field: str,
        old_value: Any,
        new_value: Any,
        source: CompetitionSource,
        stamp: datetime,
        note: str,
    ) -> None:
        from app.models import CompetitionFactRevision

        db.add(
            CompetitionFactRevision(
                competition_id=edition.competition_id,
                competition_edition_id=edition.id,
                field_name=field,
                old_value=old_value,
                new_value=new_value,
                changed_at=stamp,
                source_url=source.source_url,
                source_name=source.source_name,
                verification_status=_field_for_source(source.source_type),
            )
        )

    @staticmethod
    def _values_equal(left: Any, right: Any) -> bool:
        if isinstance(left, datetime) or isinstance(right, datetime):
            left = left.isoformat() if isinstance(left, datetime) else str(left)
            right = right.isoformat() if isinstance(right, datetime) else str(right)
            return left[:19] == right[:19]
        return str(left) == str(right)

    @staticmethod
    def _normalize_report(report: dict[str, Any]) -> None:
        counters = report["counters"]
        counters["registry_total"] = counters.get("registry_entries", 0)
        counters["sources_total_change"] = counters.get("sources_added", 0)
        report["counters"] = dict(sorted(counters.items()))


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value
