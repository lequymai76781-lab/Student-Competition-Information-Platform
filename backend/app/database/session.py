from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.safety import assert_test_database_is_safe
from app.database.review_guard import ReviewGuardedSession

settings = get_settings()
assert_test_database_is_safe(settings.database_url, environment=settings.environment)

engine_options: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool if settings.database_url.endswith(":memory:") else None,
    }
    engine_options = {key: value for key, value in engine_options.items() if value is not None}

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=ReviewGuardedSession)


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
