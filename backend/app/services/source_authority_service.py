"""V0.9 source authority and field-level proof rules.

Rules are implemented in code, not only documented:

- Every source_type maps to an authority level S/A/B/C/D.
- A source only proves the field categories its level is allowed to confirm.
- verified_official at the Competition/Edition layer requires an S-level
  (or verified organizer-level A) source; university/college sources can only
  confirm school-level facts (school_confirmed).
"""

from __future__ import annotations

from typing import Iterable

AUTHORITY_LEVELS = ("S", "A", "B", "C", "D")
AUTHORITY_ORDER = {level: index for index, level in enumerate(AUTHORITY_LEVELS)}

# source_type -> authority level (kept in sync with current data + code lists)
SOURCE_TYPE_AUTHORITY: dict[str, str] = {
    # S: national/ministry/central government/organizer official
    "ministry": "S",
    "ministry_official_notice": "S",
    "central_government": "S",
    "government": "S",
    "government_official_notice": "S",
    "official": "S",
    "official_notice": "S",
    "competition_official": "S",
    "competition_official_site": "S",
    "competition_official_website": "S",
    "official_competition_committee": "S",
    "official_competition_website": "S",
    "organizer_official": "S",
    "organizer_official_notice": "S",
    "committee_official": "S",
    # A: national societies / higher-education associations
    "higher_education_association": "A",
    "national_academic_association": "A",
    "academic_association": "A",
    "association_official_notice": "A",
    "society_official_notice": "A",
    "national_society": "A",
    # B: provincial government / university official pages & policy catalogs
    "provincial_government": "B",
    "provincial_official_notice": "B",
    "university": "B",
    "university_official": "B",
    "university_official_notice": "B",
    "university_policy": "B",
    "school_catalog": "B",
    # C: college / lab / research institute
    "college": "C",
    "college_official_notice": "C",
    "research_institute": "C",
    "laboratory": "C",
    # D: third-party and passive discovery
    "github_seed": "D",
    "github": "D",
    "third_party_platform": "D",
    "social_media": "D",
    "wechat": "D",
    "source_repository_discovery": "D",
    "manual": "D",
    "other": "D",
    "unknown": "D",
}

# S + A source types can confirm national/competition-identity facts.
OFFICIAL_COMPETITION_SOURCE_TYPES = {
    source_type
    for source_type, level in SOURCE_TYPE_AUTHORITY.items()
    if level in {"S", "A"}
}
S_AUTHORITY_SOURCE_TYPES = {
    source_type for source_type, level in SOURCE_TYPE_AUTHORITY.items() if level == "S"
}
A_AUTHORITY_SOURCE_TYPES = {
    source_type for source_type, level in SOURCE_TYPE_AUTHORITY.items() if level == "A"
}
UNIVERSITY_SOURCE_TYPES = {
    source_type
    for source_type, level in SOURCE_TYPE_AUTHORITY.items()
    if level in {"B", "C"}
}

# Field categories a source can confirm. B/C sources prove school facts only.
FIELD_CATEGORY_ALLOWED_LEVELS: dict[str, set[str]] = {
    # National facts: S or A (organizer-level association) only
    "competition_identity": {"S", "A"},
    "competition_profile": {"S", "A"},
    "catalog_level": {"S", "A"},
    "organizer_final": {"S", "A"},
    "official_website": {"S", "A"},
    "national_registration_deadline": {"S", "A"},
    "national_submission_deadline": {"S", "A"},
    "national_competition_status": {"S", "A"},
    "national_edition": {"S", "A"},
    # School facts: B (university) or C (college) sources
    "school_participation": {"S", "A", "B", "C"},
    "campus_registration_deadline": {"B", "C"},
    "campus_submission_deadline": {"B", "C"},
    "school_level_recognition": {"B", "C"},
    "school_policy": {"B", "C"},
    "responsible_department": {"B", "C"},
}

# competition fields -> proof category
FIELD_CATEGORY: dict[str, str] = {
    "name": "competition_identity",
    "short_name": "competition_identity",
    "english_name": "competition_identity",
    "former_names": "competition_identity",
    "aliases": "competition_identity",
    "category": "catalog_level",
    "competition_level": "catalog_level",
    "description": "competition_profile",
    "competition_format": "competition_profile",
    "competition_scope": "competition_profile",
    "country_or_region": "competition_profile",
    "target_students": "competition_profile",
    "team_type": "competition_profile",
    "typical_schedule": "competition_profile",
    "organizer": "organizer_final",
    "co_organizers": "organizer_final",
    "guiding_organizations": "organizer_final",
    "undertakers": "organizer_final",
    "official_website": "official_website",
    "official_registration_deadline": "national_registration_deadline",
    "submission_deadline": "national_submission_deadline",
    "official_submission_deadline": "national_submission_deadline",
    "official_competition_date": "national_competition_status",
    "current_status": "national_competition_status",
    "freshness_status": "national_competition_status",
    "university_registration_deadline": "campus_registration_deadline",
    "college_registration_deadline": "campus_registration_deadline",
    "internal_registration_deadline": "campus_registration_deadline",
    "campus_registration_deadline": "campus_registration_deadline",
    "campus_registration_start": "campus_registration_deadline",
    "campus_submission_deadline": "campus_submission_deadline",
    "recognition_level": "school_level_recognition",
    "recognized_level": "school_level_recognition",
    "credit_policy": "school_policy",
    "award_policy": "school_policy",
    "responsible_department": "responsible_department",
}


def authority_level_for(source_type: str | None) -> str | None:
    if not source_type:
        return None
    return SOURCE_TYPE_AUTHORITY.get(source_type.strip(), "D")


def can_prove(source_type: str | None, field: str | None) -> bool:
    """Whether a source type may serve as final confirmation for a field."""
    level = authority_level_for(source_type)
    category = FIELD_CATEGORY.get(field or "", "competition_profile")
    allowed = FIELD_CATEGORY_ALLOWED_LEVELS.get(category, {"S", "A"})
    return level in allowed


def is_national_authority_source(source_type: str | None) -> bool:
    return authority_level_for(source_type) in {"S", "A"}


def competition_status_from_source_levels(
    verified_levels: Iterable[str | None],
    *,
    has_any_source: bool,
    entity_type: str | None = None,
) -> str:
    """Map the set of verified source authority levels to a competition state."""
    if entity_type and entity_type not in {"competition", "series", "track"}:
        return "suspected"
    levels = {level for level in verified_levels if level}
    if "S" in levels:
        return "verified_official"
    if "A" in levels:
        return "authority_confirmed"
    if "B" in levels:
        return "school_confirmed"
    if has_any_source:
        return "pending_verification"
    return "unverified"


def lead_state_from_competition_status(
    competition_status: str | None,
    *,
    matched: bool,
    needs_review: bool,
) -> str:
    if competition_status in {"verified_official", "authority_confirmed"} and matched and not needs_review:
        return "verified"
    if matched:
        return "matched"
    return "pending"
