from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user_optional, get_db
from app.core.responses import ApiResponse, success_response
from app.core.ratelimit import rate_limit
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionDetail,
    CompetitionListItem,
    CompetitionRecognitionRead,
    CompetitionUpdate,
)
from app.services.competition_service import CompetitionService
from app.services.user_facing_data_policy import UserFacingDataPolicy
from app.services.audit_service import record_metric
from app.models import CompetitionEdition, CompetitionUpdateEvent
from app.models import User

router = APIRouter(tags=["competitions"])
service = CompetitionService()


@router.get("/competitions", response_model=ApiResponse[list[CompetitionListItem]])
def list_competitions(
    keyword: str | None = None,
    category: str | None = None,
    competition_level: str | None = None,
    grade: str | None = None,
    team_type: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    edition_status: str | None = None,
    tag: str | None = None,
    availability: str | None = Query(default=None, pattern="^(homepage|next_30_days|next_90_days)$"),
    policy_coverage_min: int | None = Query(default=None, ge=0),
    data_completeness_min: float | None = Query(default=None, ge=0, le=100),
    has_college_recognition: bool | None = None,
    cross_university: bool | None = None,
    competition_type: str | None = Query(default=None, pattern="^(series|competition|track)$"),
    source_scope: str | None = Query(
        default=None,
        pattern="^(official_current|university_notice|my_university_notice|my_college_notice|registration_open)$",
    ),
    university_id: int | None = None,
    college_id: int | None = None,
    deadline_before: datetime | None = None,
    year: int | None = None,
    sort: str = Query(default="deadline", pattern="^(deadline|latest|name)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("competitions_search", limit=180, window_seconds=60)),
) -> dict:
    if source_scope in {"my_university_notice", "my_college_notice"} and university_id is None:
        raise HTTPException(status_code=422, detail="请选择学校后查看本校通知")
    if source_scope == "my_college_notice" and college_id is None:
        raise HTTPException(status_code=422, detail="请选择学院后查看本院通知")
    data = service.list_competitions(
        db,
        keyword=keyword,
        category=category,
        competition_level=competition_level,
        grade=grade,
        team_type=team_type,
        status=status_filter,
        edition_status=edition_status,
        tag=tag,
        availability=availability,
        policy_coverage_min=policy_coverage_min,
        data_completeness_min=data_completeness_min,
        has_college_recognition=has_college_recognition,
        cross_university=cross_university,
        competition_type=competition_type,
        source_scope=source_scope,
        university_id=university_id,
        college_id=college_id,
        deadline_before=deadline_before,
        year=year,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return success_response(data, meta={"limit": limit, "offset": offset})


@router.get("/competitions/{competition_id}", response_model=ApiResponse[CompetitionDetail])
def get_competition(
    competition_id: int,
    university_id: int | None = None,
    college_id: int | None = None,
    edition_id: int | None = None,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
) -> dict:
    if viewer is not None:
        record_metric(db, "competition_view", viewer.id)
    return success_response(
        service.get_competition(
            db,
            competition_id,
            university_id=university_id,
            college_id=college_id,
            edition_id=edition_id,
        )
    )


@router.get("/competitions/{competition_id}/updates")
def list_competition_updates(competition_id: int, edition_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    competition = service.get_competition(db, competition_id)
    selected_id = edition_id if edition_id is not None else competition.current_edition_id
    rows = db.execute(
        select(CompetitionUpdateEvent)
        .join(CompetitionEdition, CompetitionEdition.id == CompetitionUpdateEvent.competition_edition_id)
        .where(CompetitionUpdateEvent.competition_id == competition_id,
               UserFacingDataPolicy.verified_clause(CompetitionEdition),
               CompetitionUpdateEvent.competition_edition_id == selected_id)
        .order_by(CompetitionUpdateEvent.changed_at.desc())
        .limit(6)
    ).scalars().all()
    return success_response(
        [
            {
                "id": row.id,
                "competition_edition_id": row.competition_edition_id,
                "event_type": row.event_type,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "source_url": row.source_url,
                "source_name": row.source_name,
                "changed_at": row.changed_at.isoformat() if row.changed_at else None,
                "notes": row.notes,
            }
            for row in rows
        ]
    )


@router.post(
    "/competitions",
    response_model=ApiResponse[CompetitionDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_competition(
    competition_in: CompetitionCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> dict:
    raise HTTPException(409, "赛事新增须通过 /admin/field-review 创建候选、核验来源并逐字段批准")


@router.put("/competitions/{competition_id}", response_model=ApiResponse[CompetitionDetail])
def update_competition(
    competition_id: int,
    competition_in: CompetitionUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> dict:
    raise HTTPException(409, "赛事修改须通过 /admin/field-review 创建候选、核验来源并逐字段批准")


@router.get(
    "/competition/{competition_id}/university-recognition",
    response_model=ApiResponse[list[CompetitionRecognitionRead]],
)
def list_competition_recognition(
    competition_id: int,
    university_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return success_response(service.list_recognition(db, competition_id, university_id))
