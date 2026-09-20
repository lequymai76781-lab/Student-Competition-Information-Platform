"""Academic Conference V1 basic read-only API (no frontend consumers yet)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.models import (
    ConferenceDiscoveryCandidate,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceSeries,
    ConferenceSource,
    SchoolConference,
)
from app.schemas.conference import (
    ConferenceDisciplineMappingRead,
    ConferenceDiscoveryCandidateRead,
    ConferenceEditionRead,
    ConferenceOpportunityRead,
    ConferenceSeriesDetail,
    ConferenceSeriesListItem,
    ConferenceSourceRead,
    DisciplineRead,
    SchoolConferenceRead,
)
from app.services.conference_authority_service import (
    AUTHORITY_STATUSES,
    AUDIENCE_VALUES,
    CONFERENCE_DISCIPLINES,
    CONFERENCE_SOURCE_TYPE_AUTHORITY,
    DISCOVERY_CANDIDATE_STATUSES,
    DISCIPLINE_RELATIONSHIP_TYPES,
    INDEXING_CLAIM_STATUSES,
    OPPORTUNITY_AUDIENCES,
    OPPORTUNITY_TYPES,
    PUBLICATION_STATUSES,
    REJECTION_REASONS,
    RISK_FLAG_VOCABULARY,
    STUDENT_VALUE_TAGS,
)
from app.services.conference_service import ConferenceService

router = APIRouter(tags=["conferences"])
service = ConferenceService()


@router.get("/conferences/disciplines", response_model=ApiResponse[list[DisciplineRead]])
def list_conference_disciplines() -> dict:
    return success_response(service.list_disciplines())


@router.get("/conferences/summary")
def conference_summary(db: Session = Depends(get_db)) -> dict:
    counts = {
        "series_total": db.scalar(select(func.count()).select_from(ConferenceSeries)) or 0,
        "editions_total": db.scalar(select(func.count()).select_from(ConferenceEdition)) or 0,
        "sources_total": db.scalar(select(func.count()).select_from(ConferenceSource)) or 0,
        "candidates_total": db.scalar(
            select(func.count()).select_from(ConferenceDiscoveryCandidate)
        )
        or 0,
        "school_relations_total": db.scalar(
            select(func.count()).select_from(SchoolConference)
        )
        or 0,
        "opportunities_total": db.scalar(
            select(func.count()).select_from(ConferenceOpportunity)
        )
        or 0,
    }
    counts["actionable"] = service.actionable_summary(db)
    counts["disciplines"] = service.list_disciplines()
    counts["authority_levels"] = list(CONFERENCE_SOURCE_TYPE_AUTHORITY.keys())
    return success_response(counts)


@router.get("/conferences/series", response_model=ApiResponse[list[ConferenceSeriesListItem]])
def list_conference_series(
    keyword: str | None = None,
    discipline: str | None = None,
    primary_discipline: str | None = None,
    is_international: bool | None = None,
    authority_status: str | None = Query(default=None, pattern="^(verified_official|authority_confirmed|pending_verification|unverified)$"),
    verification_status: str | None = Query(default=None, pattern="^(verified_official|authority_confirmed|pending_verification|unverified)$"),
    organization: str | None = None,
    year: int | None = Query(default=None, ge=1900, le=2100),
    country: str | None = None,
    student_value_tag: str | None = Query(default=None, pattern="^(" + "|".join(STUDENT_VALUE_TAGS) + ")$"),
    recognition_level: str | None = None,
    has_official_source: bool | None = None,
    has_submission: bool | None = None,
    has_student_track: bool | None = None,
    has_poster: bool | None = None,
    has_registration: bool | None = None,
    actionable: bool | None = None,
    has_opportunity: bool | None = None,
    opportunity_type: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_TYPES) + ")$"
    ),
    opportunity_audience: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_AUDIENCES) + ")$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_series(
        db,
        keyword=keyword,
        discipline=discipline,
        primary_discipline=primary_discipline,
        is_international=is_international,
        authority_status=authority_status,
        verification_status=verification_status,
        organization=organization,
        year=year,
        country=country,
        student_value_tag=student_value_tag,
        recognition_level=recognition_level,
        has_official_source=has_official_source,
        has_submission=has_submission,
        has_student_track=has_student_track,
        has_poster=has_poster,
        has_registration=has_registration,
        actionable=actionable,
        has_opportunity=has_opportunity,
        opportunity_type=opportunity_type,
        opportunity_audience=opportunity_audience,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/series/{series_id}", response_model=ApiResponse[ConferenceSeriesDetail])
def get_conference_series(series_id: int, db: Session = Depends(get_db)) -> dict:
    return success_response(service.get_series(db, series_id))


@router.get("/conferences/editions", response_model=ApiResponse[list[ConferenceEditionRead]])
def list_conference_editions(
    series_id: int | None = None,
    year: int | None = None,
    discipline: str | None = None,
    primary_discipline: str | None = None,
    organization: str | None = None,
    country: str | None = None,
    verification_status: str | None = Query(default=None, pattern="^(verified_official|authority_confirmed|pending_verification|unverified)$"),
    student_value_tag: str | None = Query(default=None, pattern="^(" + "|".join(STUDENT_VALUE_TAGS) + ")$"),
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
    opportunity_type: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_TYPES) + ")$"
    ),
    opportunity_audience: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_AUDIENCES) + ")$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_editions(
        db,
        series_id=series_id,
        year=year,
        discipline=discipline,
        primary_discipline=primary_discipline,
        organization=organization,
        country=country,
        verification_status=verification_status,
        student_value_tag=student_value_tag,
        recognition_level=recognition_level,
        has_cfp=has_cfp,
        has_paper_deadline=has_paper_deadline,
        has_registration_deadline=has_registration_deadline,
        has_dates=has_dates,
        has_location=has_location,
        has_submission=has_submission,
        has_student_track=has_student_track,
        has_poster=has_poster,
        has_registration=has_registration,
        actionable=actionable,
        has_opportunity=has_opportunity,
        opportunity_type=opportunity_type,
        opportunity_audience=opportunity_audience,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/editions/{edition_id}", response_model=ApiResponse[ConferenceEditionRead])
def get_conference_edition(edition_id: int, db: Session = Depends(get_db)) -> dict:
    return success_response(service.get_edition(db, edition_id))


@router.get(
    "/conferences/opportunities",
    response_model=ApiResponse[list[ConferenceOpportunityRead]],
)
def list_conference_opportunities(
    edition_id: int | None = None,
    series_id: int | None = None,
    opportunity_type: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_TYPES) + ")$"
    ),
    audience: str | None = Query(
        default=None, pattern="^(" + "|".join(OPPORTUNITY_AUDIENCES) + ")$"
    ),
    status: str | None = Query(
        default=None,
        pattern="^(open|closing_soon|upcoming|closed|held|unknown)$",
    ),
    year: int | None = Query(default=None, ge=1900, le=2100),
    discipline: str | None = None,
    primary_discipline: str | None = None,
    actionable: bool | None = None,
    verified_only: bool | None = None,
    verified_after: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_opportunities(
        db,
        edition_id=edition_id,
        series_id=series_id,
        opportunity_type=opportunity_type,
        audience=audience,
        status=status,
        year=year,
        discipline=discipline,
        primary_discipline=primary_discipline,
        actionable=actionable,
        verified_only=verified_only,
        verified_after=verified_after,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get(
    "/conferences/discipline-mappings",
    response_model=ApiResponse[list[ConferenceDisciplineMappingRead]],
)
def list_discipline_mappings(
    major_alias: str | None = None,
    discipline: str | None = None,
    relationship_type: str | None = Query(
        default=None, pattern="^(" + "|".join(DISCIPLINE_RELATIONSHIP_TYPES) + ")$"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_discipline_mappings(
        db,
        major_alias=major_alias,
        discipline=discipline,
        relationship_type=relationship_type,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/actionable")
def list_actionable_conferences(
    year: int | None = Query(default=None, ge=2025, le=2030),
    include_history: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_actionable(
        db,
        year=year,
        include_history=include_history,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/actionable-summary")
def conference_actionable_summary(
    year: int | None = Query(default=None, ge=2025, le=2030),
    db: Session = Depends(get_db),
) -> dict:
    return success_response(service.actionable_summary(db, year=year))


@router.get("/conferences/sources", response_model=ApiResponse[list[ConferenceSourceRead]])
def list_conference_sources(
    series_id: int | None = None,
    edition_id: int | None = None,
    authority_level: str | None = Query(default=None, pattern="^(S|A|B|C)$"),
    source_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_sources(
        db,
        series_id=series_id,
        edition_id=edition_id,
        authority_level=authority_level,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/school-relations", response_model=ApiResponse[list[SchoolConferenceRead]])
def list_conference_school_relations(
    school_id: int | None = None,
    series_id: int | None = None,
    edition_id: int | None = None,
    relation_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_school_relations(
        db,
        school_id=school_id,
        series_id=series_id,
        edition_id=edition_id,
        relation_type=relation_type,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get(
    "/conferences/candidates",
    response_model=ApiResponse[list[ConferenceDiscoveryCandidateRead]],
)
def list_conference_candidates(
    status: str | None = Query(
        default=None,
        pattern="^(pending|reviewing|matched|verified|duplicate|rejected|non_conference)$",
    ),
    keyword: str | None = None,
    entity_type: str | None = Query(
        default=None,
        pattern="^(conference_series|conference_edition|conference_opportunity)$",
    ),
    rejection_reason: str | None = Query(
        default=None,
        pattern="^(" + "|".join(REJECTION_REASONS) + ")$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    data, total = service.list_candidates(
        db,
        status=status,
        keyword=keyword,
        rejection_reason=rejection_reason,
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset, "total": total})


@router.get("/conferences/vocabulary")
def conference_vocabulary() -> dict:
    return success_response(
        {
            "disciplines": {
                code: CONFERENCE_DISCIPLINES[code] for code in CONFERENCE_DISCIPLINES
            },
            "authority_statuses": list(AUTHORITY_STATUSES),
            "source_type_authority": dict(CONFERENCE_SOURCE_TYPE_AUTHORITY),
            "candidate_statuses": list(DISCOVERY_CANDIDATE_STATUSES),
            "indexing_claim_statuses": list(INDEXING_CLAIM_STATUSES),
            "publication_statuses": list(PUBLICATION_STATUSES),
            "risk_flag_vocabulary": list(RISK_FLAG_VOCABULARY),
            "student_value_tags": list(STUDENT_VALUE_TAGS),
            "audience": list(AUDIENCE_VALUES),
            "opportunity_types": list(OPPORTUNITY_TYPES),
            "opportunity_audiences": list(OPPORTUNITY_AUDIENCES),
            "discipline_relationship_types": list(DISCIPLINE_RELATIONSHIP_TYPES),
            "rejection_reasons": list(REJECTION_REASONS),
            "recognition_systems": ["CCF", "CORE", "CAST_IMPORTANT_CONFERENCE", "UNIVERSITY_ACADEMIC", "OFFICIAL_SOCIETY_CLASSIFICATION", "OTHER"],
        }
    )
