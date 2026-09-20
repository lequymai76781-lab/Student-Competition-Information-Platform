from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import sqlite3.dbapi2 as sqlite_dbapi2

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.safety import PRODUCTION_SQLITE_PATH, assert_test_sqlite_target_is_safe

_SQLITE_CONNECT = sqlite3.connect


def _guarded_sqlite_connect(database, *args, **kwargs):
    assert_test_sqlite_target_is_safe(database)
    return _SQLITE_CONNECT(database, *args, **kwargs)


sqlite3.connect = _guarded_sqlite_connect
sqlite_dbapi2.connect = _guarded_sqlite_connect

from app.api.deps import get_db
from app.database.base import Base
from app.main import app
from app.models import (
    Competition,
    CompetitionEdition,
    CompetitionSource,
    Tag,
    University,
    UniversityCompetitionDiscoveryReport,
    UniversityCompetitionEditionRelation,
    UniversityCompetitionPolicy,
    UniversityPolicy,
)


_MISSING_OVERRIDE = object()


@contextmanager
def temporary_dependency_override(target_app, dependency, override):
    previous = target_app.dependency_overrides.get(dependency, _MISSING_OVERRIDE)
    target_app.dependency_overrides[dependency] = override
    try:
        yield
    finally:
        if previous is _MISSING_OVERRIDE:
            target_app.dependency_overrides.pop(dependency, None)
        else:
            target_app.dependency_overrides[dependency] = previous


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def test_session(test_engine) -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=test_engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = factory()
    seed_test_data(db)
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session(test_session: Session) -> Session:
    return test_session


@pytest.fixture()
def production_copy_session_factory(tmp_path: Path):
    copied_path = tmp_path / "production-copy.sqlite"
    shutil.copy2(PRODUCTION_SQLITE_PATH, copied_path)
    engine = create_engine(
        f"sqlite:///{copied_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    with temporary_dependency_override(app, get_db, override_get_db):
        with TestClient(app) as test_client:
            yield test_client


def seed_test_data(db: Session) -> None:
    tag = Tag(name="计算机", category="competition")
    university = University(name="测试大学", province="湖北", city="武汉")
    competition = Competition(
        name="测试计算机设计大赛",
        short_name="测试大赛",
        description="Python、AIGC、计算机应用方向测试比赛。",
        organizer="测试主办方",
        category="计算机",
        competition_level="国家级",
        team_type="团队赛",
        min_team_size=1,
        max_team_size=5,
        difficulty_level="中等",
        target_students="本科生",
        history_timeline=[{"year": 2020, "title": "赛事创办", "verification_status": "verified_official"}],
        participation_requirements=[{"label": "学生身份", "value": "全日制本科生", "verification_status": "verified_official"}],
        competition_process=[{"title": "报名", "verification_status": "verified_official"}],
        submission_requirements=[{"label": "作品", "value": "项目报告", "verification_status": "verified_official"}],
        award_settings=[{"label": "一等奖", "value": "按官方评审结果授予", "verification_status": "verified_official"}],
        detail_ready=True,
        recommended_grade="大二,大三",
        is_cross_major_supported=True,
        is_cross_university_supported=True,
        is_official_verified=True,
        is_demo=False,
        tags=[tag],
    )
    db.add_all([tag, university, competition])
    db.flush()
    edition = CompetitionEdition(
        competition_id=competition.id,
        year=2026,
        edition_name="2026测试计算机设计大赛",
        registration_deadline=datetime.now(timezone.utc) + timedelta(days=30),
        official_registration_deadline=datetime.now(timezone.utc) + timedelta(days=30),
        university_registration_deadline=datetime.now(timezone.utc) + timedelta(days=20),
        current_status="registration_open",
        is_verified=True,
    )
    source = CompetitionSource(
        competition_id=competition.id,
        source_type="official",
        source_name="测试官方来源",
        source_url="https://example.com/test",
        is_official=True,
        is_verified=True,
        credibility_score=100,
        is_demo=False,
    )
    policy = UniversityPolicy(
        university_id=university.id,
        policy_name="测试大学竞赛政策",
        policy_type="recommendation",
        year=2026,
        content="测试政策数据。",
        is_demo=False,
    )
    db.add_all([edition, source, policy])
    db.flush()
    db.add(
        UniversityCompetitionDiscoveryReport(
            university_id=university.id,
            batch_name="test-batch",
            status="completed",
            pages_searched=2,
            competition_leads=1,
            matched_competitions=1,
            new_competitions=1,
            new_editions=1,
            official_sources=1,
            university_notice_count=1,
            current_registration_count=1,
            edition_2026_count=1,
            last_crawled_at=datetime.now(timezone.utc),
            reason="测试发现报告。",
            channel_stats={"university_website": 1},
        )
    )
    db.add(
        UniversityCompetitionEditionRelation(
            university_id=university.id,
            competition_edition_id=edition.id,
            source_type="university_official_notice",
            source_platform="university_website",
            source_name="测试大学教务处",
            notice_type="registration_notice",
            notice_title="测试大学竞赛报名通知",
            internal_notice_url="https://example.edu.cn/notice",
            organizing_department="测试大学教务处",
            internal_registration_deadline=datetime.now(timezone.utc) + timedelta(days=20),
            official_registration_deadline=datetime.now(timezone.utc) + timedelta(days=30),
            observed_at=datetime.now(timezone.utc),
            last_verified_at=datetime.now(timezone.utc),
            verification_status="verified_official",
            is_verified=True,
            is_demo=False,
        )
    )
    db.add(
        UniversityCompetitionPolicy(
            university_id=university.id,
            competition_id=competition.id,
            policy_id=policy.id,
            year=2026,
            recognition_status="recognized",
            recognized_level="演示级别",
            usage_type="recommendation",
            notes="测试认可关系。",
            evidence_text="测试认可记录。",
            is_demo=False,
        )
    )
    db.commit()
