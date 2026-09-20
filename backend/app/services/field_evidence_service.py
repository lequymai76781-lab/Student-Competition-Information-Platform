"""V13 field-level evidence gradients.

Identity (is this a real official Competition?) stays gated by S/A sources.
Individual display fields may be proven by lower-level institutional sources,
but the proof level is always recorded with the fact and can never silently
overwrite a higher-level value.

Levels:
    LEVEL_1 primary official   - ministry/government docs, official site,
                                 official committee, official charter,
                                 official registration system
    LEVEL_2 institutional      - national society/association, host university
                                 official pages, official host institutions,
                                 formal research institutes
    LEVEL_3 university official secondary
                               - university official notices/news that explicitly
                                 quote a national fact; never identity proof
    LEVEL_4 discovery only     - third-party pages, media reprints, summaries

Homepage types (official_homepage_type):
    independent_site | organizer_page | official_topic_page | annual_site |
    registration_system | none
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


EVIDENCE_LEVELS = ("LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4")
EVIDENCE_ORDER = {level: index for index, level in enumerate(EVIDENCE_LEVELS)}

IDENTITY_LEVELS = {"LEVEL_1", "LEVEL_2"}

# Fields that may accept LEVEL_3 institutional-official/secondary evidence when
# the statement is explicit. Identity/current-status fields never accept L3.
SECONDARY_OK_FIELDS = {
    "organizer",
    "co_organizers",
    "undertakers",
    "guiding_organizations",
    "target_students",
    "founded_year",
    "first_held_year",
    "official_website",
}

# Fields that may accept LEVEL_3 for edition/history rows (host, name, dates,
# result links) but not for official identity/national status.
EDITION_SECONDARY_OK_FIELDS = {
    "edition_name",
    "host_location",
    "competition_start",
    "competition_end",
    "official_competition_date",
    "edition_status",
    "current_status",
}

THIRD_PARTY_HOSTS = {
    "saikr.com",
    "www.saikr.com",
    "baike.baidu.com",
    "baijiahao.baidu.com",
    "mp.weixin.qq.com",
}


def default_evidence_level(source_type: str | None, authority_level: str | None) -> str:
    """Conservative default mapping used when a registry entry does not
    explicitly declare an evidence level."""
    authority = (authority_level or "").upper()
    source_type = (source_type or "").strip()
    if authority == "S":
        if source_type.startswith(("university", "college")):
            return "LEVEL_2"
        return "LEVEL_1"
    if authority == "A":
        return "LEVEL_2"
    if authority == "B":
        if source_type in {"university_official", "university_official_notice", "university_policy"}:
            return "LEVEL_3"
        return "LEVEL_3"
    if authority == "C":
        return "LEVEL_3"
    return "LEVEL_4"


def evidence_level_for_source(source_type: str | None, authority_level: str | None) -> str:
    return default_evidence_level(source_type, authority_level)


def is_identity_qualified(evidence_level: str) -> bool:
    return evidence_level in IDENTITY_LEVELS


def classify_homepage(
    source_url: str,
    source_type: str | None = None,
    *,
    host: str | None = None,
    meta_title: str | None = None,
) -> str:
    """Classify an official homepage into one of the supported types.
    Third-party domains are always 'none' unless the URL itself is a
    registration system run by the competition (handled by explicit registry
    metadata)."""
    parsed = urlparse(source_url)
    domain = (parsed.netloc or "").lower()
    if domain in THIRD_PARTY_HOSTS:
        return "none"
    if source_type in {
        "competition_official_website",
        "official_competition_website",
        "competition_official_site",
    }:
        return "independent_site"
    if source_type in {"registration_system", "official_registration_system"}:
        return "registration_system"
    if source_type in {
        "organizer_official",
        "organizer_official_notice",
        "organizer_page",
        "government_official_notice",
        "official_notice",
    }:
        return "organizer_page"
    if source_type in {"annual_site", "competition_annual_site"}:
        return "annual_site"
    if host:
        return "organizer_page"
    return "none"


@dataclass(frozen=True)
class FieldPolicy:
    field: str
    min_level: str = "LEVEL_1"
    allow_secondary: bool = False
    allow_l3_website: bool = False


def field_policy(field: str, spec: dict | None = None) -> FieldPolicy:
    spec = spec or {}
    allow_secondary = field in SECONDARY_OK_FIELDS
    min_level = "LEVEL_1"
    homepage_type = spec.get("homepage_type")
    allow_l3_website = (
        field == "official_website"
        and homepage_type in {
            "independent_site",
            "organizer_page",
            "official_topic_page",
            "registration_system",
            "annual_site",
        }
    )
    return FieldPolicy(
        field=field,
        min_level=min_level,
        allow_secondary=allow_secondary,
        allow_l3_website=allow_l3_website,
    )


def evidence_allowed(
    field: str,
    evidence_level: str,
    *,
    spec: dict | None = None,
) -> bool:
    """Whether a fact at the given evidence level may fill the field.
    Identity-critical status fields are not passed here; those are governed by
    FactIntelligenceService.refresh_verification."""
    policy = field_policy(field, spec)
    level_index = EVIDENCE_ORDER.get(evidence_level, 3)
    if level_index >= EVIDENCE_ORDER["LEVEL_4"]:
        return False
    if field == "official_website":
        return level_index <= EVIDENCE_ORDER["LEVEL_2"] or (
            policy.allow_l3_website and level_index == EVIDENCE_ORDER["LEVEL_3"]
        )
    if field in EDITION_SECONDARY_OK_FIELDS:
        return level_index <= EVIDENCE_ORDER["LEVEL_3"]
    if field in SECONDARY_OK_FIELDS:
        return level_index <= EVIDENCE_ORDER["LEVEL_3"]
    return level_index <= EVIDENCE_ORDER["LEVEL_2"]
