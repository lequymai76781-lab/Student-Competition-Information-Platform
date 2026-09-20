import json

from sqlalchemy import select

from app.core.security import hash_password
from app.models import College, Major, University, User, UserProfile
from app.services.personal_competition_service import PersonalCompetitionService


def _make_user(db, email: str, university: str, college: str, major: str, grade: str, interests: list[str]) -> User:
    uni = db.execute(select(University).where(University.name == university)).scalar_one()
    college_row = db.execute(
        select(College).where(College.university_id == uni.id, College.name == college)
    ).scalar_one_or_none()
    if college_row is None:
        college_row = College(university_id=uni.id, name=college, is_verified=True, is_demo=False)
        db.add(college_row)
        db.flush()
    major_row = db.execute(select(Major).where(Major.name == major)).scalar_one_or_none()
    if major_row is None:
        major_row = Major(name=major)
        db.add(major_row)
        db.flush()
    user = User(email=email, username=email.split("@")[0], hashed_password=hash_password("test123456"))
    db.add(user)
    db.flush()
    profile = UserProfile(
        user_id=user.id,
        university_id=uni.id,
        university_name=uni.name,
        college_id=college_row.id,
        college_name=college_row.name,
        major_id=major_row.id,
        major_name=major_row.name,
        grade=grade,
        interest_tags=interests,
    )
    db.add(profile)
    db.flush()
    return user


def test_personal_overview_differentiates_users(production_copy_session_factory):
    service = PersonalCompetitionService()
    with production_copy_session_factory() as db:
        user_a = _make_user(
            db,
            "v09test-a@example.com",
            "武汉体育学院",
            "新闻传播学院",
            "播音主持",
            "大二",
            ["新闻传播", "AIGC", "影视制作"],
        )
        user_b = _make_user(
            db,
            "v09test-b@example.com",
            "西南交通大学",
            "经济管理学院",
            "工商管理",
            "大二",
            ["商业分析", "创新创业"],
        )
        overview_a = service.overview(db, user_a)
        overview_b = service.overview(db, user_b)
        names_a = {item["name"] for item in overview_a["now_available"]}
        names_b = {item["name"] for item in overview_b["now_available"]}
        assert overview_a["profile"]["university_name"] == "武汉体育学院"
        assert overview_b["profile"]["university_name"] == "西南交通大学"
        assert overview_b["counts"]["school_notices"] > 0
        assert names_a != names_b or overview_a["counts"] != overview_b["counts"]
        for item in overview_a["now_available"]:
            assert isinstance(item["reasons"], list)
            assert "competition_id" in item


def test_personalized_deadline_uses_user_context(production_copy_session_factory):
    service = PersonalCompetitionService()
    with production_copy_session_factory() as db:
        user = _make_user(
            db,
            "v09test-c@example.com",
            "西南交通大学",
            "经济管理学院",
            "工商管理",
            "大二",
            ["商业分析"],
        )
        rows = service.personalized_competitions(db, user)
        with_notice = [
            row for row in rows.values()
            if any(reason["type"] == "school_notice" for reason in row["reasons"])
        ]
        assert with_notice, "西南交通大学 should expose verified school notices"
        assert all(row["school_notice"] for row in with_notice)
