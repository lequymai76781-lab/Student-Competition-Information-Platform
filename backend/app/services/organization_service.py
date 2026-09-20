"""V0.9 organization registry sync (idempotent, read-model additive).

Populates organizations + competition_organizations from the existing free-text
organizer columns. Existing competition rows are NOT modified so the current
API and frontend stay untouched.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, CompetitionOrganization, Organization

ROLE_FIELDS = {
    "organizer": "organizer",
    "co_organizer": "co_organizers",
    "guiding": "guiding_organizations",
    "undertaker": "undertakers",
}


def split_org_names(value: str | None) -> list[str]:
    """Split a free-text organizer string into candidate organization names."""
    if not value:
        return []
    parts = re.split(r"[、,，;；/｜|]", value)
    names: list[str] = []
    for part in parts:
        name = part.strip().strip("[]（）()\"'“”‘’　 ")
        if not name:
            continue
        if name not in names:
            names.append(name)
    return names


def normalize_org_name(name: str) -> str:
    """Normalize punctuation/whitespace for dedupe; does not translate aliases."""
    normalized = name.strip()
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def lead_review_status(
    *,
    matched_competition_id: int | None,
    matched_edition_id: int | None,
    needs_review: bool,
    verification_status: str | None = None,
) -> str:
    """Map existing lead state to the V0.9 review_status state machine."""
    if matched_competition_id is not None and not needs_review:
        return "verified"
    if matched_competition_id is not None or matched_edition_id is not None:
        return "matched"
    return "pending"


class OrganizationService:
    def __init__(self) -> None:
        self._org_was_created = False

    def sync_competition_organizations(self, db: Session) -> dict[str, Any]:
        created_orgs = 0
        created_links = 0
        updated_links = 0
        role_counts: Counter[str] = Counter()
        org_type_counts: Counter[str] = Counter()

        competitions = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                )
            ).scalars()
        )
        for competition in competitions:
            for role, field_name in ROLE_FIELDS.items():
                value = getattr(competition, field_name, None)
                if isinstance(value, str):
                    display_names = split_org_names(value)
                elif isinstance(value, list):
                    display_names = []
                    for item in value:
                        display_names.extend(split_org_names(str(item)))
                else:
                    display_names = []
                for display_name in display_names:
                    organization = self._upsert_organization(
                        db,
                        display_name,
                        org_type="other",
                    )
                    if organization is None:
                        continue
                    created_orgs += 1 if self._org_was_created else 0
                    org_type_counts[organization.org_type] += 1
                    role_counts[role] += 1
                    link = db.execute(
                        select(CompetitionOrganization).where(
                            CompetitionOrganization.competition_id == competition.id,
                            CompetitionOrganization.organization_id == organization.id,
                            CompetitionOrganization.role == role,
                        )
                    ).scalar_one_or_none()
                    payload = {
                        "display_name": display_name,
                        "is_verified": False,
                    }
                    if link is None:
                        db.add(
                            CompetitionOrganization(
                                competition_id=competition.id,
                                organization_id=organization.id,
                                role=role,
                                **payload,
                            )
                        )
                        created_links += 1
                    else:
                        changed = False
                        for key, item in payload.items():
                            if getattr(link, key) != item:
                                setattr(link, key, item)
                                changed = True
                        updated_links += int(changed)

        db.flush()
        return {
            "competitions_scanned": len(competitions),
            "organizations_created": created_orgs,
            "links_created": created_links,
            "links_updated": updated_links,
            "roles": dict(sorted(role_counts.items())),
        }

    def backfill_lead_review_status(self, db: Session) -> dict[str, int]:
        from app.models import CompetitionLead

        leads = list(db.execute(select(CompetitionLead)).scalars())
        counts: Counter[str] = Counter()
        for lead in leads:
            status = lead_review_status(
                matched_competition_id=lead.matched_competition_id,
                matched_edition_id=lead.matched_edition_id,
                needs_review=lead.needs_review,
                verification_status=lead.verification_status,
            )
            if lead.review_status != status:
                lead.review_status = status
            counts[status] += 1
        db.flush()
        return dict(sorted(counts.items()))

    def _upsert_organization(
        self,
        db: Session,
        display_name: str,
        *,
        org_type: str,
    ) -> Organization | None:
        name = display_name.strip().strip("（）()[]")
        if not name:
            return None
        normalized = normalize_org_name(name)
        self._org_was_created = False
        organization = db.execute(
            select(Organization).where(Organization.name == name)
        ).scalar_one_or_none()
        if organization is None:
            candidates = list(db.execute(select(Organization)).scalars())
            organization = next(
                (row for row in candidates if normalize_org_name(row.name) == normalized),
                None,
            )
        if organization is None:
            organization = Organization(
                name=name,
                aliases=[display_name] if display_name != name else [],
                org_type=org_type,
                is_verified=False,
                is_demo=False,
            )
            db.add(organization)
            db.flush()
            self._org_was_created = True
        else:
            aliases = list(organization.aliases or [])
            if display_name != organization.name and display_name not in aliases:
                aliases.append(display_name)
                organization.aliases = aliases
        return organization
