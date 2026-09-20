"""V0.9 five test-user scenarios.

Creates (idempotent) test users with profiles and prints each user's
personalized competition result for the acceptance report.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import College, Major, University, User, UserProfile
from app.services.personal_competition_service import PersonalCompetitionService


SCENARIOS = [
    {
        "case": "CASE1",
        "email": "case1@test.local",
        "username": "case1-whsu",
        "password": "test123456",
        "university": "武汉体育学院",
        "college": "新闻传播学院",
        "major": "播音主持",
        "grade": "大二",
        "interest_tags": ["新闻传播", "AIGC", "影视制作"],
    },
    {
        "case": "CASE2",
        "email": "case2@test.local",
        "username": "case2-whu",
        "password": "test123456",
        "university": "武汉大学",
        "college": "计算机学院",
        "major": "计算机科学",
        "grade": "大三",
        "interest_tags": ["人工智能", "程序设计", "大数据"],
    },
    {
        "case": "CASE3",
        "email": "case3@test.local",
        "username": "case3-bjtu",
        "password": "test123456",
        "university": "北京交通大学",
        "college": "电子信息学院",
        "major": "电子信息工程",
        "grade": "大二",
        "interest_tags": ["电子信息", "人工智能"],
    },
    {
        "case": "CASE4",
        "email": "case4@test.local",
        "username": "case4-nuaa",
        "password": "test123456",
        "university": "南京航空航天大学",
        "college": "机电学院",
        "major": "机械工程",
        "grade": "大三",
        "interest_tags": ["机械制造", "机器人"],
    },
    {
        "case": "CASE5",
        "email": "case5@test.local",
        "username": "case5-swjtu",
        "password": "test123456",
        "university": "西南交通大学",
        "college": "经济管理学院",
        "major": "工商管理",
        "grade": "大二",
        "interest_tags": ["商业分析", "创新创业"],
    },
    {
        "case": "CASE6",
        "email": "case6@test.local",
        "username": "case6-bupt",
        "password": "test123456",
        "university": "北京邮电大学",
        "college": "信息与通信工程学院",
        "major": "通信工程",
        "grade": "大二",
        "interest_tags": ["电子信息", "程序设计", "网络安全"],
    },
    {
        "case": "CASE7",
        "email": "case7@test.local",
        "username": "case7-fudan",
        "password": "test123456",
        "university": "复旦大学",
        "college": "新闻学院",
        "major": "新闻学",
        "grade": "大三",
        "interest_tags": ["新闻传播", "影视制作", "写作"],
    },
    {
        "case": "CASE8",
        "email": "case8@test.local",
        "username": "case8-hust",
        "password": "test123456",
        "university": "华中科技大学",
        "college": "机械科学与工程学院",
        "major": "机械设计制造及其自动化",
        "grade": "大三",
        "interest_tags": ["机械制造", "机器人", "人工智能"],
    },
    {
        "case": "CASE9",
        "email": "case9@test.local",
        "username": "case9-scu",
        "password": "test123456",
        "university": "四川大学",
        "college": "文学与新闻学院",
        "major": "广告学",
        "grade": "大二",
        "interest_tags": ["广告设计", "艺术设计", "AIGC"],
    },
    {
        "case": "CASE10",
        "email": "case10@test.local",
        "username": "case10-ruc",
        "password": "test123456",
        "university": "中国人民大学",
        "college": "经济学院",
        "major": "金融学",
        "grade": "大四",
        "interest_tags": ["商业分析", "创新创业", "职业发展"],
    },
]

ADMIN = {
    "email": "admin@test.local",
    "username": "v1-admin",
    "password": "test123456",
}


def _resolve(db, scenario: dict) -> None:
    university = db.execute(
        select(University).where(University.name == scenario["university"])
    ).scalar_one_or_none()
    assert university is not None, f"missing university {scenario['university']}"
    college = db.execute(
        select(College).where(
            College.university_id == university.id,
            College.name == scenario["college"],
        )
    ).scalar_one_or_none()
    if college is None:
        college = College(university_id=university.id, name=scenario["college"], is_verified=True, is_demo=False)
        db.add(college)
        db.flush()
    major = db.execute(
        select(Major).where(Major.name == scenario["major"])
    ).scalar_one_or_none()
    if major is None:
        major = Major(name=scenario["major"])
        db.add(major)
        db.flush()

    user = db.execute(
        select(User).where(User.email == scenario["email"])
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=scenario["email"],
            username=scenario["username"],
            hashed_password=hash_password(scenario["password"]),
        )
        db.add(user)
        db.flush()
    if user.profile is None:
        db.add(UserProfile(user_id=user.id))
        db.flush()
    profile = db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    ).scalar_one()
    profile.university_id = university.id
    profile.university_name = university.name
    profile.college_id = college.id
    profile.college_name = college.name
    profile.major_id = major.id
    profile.major_name = major.name
    profile.grade = scenario["grade"]
    profile.graduation_year = {
        "大一": 2030,
        "大二": 2029,
        "大三": 2028,
        "大四": 2027,
    }.get(scenario["grade"])
    profile.interest_tags = scenario["interest_tags"]
    db.commit()


def main() -> None:
    service = PersonalCompetitionService()
    output = []
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.email == ADMIN["email"])).scalar_one_or_none()
        if admin is None:
            admin = User(
                email=ADMIN["email"],
                username=ADMIN["username"],
                hashed_password=hash_password(ADMIN["password"]),
                is_admin=True,
            )
            db.add(admin)
            db.flush()
        else:
            admin.is_admin = True
        db.commit()
        for scenario in SCENARIOS:
            _resolve(db, scenario)
        for scenario in SCENARIOS:
            user = db.execute(
                select(User).where(User.email == scenario["email"])
            ).scalar_one()
            overview = service.overview(db, user)
            counts = overview["counts"]
            now_available = overview["now_available"][:5]
            names = [item["name"] for item in now_available]
            deadline_items = [
                {
                    "name": item["name"],
                    "deadline": item["effective_deadline"],
                    "label": item["effective_deadline_label"],
                }
                for item in overview["upcoming_deadline"][:5]
            ]
            output.append(
                {
                    "case": scenario["case"],
                    "profile": overview["profile"],
                    "counts": counts,
                    "top5_now_available": names,
                    "school_notice_names": [item["name"] for item in overview["school_notices"][:5]],
                    "personalized_deadline_items": deadline_items,
                }
            )
            print(f"== {scenario['case']} {scenario['university']}/{scenario['college']}/{scenario['major']} ==")
            print("  profile:", json.dumps(overview["profile"], ensure_ascii=False))
            print("  counts:", json.dumps(counts, ensure_ascii=False))
            print("  now_available top5:", json.dumps(names, ensure_ascii=False))
            print("  school_notices:", json.dumps([item["name"] for item in overview["school_notices"][:5]], ensure_ascii=False))
            print("  upcoming deadline top5:", json.dumps(deadline_items, ensure_ascii=False)[:500])
    out_path = ROOT / "data" / "reports" / "v09_test_users_scenarios.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
