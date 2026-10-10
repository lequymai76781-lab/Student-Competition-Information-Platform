from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.models import User


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def _current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    from app.core.config import get_settings
    from app.core.security import verify_token

    user_id = verify_token(token, get_settings().app_secret)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user if user is not None and user.is_active else None


def get_current_user_optional(
    user: User | None = Depends(_current_user),
) -> User | None:
    return user


def get_current_user(user: User | None = Depends(_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return user


def get_current_admin(user: User | None = Depends(_current_user)) -> User:
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
