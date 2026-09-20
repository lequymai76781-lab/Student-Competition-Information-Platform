"""Academic Conference V1 authority rules and controlled vocabulary.

Conference identity proof intentionally differs from the competition module:

- S: CAST official directories, conference official sites/CFP pages, IEEE/ACM
  official conference pages, national primary society meeting pages and
  sub-committee official conference pages.
- A: national society notices, research institutes, conference organizers and
  official publishers (identity-supporting, not identity-final without S).
- B: university / college / research-department official pages. They attach
  school relations and campus facts but can never verify a conference identity.
- C: third-party directories, conference aggregators, commercial conference
  platforms and search snippets. Discovery only; cannot verify identity.

The module contains no database writes, so tests can exercise the rules with
plain objects.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Iterable

CONFERENCE_AUTHORITY_LEVELS = ("S", "A", "B", "C")
AUTHORITY_ORDER = {level: index for index, level in enumerate(CONFERENCE_AUTHORITY_LEVELS)}

# Controlled coarse-grained disciplines (V1: no deep discipline tree).
CONFERENCE_DISCIPLINES: dict[str, dict[str, str]] = {
    "computer_science": {"name_en": "Computer Science", "name_zh": "计算机科学"},
    "artificial_intelligence": {"name_en": "Artificial Intelligence", "name_zh": "人工智能"},
    "data_science": {"name_en": "Data Science", "name_zh": "数据科学"},
    "engineering": {"name_en": "Engineering", "name_zh": "工程技术"},
    "sports_science": {"name_en": "Sports Science", "name_zh": "体育科学"},
    "journalism_communication": {"name_en": "Journalism & Communication", "name_zh": "新闻传播学"},
    "management": {"name_en": "Management Science", "name_zh": "管理科学"},
    "economics": {"name_en": "Economics", "name_zh": "经济学"},
    "education": {"name_en": "Education", "name_zh": "教育学"},
    "medicine": {"name_en": "Medicine", "name_zh": "医药卫生"},
    "natural_sciences": {"name_en": "Natural Sciences", "name_zh": "自然科学"},
    "humanities": {"name_en": "Humanities", "name_zh": "人文科学"},
    "interdisciplinary": {"name_en": "Interdisciplinary", "name_zh": "交叉学科"},
}

# source_type -> authority level (conference-specific)
CONFERENCE_SOURCE_TYPE_AUTHORITY: dict[str, str] = {
    # S: CAST directory / conference official identity & date pages
    "cast_official_directory": "S",
    "conference_official_site": "S",
    "conference_official_cfp": "S",
    "conference_official_registration": "S",
    "international_professional_org": "S",
    "national_society_official_meeting_page": "S",
    "subcommittee_official": "S",
    # A: national societies (general notices), organizers, publishers, institutes
    "national_society": "A",
    "national_society_notice": "A",
    "association_official_notice": "A",
    "subcommittee_notice": "A",
    "organizer_official": "A",
    "research_institute_official": "A",
    "publisher_official": "A",
    # B: school/department sources - supplementary only
    "university_official": "B",
    "university_conference_notice": "B",
    "college_official": "B",
    "school_conference_notice": "B",
    # C: discovery only - never identity proof
    "third_party_directory": "C",
    "commercial_conference_platform": "C",
    "conference_aggregator": "C",
    "search_summary": "C",
    "wechat_republish": "C",
    "social_media": "C",
    "manual": "C",
    "other": "C",
    "unknown": "C",
}

CONFERENCE_ORGANIZATION_ROLES = (
    "organizer",
    "co_organizer",
    "undertaker",
    "co_undertaker",
    "host",
    "academic_support",
    "local_organizer",
    "recommending_organization",
    "publisher",
)

SCHOOL_CONFERENCE_RELATION_TYPES = (
    "organizer",
    "co_organizer",
    "undertaker",
    "co_undertaker",
    "host",
    "academic_support",
    "local_organizer",
    "published_notice",
    "participation_notice",
    "call_for_papers_notice",
    "reimbursement_notice",
    "other",
)

CONFERENCE_SCOPES = ("national", "international", "regional")
CONFERENCE_FREQUENCIES = ("annual", "biennial", "irregular", "unknown")

# identity-level authority states (independent for Series and Edition)
AUTHORITY_STATUSES = (
    "verified_official",
    "authority_confirmed",
    "pending_verification",
    "unverified",
)

# V1 risk markers; never an auto-generated "quality score".
RISK_FLAG_VOCABULARY = (
    "official_org_missing",
    "official_site_missing",
    "organizer_unclear",
    "indexing_claim_unverified",
    "no_history_found",
    "commercial_intermediary_only",
    "duplicate_name_risk",
)

DISCOVERY_CANDIDATE_STATUSES = (
    "pending",
    "reviewing",
    "matched",
    "verified",
    "duplicate",
    "rejected",
    "non_conference",
)

REJECTION_REASONS = (
    "unofficial_source_only",
    "commercial_conference",
    "predatory_conference",
    "duplicate",
    "insufficient_evidence",
    "inactive",
    "irrelevant_to_platform",
    "unknown",
)

STUDENT_VALUE_TAGS = (
    "undergraduate_friendly",
    "graduate_friendly",
    "paper_submission",
    "student_paper",
    "poster",
    "workshop",
    "doctoral_consortium",
    "student_forum",
    "youth_forum",
    "academic_exchange",
    "publication_opportunity",
    "research_resume_value",
)

AUDIENCE_VALUES = (
    "undergraduate",
    "master",
    "phd",
    "researcher",
    "faculty",
    "industry",
)

# Student-facing opportunity tags that may appear at Edition level. They are
# never copied from the Series and never inferred from history.
STUDENT_OPPORTUNITY_TAGS = (
    "student_paper",
    "student_forum",
    "doctoral_consortium",
    "poster",
    "workshop",
    "youth_forum",
    "undergraduate_friendly",
    "graduate_friendly",
)

# Official deadline fields that make a real Edition "actionable" for students.
ACTIONABLE_DEADLINE_FIELDS = (
    "abstract_deadline",
    "paper_deadline",
    "poster_deadline",
    "workshop_deadline",
    "registration_deadline",
)

# V1.2 student-opportunity controlled vocabulary. Only official pages that
# state the activity may create a row; no type is force-populated.
OPPORTUNITY_TYPES = (
    "paper_submission",
    "abstract_submission",
    "poster",
    "student_paper",
    "student_forum",
    "undergraduate_forum",
    "graduate_forum",
    "doctoral_consortium",
    "young_scholar_forum",
    "workshop",
    "tutorial",
    "mentoring",
    "volunteer",
    "student_registration",
    "travel_grant",
    "student_award",
    "competition",
    "summer_school",
    "other",
)

# Audience vocabulary: a generic official "students" stays "student" and is
# never auto-expanded into undergraduate + master + phd.
OPPORTUNITY_AUDIENCES = (
    "undergraduate",
    "master",
    "phd",
    "graduate",
    "early_career",
    "researcher",
    "faculty",
    "student",
    "all",
    "unknown",
)

DISCIPLINE_RELATIONSHIP_TYPES = ("direct", "related", "interdisciplinary")

OPPORTUNITY_EVIDENCE_STATUSES = (
    "full_page_verified",
    "access_limited",
    "official_site_maintenance",
    "robots_restricted",
    "snippet_only",
    "pending_evidence",
)

# Official wording captured from the page at verification time, used only when
# real dates cannot decide the state ("submissions are now open" without a
# deadline -> open; "coming soon" -> upcoming). Never inferred from history.
OPPORTUNITY_STATUS_HINTS = ("open", "upcoming")

# Discovery pool entity kinds (V1.2.1): a noisy find may point at a suspected
# series, a specific edition, or a student opportunity page. The candidate row
# itself is never treated as verified evidence.
DISCOVERY_ENTITY_TYPES = (
    "conference_series",
    "conference_edition",
    "conference_opportunity",
)

# A real deadline within this many days of today is "closing_soon".
ACTIONABLE_CLOSING_SOON_DAYS = 14

VALUE_REASON_TYPES = (
    "recognized_conference",
    "official_student_track",
    "paper_submission_available",
    "poster_available",
    "doctoral_consortium",
    "student_forum",
    "undergraduate_opportunity",
    "graduate_opportunity",
    "student_registration",
    "travel_grant",
    "student_award",
    "national_academic_society",
    "international_academic_society",
    "university_hosted",
    "proceedings_available",
)

INDEXING_CLAIM_STATUSES = (
    "organizer_claimed",
    "publisher_confirmed",
    "database_confirmed",
    "historical_indexed",
    "unknown",
)
INDEXING_CLAIM_ORDER = {status: i for i, status in enumerate(INDEXING_CLAIM_STATUSES)}

PUBLICATION_STATUSES = ("planned", "confirmed", "published", "indexed", "unknown")

EXTERNAL_CLASSIFICATION_SYSTEMS = ("CCF", "CAST_important_conference", "other")


def authority_level_for(source_type: str | None) -> str | None:
    if not source_type:
        return None
    return CONFERENCE_SOURCE_TYPE_AUTHORITY.get(source_type.strip(), "C")


def validate_discipline(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip()
    if code not in CONFERENCE_DISCIPLINES:
        raise ValueError(f"未知会议学科分类: {code!r}（受控分类见 CONFERENCE_DISCIPLINES）")
    return code


def normalize_risk_flags(flags: Iterable[str] | None) -> list[str]:
    if not flags:
        return []
    normalized: list[str] = []
    for flag in flags:
        flag = flag.strip()
        if flag and flag not in normalized:
            normalized.append(flag)
    unknown = [flag for flag in normalized if flag not in RISK_FLAG_VOCABULARY]
    if unknown:
        raise ValueError(f"未知风险标记: {unknown}")
    return normalized


def can_prove_identity(source_type: str | None) -> bool:
    """Only S/A sources may verify conference identity facts."""
    return authority_level_for(source_type) in {"S", "A"}


def is_discovery_only_source(source_type: str | None) -> bool:
    return authority_level_for(source_type) == "C"


def can_prove_school_fact(source_type: str | None) -> bool:
    """School relations may be added from B sources (or better), never from C."""
    level = authority_level_for(source_type)
    return level in {"S", "A", "B"}


def authority_status_from_sources(
    verified_source_types: Iterable[str | None],
    *,
    has_any_source: bool,
) -> str:
    """Compute Series/Edition identity authority from its verified sources."""
    levels = {
        level
        for level in (authority_level_for(source_type) for source_type in verified_source_types)
        if level
    }
    if "S" in levels:
        return "verified_official"
    if "A" in levels:
        return "authority_confirmed"
    if has_any_source:
        return "pending_verification"
    return "unverified"


def summarize_indexing_claims(claims: Iterable[dict[str, Any]] | None) -> str:
    """Highest confirmed claim status (does not invent 'indexed' from claims)."""
    if not claims:
        return "unknown"
    statuses = [str(claim.get("status", "unknown")) for claim in claims]
    ordered = [status for status in INDEXING_CLAIM_STATUSES if status in statuses]
    if not ordered:
        return "unknown"
    return ordered[-1]


def publication_state(publication_status: str | None) -> str:
    status = (publication_status or "unknown").strip()
    if status not in PUBLICATION_STATUSES:
        raise ValueError(f"未知出版状态: {status!r}")
    return status


def external_classification_display(classification: dict[str, Any] | None) -> str | None:
    """e.g. CCF recommended A (2022) -> 'CCF推荐A类' - never 'platform A-level'."""
    if not classification:
        return None
    system = str(classification.get("system", "")).upper()
    level = str(classification.get("level", "")).upper()
    year = classification.get("version_year")
    if system == "CCF":
        return f"CCF推荐{level}类" + (f"（{year}版目录）" if year else "")
    if system == "CAST_IMPORTANT_CONFERENCE":
        return "中国科协重要学术会议" + (f"（{year}指南）" if year else "")
    if system == "CORE":
        return f"CORE推荐{level}类" + (f"（{year}版目录）" if year else "")
    return None


def conference_status_totals(statuses: Iterable[str | None]) -> dict[str, int]:
    return dict(sorted(Counter(status for status in statuses if status).items()))


def risk_flag_totals(rows: Iterable[list[str] | None]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for flags in rows:
        for flag in flags or []:
            counter[flag] += 1
    return dict(sorted(counter.items()))


def validate_student_value_tags(tags: Iterable[str] | None) -> list[str]:
    """Controlled student-value vocabulary; unknown tags are rejected."""
    if not tags:
        return []
    normalized: list[str] = []
    for tag in tags:
        tag = str(tag).strip()
        if not tag:
            continue
        if tag not in STUDENT_VALUE_TAGS:
            raise ValueError(f"未知学生价值标签: {tag!r}")
        if tag not in normalized:
            normalized.append(tag)
    return normalized


def validate_opportunity_type(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value not in OPPORTUNITY_TYPES:
        raise ValueError(f"未知机会类型: {value!r}")
    return value


def validate_opportunity_audience(values: Iterable[str] | None) -> list[str]:
    """Controlled audience; generic 'student' is never auto-split."""
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value:
            continue
        if value not in OPPORTUNITY_AUDIENCES:
            raise ValueError(f"未知机会受众: {value!r}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def validate_discipline_relationship(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value not in DISCIPLINE_RELATIONSHIP_TYPES:
        raise ValueError(f"未知学科关系类型: {value!r}")
    return value


def validate_opportunity_evidence_status(value: str | None) -> str:
    value = (value or "pending_evidence").strip()
    if value not in OPPORTUNITY_EVIDENCE_STATUSES:
        raise ValueError(f"未知机会证据状态: {value!r}")
    return value


def validate_opportunity_status_hint(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value not in OPPORTUNITY_STATUS_HINTS:
        raise ValueError(f"非法机会状态提示: {value!r}")
    return value


def validate_discovery_entity_type(value: str | None) -> str:
    value = (value or "conference_series").strip()
    if value not in DISCOVERY_ENTITY_TYPES:
        raise ValueError(f"非法发现实体类型: {value!r}")
    return value


def _field_value(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def student_opportunity_tags(tags: Iterable[str] | None) -> list[str]:
    """Return the controlled student-opportunity subset of ``tags``.

    An Edition-level tag is only meaningful when the official page of that
    Edition states the corresponding activity; this helper never propagates
    Series tags or historical facts.
    """
    if not tags:
        return []
    wanted = set(STUDENT_OPPORTUNITY_TAGS)
    return [tag for tag in tags if tag in wanted]


def edition_has_actionable_official_info(edition: Any) -> bool:
    """A real current-year Edition is actionable when its official source
    states at least one student-relevant deadline or student opportunity tag.
    Unknown fields stay unknown - an empty Edition is never actionable."""
    if any(_field_value(edition, field) for field in ACTIONABLE_DEADLINE_FIELDS):
        return True
    return bool(student_opportunity_tags(_field_value(edition, "student_value_tags")))


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def edition_actionable_status(edition: Any, *, today: date | None = None) -> str | None:
    """Classify a real Edition by real official dates (never by inference).

    Returns None when the Edition is not actionable for the current year.
    Status values:
    - open: a real official deadline is still in the future;
    - upcoming: no future deadline, but the conference period has not ended;
    - closed: the conference period is over;
    - unknown: actionable info exists but no usable dates were recorded.
    """
    if not edition_has_actionable_official_info(edition):
        return None
    year = _field_value(edition, "year")
    if year is None:
        return "unknown"
    current = today or date.today()
    if int(year) != current.year:
        return None
    deadlines = [
        _as_date(_field_value(edition, field)) for field in ACTIONABLE_DEADLINE_FIELDS
    ]
    if any(deadline and deadline >= current for deadline in deadlines):
        return "open"
    start = _as_date(_field_value(edition, "start_date"))
    end = _as_date(_field_value(edition, "end_date"))
    if end is not None and end < current:
        return "closed"
    if start is not None or end is not None:
        return "upcoming"
    return "unknown"


def opportunity_status(
    opportunity: Any,
    *,
    edition: Any | None = None,
    today: date | None = None,
) -> str:
    """Status of a concrete student opportunity from real dates and, only
    where the official page states a live state without dates, from the
    captured ``status_hint``.

    - closing_soon: deadline is today or within ACTIONABLE_CLOSING_SOON_DAYS;
    - open: deadline is further in the future;
    - upcoming: official open_date is in the future, or the official page says
      "coming soon" with no deadline;
    - closed: deadline already passed;
    - held: no deadline and the edition period is already over;
    - unknown: no usable date is recorded.
    """
    current = today or date.today()
    deadline = _as_date(_field_value(opportunity, "deadline"))
    open_date = _as_date(_field_value(opportunity, "open_date"))
    if deadline is not None:
        if deadline < current:
            return "closed"
        if open_date is not None and open_date > current:
            return "upcoming"
        if (deadline - current).days <= ACTIONABLE_CLOSING_SOON_DAYS:
            return "closing_soon"
        return "open"
    # Opening "today" is already open, so only a strictly future open_date
    # classifies as upcoming when there is no deadline.
    if open_date is not None and open_date > current:
        return "upcoming"
    if edition is not None:
        end = _as_date(_field_value(edition, "end_date"))
        if end is not None and end < current:
            return "held"
    hint = _field_value(opportunity, "status_hint")
    if hint in OPPORTUNITY_STATUS_HINTS:
        if hint == "open":
            return "open"
        return "upcoming"
    return "unknown"


def edition_lifecycle_status(edition: Any, *, today: date | None = None) -> str:
    """Edition lifecycle from real dates (opportunities are classified with
    opportunity_status separately so one closed track never closes the event)."""
    current = today or date.today()
    deadline_values = [
        _as_date(_field_value(edition, field)) for field in ACTIONABLE_DEADLINE_FIELDS
    ]
    future_deadlines = [d for d in deadline_values if d is not None and d >= current]
    if future_deadlines:
        nearest = min(future_deadlines)
        if (nearest - current).days <= ACTIONABLE_CLOSING_SOON_DAYS:
            return "closing_soon"
        return "open"
    start = _as_date(_field_value(edition, "start_date"))
    end = _as_date(_field_value(edition, "end_date"))
    if end is not None and end < current:
        return "held"
    if start is not None or end is not None:
        return "upcoming"
    return "unknown"


def value_reason_type_for_opportunity(opportunity_type: str | None) -> str | None:
    mapping = {
        "paper_submission": "paper_submission_available",
        "abstract_submission": "paper_submission_available",
        "poster": "poster_available",
        "student_paper": "official_student_track",
        "student_forum": "student_forum",
        "undergraduate_forum": "undergraduate_opportunity",
        "graduate_forum": "graduate_opportunity",
        "doctoral_consortium": "doctoral_consortium",
        "young_scholar_forum": "graduate_opportunity",
        "student_registration": "student_registration",
        "travel_grant": "travel_grant",
        "student_award": "student_award",
        "mentoring": "official_student_track",
        "workshop": "paper_submission_available",
        "tutorial": "paper_submission_available",
        "volunteer": "student_registration",
        "competition": "student_award",
        "summer_school": "student_registration",
    }
    return mapping.get((opportunity_type or "").strip())


def validate_audience(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value:
            continue
        if value not in AUDIENCE_VALUES:
            raise ValueError(f"未知参会人群: {value!r}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def validate_rejection_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    reason = reason.strip()
    if reason not in REJECTION_REASONS:
        raise ValueError(f"未知拒绝原因: {reason!r}")
    return reason


def validate_recognition(recognition: dict[str, Any] | None) -> dict[str, Any] | None:
    """external_classifications record contract for V1.1 recognition."""
    if not recognition:
        return None
    system = str(recognition.get("system") or "").upper()
    level = str(recognition.get("level") or "").upper()
    allowed_systems = {
        "CCF",
        "CORE",
        "CAST_IMPORTANT_CONFERENCE",
        "UNIVERSITY_ACADEMIC",
        "OFFICIAL_SOCIETY_CLASSIFICATION",
        "OTHER",
    }
    if system not in allowed_systems:
        raise ValueError(f"未知认可体系: {system!r}")
    if system in {"CCF", "CORE"} and level not in {"A", "B", "C"}:
        raise ValueError(f"{system} 等级必须为 A/B/C: {level!r}")
    return {**recognition, "system": system, "level": level if level else None}


def recognition_has_evidence(recognition: dict[str, Any] | None) -> bool:
    """V1.1 evidence rule: an external recognition must cite its official
    source URL (or embed the evidence text) before it is treated as recorded
    with evidence. Absence of evidence is a curation flag, not a deletion."""
    if not recognition:
        return False
    return bool(recognition.get("source_url") or recognition.get("evidence"))


def recognition_summary(
    recognitions: Iterable[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return normalized recognition records with display text."""
    if not recognitions:
        return []
    result: list[dict[str, Any]] = []
    for item in recognitions:
        normalized = validate_recognition(item)
        if not normalized:
            continue
        result.append(
            {
                "system": normalized["system"],
                "level": normalized.get("level"),
                "version_year": normalized.get("version_year"),
                "source_url": normalized.get("source_url"),
                "evidence": normalized.get("evidence"),
                "display": external_classification_display(normalized),
            }
        )
    return result


CANONICAL_ALIAS_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    (
        "The Web Conference",
        (
            "The Web Conference",
            "WWW",
            "International World Wide Web Conference",
            "国际万维网大会",
            "ACM Web Conference",
        ),
    ),
    (
        "NAACL",
        ("NAACL", "NAACL-HLT", "北美计算语言学协会年会"),
    ),
    (
        "ESEC/FSE",
        ("ESEC/FSE", "FSE", "ESEC-FSE", "软件工程基础国际研讨会"),
    ),
    (
        "IEEE S&P",
        ("IEEE S&P", "S&P", "Oakland", "IEEE 安全与隐私研讨会"),
    ),
    (
        "中国计算机大会",
        ("CNCC", "中国计算机大会", "CCF 中国计算机大会"),
    ),
    (
        "全国数据库学术会议",
        ("NDBC", "全国数据库学术会议", "CCF NDBC", "中国数据库学术会议"),
    ),
    (
        "中国金融学年会",
        ("中国金融学年会", "CFA", "China Finance Annual Conference"),
    ),
]


def canonical_name_hint(
    *,
    name: str | None = None,
    english_name: str | None = None,
    short_name: str | None = None,
    aliases: Iterable[str] | None = None,
) -> str | None:
    """Return a known canonical name for an alias group (never auto-merges)."""
    tokens = {
        str(token).strip().casefold()
        for token in [name, english_name, short_name, *(aliases or [])]
        if token and str(token).strip()
    }
    for canonical, group in CANONICAL_ALIAS_GROUPS:
        group_tokens = {str(token).casefold() for token in group}
        if tokens & group_tokens:
            return canonical
    return None
