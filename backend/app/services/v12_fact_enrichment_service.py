"""V12 evidence-grounded fact enrichment (idempotent, provenance-preserving).

Reads a curated registry under data/seeds/v12_fact_registry/. Every fact entry
carries an official source URL plus an optional local evidence file. Applying
an entry:

- never fabricates fields; each write must be provable by an S/A source
  (B/C sources can only fill school-level facts, which this registry never uses)
- fills Competition permanent fields only when empty, or when the registry
  explicitly marks allow_overwrite with a reason
- creates/links CompetitionSource rows (URL-deduped) and attaches them to
  CompetitionEdition rows when the registry proves a year
- records CompetitionFactSource provenance and CompetitionFactRevision on every
  change; logs every write/delete to AdminAuditLog
- reruns safe; dry_run=True produces a plan without writes

Registry format (one entry per competition):

{
  "competition_id": 1,
  "name": "中国国际大学生创新大赛",
  "notes": "...",
  "competition_fields": {
    "organizer": {
      "value": "...",
      "source_url": "https://...",
      "allow_overwrite": true,
      "overwrite_reason": "..."
    }
  },
  "organizations": [
    {"name": "教育部", "role": "organizer", "org_type": "government_agency",
     "source_url": "https://..."}
  ],
  "organization_removals": [
    {"name": "江苏省人民政府", "role": "organizer", "reason": "2026届当届主办，不写入永久关系"}
  ],
  "editions": [
    {"year": 2026, "upsert": true,
     "fields": {"edition_name": "...", "official_registration_url": "..."},
     "nullify": ["official_registration_deadline"],
     "source_url": "https://...", "source_type": "official_notice",
     "authority_level": "S", "published_at": "2026-07-31",
     "evidence_file": "data/raw/...", "raw_title": "...",
     "facts": {"edition_result_url": "..."}}
  ]
}
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdminAuditLog,
    Competition,
    CompetitionEdition,
    CompetitionFactRevision,
    CompetitionFactSource,
    CompetitionOrganization,
    CompetitionSource,
    Organization,
)
from app.services.audit_service import record_admin_action
from app.services.competition_freshness_service import CompetitionFreshnessService
from app.services.fact_intelligence_service import FactIntelligenceService
from app.services.field_evidence_service import (
    default_evidence_level,
    evidence_allowed,
    evidence_level_for_source,
    classify_homepage,
)
from app.services.source_authority_service import (
    AUTHORITY_LEVELS,
    can_prove,
    authority_level_for,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_DIR_DEFAULT = PROJECT_ROOT / "data" / "seeds" / "v12_fact_registry"

WEBSITE_SOURCE_TYPES = {
    "competition_official_website",
    "official_competition_website",
    "competition_official_site",
}

COMPETITION_EDITABLE_FIELDS = {
    "official_website",
    "organizer",
    "co_organizers",
    "undertakers",
    "guiding_organizations",
    "target_students",
    "description",
    "competition_format",
    "competition_scope",
    "team_type",
    "first_held_year",
    "founded_year",
}

EDITION_EDITABLE_FIELDS = {
    "edition_name",
    "edition_status",
    "current_status",
    "registration_start",
    "official_registration_deadline",
    "registration_deadline",
    "submission_deadline",
    "competition_start",
    "competition_end",
    "official_competition_date",
    "host_location",
    "edition_rules_url",
    "official_notice_url",
    "official_registration_url",
    "official_url",
    "source_url",
}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) or isinstance(right, datetime):
        left = left.isoformat() if isinstance(left, datetime) else str(left)
        right = right.isoformat() if isinstance(right, datetime) else str(right)
        return left[:19] == right[:19]
    if isinstance(left, list) or isinstance(right, list):
        return (left or []) == (right or [])
    return (left or "") == (right or "")


def _domain_root(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


class V12FactEnrichmentService:
    def __init__(self) -> None:
        self.freshness = CompetitionFreshnessService()
        self._fact_service = FactIntelligenceService()

    def run(
        self,
        db: Session,
        *,
        registry_dir: Path = REGISTRY_DIR_DEFAULT,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now(timezone.utc)
        report: dict[str, Any] = {
            "pipeline": "v12-fact-enrichment",
            "dry_run": dry_run,
            "generated_at": stamp.isoformat(),
            "registry_dir": str(registry_dir),
            "entries": [],
            "counters": {
                "entries": 0,
                "competition_fields_changed": 0,
                "competition_fields_conflict": 0,
                "fact_rows_added": 0,
                "sources_added": 0,
                "sources_existing": 0,
                "source_links_added": 0,
                "editions_created": 0,
                "editions_updated": 0,
                "edition_fields_changed": 0,
                "organizations_created": 0,
                "organization_links_added": 0,
                "organization_links_updated": 0,
                "organization_links_removed": 0,
                "audit_rows": 0,
                "skipped_competition_missing": 0,
                "skipped_evidence_missing": 0,
            },
        }
        if not dry_run:
            report["status_before"] = self._status_snapshot(db)
        paths = sorted(registry_dir.glob("*.json"))
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for entry in payload if isinstance(payload, list) else payload.get("entries", [payload]):
                report["counters"]["entries"] += 1
                result = self._process_entry(db, entry, stamp, dry_run, report)
                report["entries"].append(result)
        if not dry_run:
            db.flush()
            db.expire_all()
            self._fact_service.refresh_source_tiers(db)
            self._fact_service.refresh_verification(db)
            report["status_after"] = self._status_snapshot(db)
            report["status_deltas"] = self._status_deltas(
                report["status_before"], report["status_after"]
            )
        report["counters"] = dict(sorted(report["counters"].items()))
        return report

    # ------------------------------------------------------------------ #
    def _process_entry(
        self,
        db: Session,
        entry: dict[str, Any],
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        competition_id = entry["competition_id"]
        competition = db.get(Competition, competition_id)
        row: dict[str, Any] = {
            "competition_id": competition_id,
            "name": entry.get("name"),
            "notes": entry.get("notes"),
            "actions": [],
            "errors": [],
        }
        if competition is None:
            report["counters"]["skipped_competition_missing"] += 1
            row["errors"].append("competition missing")
            return row
        if entry.get("name") and entry["name"] != competition.name:
            row["errors"].append(
                f"name mismatch: registry={entry['name']!r} db={competition.name!r}"
            )
            return row
        row["name"] = competition.name
        for field, spec in (entry.get("competition_fields") or {}).items():
            action = self._apply_competition_field(
                db, competition, field, spec, stamp, dry_run, report
            )
            row["actions"].extend(action)
        for org_spec in entry.get("organizations") or []:
            action = self._upsert_organization_link(
                db, competition, org_spec, stamp, dry_run, report
            )
            if action:
                row["actions"].append(action)
        for removal in entry.get("organization_removals") or []:
            action = self._remove_organization_link(
                db, competition, removal, stamp, dry_run, report
            )
            if action:
                row["actions"].append(action)
        for edition_block in entry.get("editions") or []:
            action = self._sync_edition(
                db, competition, edition_block, stamp, dry_run, report
            )
            if action:
                row["actions"].append(action)
        return row

    # ------------------------------------------------------------------ #
    def _apply_competition_field(
        self,
        db: Session,
        competition: Competition,
        field: str,
        spec: Any,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if field not in COMPETITION_EDITABLE_FIELDS:
            return [{"type": "error", "message": f"field not editable: {field}"}]
        value = spec if isinstance(spec, dict) is False else spec.get("value")
        source_url = spec.get("source_url") if isinstance(spec, dict) else None
        if value is None and not isinstance(spec, dict):
            return actions
        source = self._resolve_or_prepare_source(
            db,
            competition=competition,
            source_url=source_url,
            source_type=spec.get("source_type") if isinstance(spec, dict) else None,
            authority_level=spec.get("authority_level") if isinstance(spec, dict) else None,
            raw_title=spec.get("raw_title") if isinstance(spec, dict) else None,
            published_at=spec.get("published_at") if isinstance(spec, dict) else None,
            evidence_file=spec.get("evidence_file") if isinstance(spec, dict) else None,
            notes=spec.get("notes") if isinstance(spec, dict) else None,
            repository=spec.get("repository") if isinstance(spec, dict) else None,
            stamp=stamp,
            dry_run=dry_run,
            report=report,
        )
        if source is None and source_url:
            actions.append(
                {
                    "type": "error",
                    "field": field,
                    "message": "source not resolved (evidence missing?)",
                }
            )
            return actions
        source_type = source.source_type if source is not None else "official_notice"
        spec_dict = spec if isinstance(spec, dict) else {}
        evidence_level = (
            spec_dict.get("evidence_level")
            or evidence_level_for_source(source_type, source.authority_level if source is not None else None)
        )
        if (
            evidence_level == "LEVEL_3"
            and not spec_dict.get("source_scope")
            and not spec_dict.get("notes")
        ):
            actions.append(
                {
                    "type": "not_provable",
                    "field": field,
                    "message": "LEVEL_3 secondary evidence requires source_scope/notes",
                }
            )
            report["counters"]["competition_fields_conflict"] += 1
            return actions
        if not evidence_allowed(field, evidence_level, spec=spec_dict):
            actions.append(
                {
                    "type": "not_provable",
                    "field": field,
                    "message": (
                        f"evidence {evidence_level} cannot prove {field} "
                        f"(source_type={source_type})"
                    ),
                }
            )
            report["counters"]["competition_fields_conflict"] += 1
            return actions
        current = getattr(competition, field)
        allow_overwrite = bool(spec.get("allow_overwrite")) if isinstance(spec, dict) else False
        if current not in (None, "", [], {}) and not _values_equal(current, value):
            if not allow_overwrite:
                actions.append(
                    {
                        "type": "conflict",
                        "field": field,
                        "current": _json_safe(current),
                        "incoming": _json_safe(value),
                    }
                )
                report["counters"]["competition_fields_conflict"] += 1
                return actions
        if _values_equal(current, value):
            actions.append({"type": "unchanged", "field": field})
            return actions
        reason = spec.get("overwrite_reason") if isinstance(spec, dict) else None
        actions.append(
            {
                "type": "change",
                "field": field,
                "old": _json_safe(current),
                "new": _json_safe(value),
                "reason": reason,
                "source_url": source_url,
            }
        )
        if dry_run:
            report["counters"]["competition_fields_changed"] += 1
            return actions
        if current not in (None, "", [], {}):
            db.add(
                CompetitionFactRevision(
                    competition_id=competition.id,
                    field_name=field,
                    old_value=_json_safe(current),
                    new_value=_json_safe(value),
                    changed_at=stamp,
                    source_url=source_url,
                    source_name=source.source_name if source is not None else None,
                    verification_status="verified_official",
                )
            )
        setattr(competition, field, value)
        if source is not None:
            self._upsert_fact_row(
                db,
                competition=competition,
                edition=None,
                field_name=field,
                value=_json_safe(value),
                source=source,
                stamp=stamp,
                notes=reason,
                evidence_level=evidence_level,
                homepage_type=spec_dict.get("homepage_type"),
                source_scope=spec_dict.get("source_scope"),
            )
        record_admin_action(
            db,
            admin_id=None,
            action="v12.enrichment.field",
            object_type="competition",
            object_id=competition.id,
            before=_json_safe(current),
            after=_json_safe(value),
        )
        report["counters"]["competition_fields_changed"] += 1
        report["counters"]["audit_rows"] += 1
        return actions

    # ------------------------------------------------------------------ #
    def _upsert_organization_link(
        self,
        db: Session,
        competition: Competition,
        spec: dict[str, Any],
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        name = spec["name"]
        role = spec.get("role", "organizer")
        org = db.execute(
            select(Organization).where(Organization.name == name)
        ).scalar_one_or_none()
        if org is None:
            if dry_run:
                report["counters"]["organizations_created"] += 1
            else:
                org = Organization(
                    name=name,
                    org_type=spec.get("org_type", "other"),
                    official_website=spec.get("official_website"),
                    official_domain=spec.get("official_domain"),
                    is_verified=True,
                    is_demo=False,
                )
                db.add(org)
                db.flush()
                report["counters"]["organizations_created"] += 1
        else:
            changed = False
            if org.org_type == "other" and spec.get("org_type"):
                org.org_type = spec["org_type"]
                changed = True
            if spec.get("official_website") and not org.official_website:
                org.official_website = spec["official_website"]
                changed = True
            if spec.get("official_domain") and not org.official_domain:
                org.official_domain = spec["official_domain"]
                changed = True
            if not org.is_verified:
                org.is_verified = True
                changed = True
            if changed and not dry_run:
                db.flush()
        if org is None:
            return {"type": "dry_run_org_created", "organization": name, "role": role}
        link = db.execute(
            select(CompetitionOrganization).where(
                CompetitionOrganization.competition_id == competition.id,
                CompetitionOrganization.organization_id == org.id,
                CompetitionOrganization.role == role,
            )
        ).scalar_one_or_none()
        action: dict[str, Any] = {
            "type": "organization_link",
            "organization": name,
            "role": role,
        }
        if link is None:
            if dry_run:
                report["counters"]["organization_links_added"] += 1
                action["mode"] = "would_add"
            else:
                db.add(
                    CompetitionOrganization(
                        competition_id=competition.id,
                        organization_id=org.id,
                        role=role,
                        display_name=spec.get("display_name", name),
                        is_verified=True,
                        source_url=spec.get("source_url"),
                    )
                )
                report["counters"]["organization_links_added"] += 1
                record_admin_action(
                    db,
                    admin_id=None,
                    action="v12.enrichment.org_link.add",
                    object_type="competition",
                    object_id=competition.id,
                    after={"organization": name, "role": role},
                )
                report["counters"]["audit_rows"] += 1
        else:
            changed = False
            payload = {
                "is_verified": True,
                "source_url": spec.get("source_url"),
                "display_name": spec.get("display_name", name),
            }
            for key, value in payload.items():
                if getattr(link, key) != value:
                    setattr(link, key, value)
                    changed = True
            if changed:
                if dry_run:
                    report["counters"]["organization_links_updated"] += 1
                    action["mode"] = "would_update"
                else:
                    report["counters"]["organization_links_updated"] += 1
                    action["mode"] = "updated"
            else:
                action["mode"] = "unchanged"
        return action

    def _remove_organization_link(
        self,
        db: Session,
        competition: Competition,
        spec: dict[str, Any],
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        org = db.execute(
            select(Organization).where(Organization.name == spec["name"])
        ).scalar_one_or_none()
        if org is None:
            return {
                "type": "organization_removal_skip",
                "organization": spec["name"],
                "role": spec.get("role"),
                "message": "organization row not found",
            }
        link = db.execute(
            select(CompetitionOrganization).where(
                CompetitionOrganization.competition_id == competition.id,
                CompetitionOrganization.organization_id == org.id,
                CompetitionOrganization.role == spec.get("role", "organizer"),
            )
        ).scalar_one_or_none()
        if link is None:
            return {
                "type": "organization_removal_skip",
                "organization": spec["name"],
                "role": spec.get("role"),
                "message": "link not found",
            }
        action = {
            "type": "organization_removal",
            "organization": spec["name"],
            "role": link.role,
            "reason": spec.get("reason"),
        }
        if dry_run:
            report["counters"]["organization_links_removed"] += 1
            return action
        before = {"organization": spec["name"], "role": link.role}
        db.delete(link)
        db.flush()
        record_admin_action(
            db,
            admin_id=None,
            action="v12.enrichment.org_link.remove",
            object_type="competition",
            object_id=competition.id,
            before=before,
            after=None,
        )
        report["counters"]["organization_links_removed"] += 1
        report["counters"]["audit_rows"] += 1
        return action

    # ------------------------------------------------------------------ #
    def _sync_edition(
        self,
        db: Session,
        competition: Competition,
        block: dict[str, Any],
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        year = int(block["year"])
        action: dict[str, Any] = {"type": "edition", "year": year}
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == year,
            )
        ).scalar_one_or_none()
        if edition is None:
            if dry_run:
                report["counters"]["editions_created"] += 1
                action["mode"] = "would_create"
            else:
                edition = CompetitionEdition(
                    competition_id=competition.id,
                    year=year,
                    edition_status="unknown",
                    current_status="unknown",
                    freshness_status="unknown",
                    verification_status="unverified",
                )
                db.add(edition)
                db.flush()
                report["counters"]["editions_created"] += 1
                action["mode"] = "created"
        else:
            action["mode"] = "updated"
            report["counters"]["editions_updated"] += 1
        if edition is None:
            return action

        source = self._resolve_or_prepare_source(
            db,
            competition=competition,
            source_url=block.get("source_url"),
            source_type=block.get("source_type", "official_notice"),
            authority_level=block.get("authority_level", "S"),
            raw_title=block.get("raw_title"),
            published_at=block.get("published_at"),
            evidence_file=block.get("evidence_file"),
            notes=block.get("notes"),
            repository=block.get("repository"),
            stamp=stamp,
            dry_run=dry_run,
            report=report,
        )
        if source is not None and source.competition_edition_id != edition.id:
            if dry_run:
                report["counters"]["source_links_added"] += 1
            else:
                source.competition_edition_id = edition.id
                db.flush()
                report["counters"]["source_links_added"] += 1
        for extra_spec in block.get("additional_sources") or []:
            extra = self._resolve_or_prepare_source(
                db,
                competition=competition,
                source_url=extra_spec.get("source_url"),
                source_type=extra_spec.get("source_type", "official_notice"),
                authority_level=extra_spec.get("authority_level", "S"),
                raw_title=extra_spec.get("raw_title"),
                published_at=extra_spec.get("published_at"),
                    evidence_file=extra_spec.get("evidence_file"),
                    notes=extra_spec.get("notes"),
                    repository=extra_spec.get("repository"),
                    stamp=stamp,
                dry_run=dry_run,
                report=report,
            )
            if extra is not None and extra.competition_edition_id != edition.id:
                if dry_run:
                    report["counters"]["source_links_added"] += 1
                else:
                    extra.competition_edition_id = edition.id
                    db.flush()
                    report["counters"]["source_links_added"] += 1

        fields = block.get("fields") or {}
        for raw_field, value in fields.items():
            if raw_field not in EDITION_EDITABLE_FIELDS:
                action.setdefault("errors", []).append(f"field not editable: {raw_field}")
                continue
            current = getattr(edition, raw_field)
            incoming_dt = _parse_dt(value)
            incoming = incoming_dt if incoming_dt else value
            if _values_equal(current, incoming):
                continue
            status_placeholder = (
                raw_field in {"edition_status", "current_status"}
                and str(current or "") == "unknown"
            )
            allow_overwrite = raw_field in (block.get("allow_overwrite") or [])
            if (
                current not in (None, "", [], {})
                and not allow_overwrite
                and not status_placeholder
            ):
                action.setdefault("conflicts", []).append(
                    {
                        "field": raw_field,
                        "current": _json_safe(current),
                        "incoming": _json_safe(incoming),
                    }
                )
                report["counters"]["competition_fields_conflict"] += 1
                continue
            if source is None:
                continue
            block_evidence = (
                block.get("evidence_level")
                or evidence_level_for_source(source.source_type, source.authority_level)
            )
            if block_evidence == "LEVEL_3" and not block.get("source_scope"):
                action.setdefault("errors", []).append(
                    "LEVEL_3 secondary evidence requires source_scope"
                )
                continue
            if not evidence_allowed(raw_field, block_evidence, spec=block):
                action.setdefault("errors", []).append(
                    f"evidence {block_evidence} cannot prove {raw_field}"
                )
                continue
            if dry_run:
                report["counters"]["edition_fields_changed"] += 1
                action.setdefault("field_changes", []).append(
                    {"field": raw_field, "old": _json_safe(current), "new": _json_safe(incoming)}
                )
                continue
            changed = self.freshness.update_edition_fact(
                db,
                edition,
                field_name=raw_field,
                value=incoming,
                changed_at=stamp,
                source_url=source.source_url,
                source_name=source.source_name,
                verification_status="verified_official",
            )
            if changed:
                report["counters"]["edition_fields_changed"] += 1
            self._upsert_fact_row(
                db,
                competition=competition,
                edition=edition,
                field_name=raw_field,
                value=_json_safe(incoming),
                source=source,
                stamp=stamp,
                notes=block.get("notes"),
                evidence_level=block_evidence,
                homepage_type=block.get("homepage_type"),
                source_scope=block.get("source_scope"),
            )

        for raw_field in block.get("nullify") or []:
            if raw_field not in EDITION_EDITABLE_FIELDS:
                continue
            current = getattr(edition, raw_field)
            if current is None:
                continue
            if dry_run:
                report["counters"]["edition_fields_changed"] += 1
                action.setdefault("field_changes", []).append(
                    {"field": raw_field, "old": _json_safe(current), "new": None}
                )
                continue
            self.freshness.update_edition_fact(
                db,
                edition,
                field_name=raw_field,
                value=None,
                changed_at=stamp,
                source_url=source.source_url if source else block.get("source_url", ""),
                source_name=source.source_name if source else None,
                verification_status="verified_official",
            )
            report["counters"]["edition_fields_changed"] += 1

        for fact_name, fact_value in (block.get("facts") or {}).items():
            fact_source = source
            fact_notes = block.get("notes")
            if isinstance(fact_value, dict) and "value" in fact_value:
                fact_source = self._resolve_or_prepare_source(
                    db,
                    competition=competition,
                    source_url=fact_value.get("source_url"),
                    source_type=fact_value.get("source_type", "official_notice"),
                    authority_level=fact_value.get("authority_level", "S"),
                    raw_title=fact_value.get("raw_title"),
                    published_at=fact_value.get("published_at"),
                    evidence_file=fact_value.get("evidence_file"),
                    notes=fact_value.get("notes"),
                    repository=fact_value.get("repository"),
                    stamp=stamp,
                    dry_run=dry_run,
                    report=report,
                )
                if (
                    fact_source is not None
                    and fact_source.competition_edition_id != edition.id
                ):
                    if dry_run:
                        report["counters"]["source_links_added"] += 1
                    else:
                        fact_source.competition_edition_id = edition.id
                        db.flush()
                        report["counters"]["source_links_added"] += 1
                fact_value = fact_value["value"]
            if dry_run:
                existing = db.execute(
                    select(CompetitionFactSource).where(
                        CompetitionFactSource.competition_id == competition.id,
                        CompetitionFactSource.competition_edition_id == edition.id,
                        CompetitionFactSource.field_name == fact_name,
                        CompetitionFactSource.source_url
                        == (
                            fact_source.source_url
                            if fact_source
                            else block.get("source_url")
                        ),
                    )
                ).scalars().first()
                if existing is None:
                    report["counters"]["fact_rows_added"] += 1
                continue
            if fact_source is None:
                continue
            self._upsert_fact_row(
                db,
                competition=competition,
                edition=edition,
                field_name=fact_name,
                value=fact_value,
                source=fact_source,
                stamp=stamp,
                notes=fact_notes,
            )
        if not dry_run and source is not None:
            self.freshness.mark_verified(
                edition,
                observed_at=stamp,
                source_updated_at=_parse_dt(block.get("published_at")),
            )
            record_admin_action(
                db,
                admin_id=None,
                action="v12.enrichment.edition",
                object_type="competition_edition",
                object_id=edition.id,
                after={"year": year, "source_url": source.source_url},
            )
            report["counters"]["audit_rows"] += 1
        return action

    # ------------------------------------------------------------------ #
    def _resolve_or_prepare_source(
        self,
        db: Session,
        *,
        competition: Competition,
        source_url: str | None,
        source_type: str | None,
        authority_level: str | None,
        raw_title: str | None,
        published_at: str | None,
        evidence_file: str | None,
        notes: str | None,
        repository: str | None,
        stamp: datetime,
        dry_run: bool,
        report: dict[str, Any],
    ) -> CompetitionSource | None:
        if not source_url:
            return None
        existing = db.execute(
            select(CompetitionSource).where(
                CompetitionSource.competition_id == competition.id,
                CompetitionSource.source_url == source_url,
            )
        ).scalars().first()
        if existing is not None:
            report["counters"]["sources_existing"] += 1
            if raw_title and (not existing.raw_title or not existing.source_name):
                existing.raw_title = raw_title
                existing.source_name = raw_title
                db.flush()
            return existing
        if evidence_file:
            evidence_path = PROJECT_ROOT / evidence_file
            if not evidence_path.exists():
                report["counters"]["skipped_evidence_missing"] += 1
                return None
        if dry_run:
            report["counters"]["sources_added"] += 1
            level = (authority_level or authority_level_for(source_type) or "D").upper()
            return SimpleNamespace(
                source_type=source_type or "official_notice",
                authority_level=level if level in AUTHORITY_LEVELS else "D",
                source_name=raw_title,
                source_url=source_url,
                reliability_tier={"S": 1, "A": 2, "B": 2, "C": 3, "D": 4}.get(
                    level if level in AUTHORITY_LEVELS else "D", 4
                ),
                published_at=_parse_dt(published_at),
                competition_edition_id=None,
            )
        level = (authority_level or authority_level_for(source_type) or "D").upper()
        if level not in AUTHORITY_LEVELS:
            level = "D"
        published = _parse_dt(published_at)
        source = CompetitionSource(
            competition_id=competition.id,
            source_type=source_type or "official_notice",
            authority_level=level,
            source_name=raw_title,
            source_url=source_url,
            source_repository=repository or "v12-fact-registry",
            source_platform="official_website",
            published_at=published,
            crawled_at=stamp,
            retrieved_at=stamp,
            is_official=True,
            is_verified=True,
            credibility_score=100,
            reliability_tier={"S": 1, "A": 2, "B": 2, "C": 3, "D": 4}[level],
            verification_status=(
                "verified_official" if level in {"S", "A"} else "school_confirmed"
            ),
            raw_title=raw_title,
            metadata_json={
                "evidence_file": evidence_file,
                "authority_level": level,
                "enrichment_notes": notes,
            },
            is_demo=False,
        )
        db.add(source)
        db.flush()
        report["counters"]["sources_added"] += 1
        return source

    def _upsert_fact_row(
        self,
        db: Session,
        *,
        competition: Competition,
        edition: CompetitionEdition | None,
        field_name: str,
        value: Any,
        source: CompetitionSource,
        stamp: datetime,
        notes: str | None = None,
        evidence_level: str | None = None,
        homepage_type: str | None = None,
        source_scope: str | None = None,
    ) -> bool:
        existing = db.execute(
            select(CompetitionFactSource).where(
                CompetitionFactSource.competition_id == competition.id,
                CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
                CompetitionFactSource.field_name == field_name,
                CompetitionFactSource.source_url == source.source_url,
            )
        ).scalars().first()
        payload = {
            "fact_value": value,
            "source_type": source.source_type,
            "source_name": source.source_name,
            "reliability_tier": source.reliability_tier,
            "source_level": evidence_level
            or evidence_level_for_source(source.source_type, source.authority_level),
            "is_official": True,
            "verification_status": {
                "LEVEL_1": "verified_official",
                "LEVEL_2": "authority_confirmed",
                "LEVEL_3": "secondary_verified",
            }.get(
                evidence_level
                or evidence_level_for_source(source.source_type, source.authority_level),
                "secondary_source_only",
            ),
            "published_at": source.published_at,
            "observed_at": stamp,
            "last_verified_at": stamp,
            "notes": self._provenance_notes(
                notes,
                evidence_level=evidence_level,
                homepage_type=homepage_type,
                source_scope=source_scope,
            ),
        }
        if existing is not None:
            for key, item in payload.items():
                setattr(existing, key, item)
            return False
        db.add(
            CompetitionFactSource(
                competition_id=competition.id,
                competition_edition_id=edition.id if edition else None,
                field_name=field_name,
                source_url=source.source_url,
                **payload,
            )
        )
        return True

    @staticmethod
    def _provenance_notes(
        notes: str | None,
        *,
        evidence_level: str | None,
        homepage_type: str | None,
        source_scope: str | None,
    ) -> str | None:
        if not any((notes, evidence_level, homepage_type, source_scope)):
            return None
        parts = []
        if notes:
            parts.append(f"note={notes}")
        if evidence_level:
            parts.append(f"evidence_level={evidence_level}")
        if homepage_type:
            parts.append(f"official_homepage_type={homepage_type}")
        if source_scope:
            parts.append(f"source_scope={source_scope}")
        return "; ".join(parts)

    # ------------------------------------------------------------------ #
    def fill_official_website_from_sources(
        self,
        db: Session,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Set Competition.official_website from verified S website sources."""
        competitions = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                )
            ).scalars()
        )
        counters = {
            "checked": len(competitions),
            "would_set": 0,
            "set": 0,
            "unchanged": 0,
            "no_website_source": 0,
        }
        details: list[dict[str, Any]] = []
        for competition in competitions:
            if competition.official_website:
                counters["unchanged"] += 1
                continue
            candidates = [
                source
                for source in competition.sources
                if source.is_verified
                and source.authority_level == "S"
                and source.source_type in WEBSITE_SOURCE_TYPES
                and source.source_url
                and not source.source_url.startswith("local-source://")
            ]
            if not candidates:
                counters["no_website_source"] += 1
                continue
            source = sorted(
                candidates,
                key=lambda s: (0 if s.source_type in {"competition_official_website", "official_competition_website"} else 1, len(s.source_url)),
            )[0]
            value = _domain_root(source.source_url)
            details.append(
                {
                    "competition_id": competition.id,
                    "name": competition.name,
                    "official_website": value,
                    "source_url": source.source_url,
                    "source_type": source.source_type,
                    "evidence": (source.metadata_json or {}).get("evidence_file"),
                }
            )
            if dry_run:
                counters["would_set"] += 1
                continue
            setattr(competition, "official_website", value)
            self._upsert_fact_row(
                db,
                competition=competition,
                edition=None,
                field_name="official_website",
                value=value,
                source=source,
                stamp=datetime.now(timezone.utc),
                notes="自动从已核验的S级官网来源回填（域名根）",
                evidence_level="LEVEL_1",
                homepage_type=classify_homepage(source.source_url, source.source_type),
            )
            record_admin_action(
                db,
                admin_id=None,
                action="v12.enrichment.official_website_autofill",
                object_type="competition",
                object_id=competition.id,
                before=None,
                after=value,
            )
            counters["set"] += 1
        return {"counters": counters, "details": details}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _status_snapshot(db: Session) -> dict[str, dict[str, int]]:
        def one(rows) -> dict[str, int]:
            out: dict[str, int] = {}
            for row in rows:
                out[row.verification_status] = out.get(row.verification_status, 0) + 1
            return out

        return {
            "competitions": one(
                db.execute(select(Competition).where(Competition.is_demo.is_(False))).scalars()
            ),
            "editions": one(db.execute(select(CompetitionEdition)).scalars()),
        }

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
