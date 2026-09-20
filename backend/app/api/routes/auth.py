from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.responses import ApiResponse, success_response
from app.core.ratelimit import rate_limit
from app.core.security import create_token, hash_password, verify_password
from app.models import User, UserProfile
from app.schemas.user import LoginIn, RegisterIn
from app.services.personal_competition_service import PersonalCompetitionService
from app.services.audit_service import record_metric

router = APIRouter(tags=["v0.9-auth"])
personal_service = PersonalCompetitionService()
logger = logging.getLogger("v1.auth")


@router.post("/auth/register", response_model=ApiResponse)
def register(
    payload: RegisterIn,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("register", limit=5, window_seconds=60)),
) -> dict:
    settings = get_settings()
    if settings.beta_invite_code:
        if not payload.invite_code or payload.invite_code.strip() != settings.beta_invite_code:
            raise HTTPException(status_code=403, detail="Beta阶段需要邀请码才能注册")
    email = payload.email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")
    user = User(
        email=email,
        username=payload.username.strip(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    record_metric(db, "registered", user.id)
    db.commit()
    token = create_token(user.id, get_settings().app_secret)
    return success_response(
        {
            "token": token,
            "user": personal_service.profile_context(db, user),
            "onboarding_complete": False,
        },
        message="registered",
    )


@router.post("/auth/login", response_model=ApiResponse)
def login(
    payload: LoginIn,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("login", limit=10, window_seconds=60)),
) -> dict:
    user = db.execute(
        select(User).where(User.email == payload.email.strip().lower())
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        logger.warning("auth_failure email=%s", payload.email.strip().lower())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    token = create_token(user.id, get_settings().app_secret)
    return success_response(
        {
            "token": token,
            "user": personal_service.profile_context(db, user),
            "onboarding_complete": user.profile is not None and user.profile.university_id is not None,
        },
        message="ok",
    )


@router.get("/auth/me", response_model=ApiResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return success_response(
        {
            "user": personal_service.profile_context(db, user),
            "onboarding_complete": user.profile is not None and user.profile.university_id is not None,
        }
    )
