from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionSource,
    Major,
    Tag,
    University,
    UniversityCompetitionPolicy,
    UniversityPolicy,
)
from app.services.source_credibility_service import SourceCredibilityService

TAGS = [
    "科技创新",
    "人工智能",
    "计算机",
    "大数据",
    "数学建模",
    "电子信息",
    "机械工程",
    "商业分析",
    "创新创业",
    "市场营销",
    "新闻传播",
    "广告设计",
    "影视制作",
    "AIGC",
    "艺术设计",
    "语言文学",
    "外语",
    "体育",
    "电子竞技",
    "社会实践",
    "公益",
    "综合类",
    "其他",
]

UNIVERSITIES = [
    {"name": "武汉体育学院", "short_name": "武体", "province": "湖北", "city": "武汉", "university_type": "体育类", "official_website": "https://www.whsu.edu.cn"},
    {"name": "武汉大学", "short_name": "武大", "province": "湖北", "city": "武汉", "university_type": "综合类", "is_985": True, "is_211": True, "is_double_first_class": True, "official_website": "https://www.whu.edu.cn"},
    {"name": "华中科技大学", "short_name": "华科", "province": "湖北", "city": "武汉", "university_type": "理工类", "is_985": True, "is_211": True, "is_double_first_class": True, "official_website": "https://www.hust.edu.cn"},
    {"name": "浙江大学", "short_name": "浙大", "province": "浙江", "city": "杭州", "university_type": "综合类", "is_985": True, "is_211": True, "is_double_first_class": True, "official_website": "https://www.zju.edu.cn"},
    {"name": "北京师范大学", "short_name": "北师大", "province": "北京", "city": "北京", "university_type": "师范类", "is_985": True, "is_211": True, "is_double_first_class": True, "official_website": "https://www.bnu.edu.cn"},
]

COLLEGES = {
    "武汉体育学院": ["新闻传播学院", "体育教育学院", "艺术学院"],
    "武汉大学": ["计算机学院", "新闻与传播学院"],
    "华中科技大学": ["人工智能与自动化学院", "管理学院"],
    "浙江大学": ["计算机科学与技术学院", "传媒与国际文化学院"],
    "北京师范大学": ["新闻传播学院", "文学院"],
}

MAJORS = [
    {"name": "播音与主持艺术", "discipline_category": "艺术学", "major_category": "戏剧与影视学类"},
    {"name": "新闻学", "discipline_category": "文学", "major_category": "新闻传播学类"},
    {"name": "计算机科学与技术", "discipline_category": "工学", "major_category": "计算机类"},
    {"name": "人工智能", "discipline_category": "工学", "major_category": "电子信息类"},
    {"name": "市场营销", "discipline_category": "管理学", "major_category": "工商管理类"},
    {"name": "数据科学与大数据技术", "discipline_category": "工学", "major_category": "计算机类"},
]

COMPETITIONS = [
    ("挑战杯", "挑战杯", "科技创新", ["科技创新", "社会实践", "综合类"], "国家级", "团队赛", "较高", "大一,大二,大三,大四", 3, 10, 44),
    ("中国国际大学生创新大赛", "创新大赛", "创新创业", ["创新创业", "商业分析", "综合类"], "国家级", "团队赛", "高", "大一,大二,大三,大四,研究生", 3, 15, 60),
    ("中国大学生计算机设计大赛", "计算机设计大赛", "计算机", ["计算机", "AIGC", "新闻传播", "艺术设计"], "国家级", "团队赛", "中等", "大一,大二,大三,大四", 1, 5, 67),
    ("蓝桥杯全国软件和信息技术专业人才大赛", "蓝桥杯", "计算机", ["计算机", "人工智能", "大数据"], "国家级", "个人赛", "中等", "大一,大二,大三,大四", 1, 1, 24),
    ("全国大学生数学建模竞赛", "数模国赛", "数学建模", ["数学建模", "大数据", "科技创新"], "国家级", "团队赛", "较高", "大二,大三,大四", 3, 3, 18),
    ("全国大学生广告艺术大赛", "大广赛", "广告设计", ["广告设计", "新闻传播", "艺术设计", "AIGC"], "国家级", "团队赛", "中等", "大一,大二,大三,大四", 1, 5, 36),
    ("中国大学生服务外包创新创业大赛", "服创赛", "创新创业", ["创新创业", "计算机", "商业分析"], "国家级", "团队赛", "较高", "大二,大三,大四,研究生", 3, 5, 52),
    ("全国大学生电子设计竞赛", "电赛", "电子信息", ["电子信息", "科技创新", "机械工程"], "国家级", "团队赛", "高", "大二,大三,大四", 3, 3, 12),
    ("全国大学生英语竞赛", "NECCS", "外语", ["外语", "语言文学"], "国家级", "个人赛", "入门", "大一,大二,大三,大四", 1, 1, 80),
    ("大学生市场调查与分析大赛", "市调大赛", "商业分析", ["商业分析", "市场营销", "大数据"], "国家级", "团队赛", "中等", "大一,大二,大三,大四", 3, 5, 41),
    ("全国大学生电子商务三创赛", "三创赛", "创新创业", ["创新创业", "市场营销", "商业分析"], "国家级", "团队赛", "中等", "大一,大二,大三,大四", 3, 5, 72),
    ("中国高校计算机大赛", "C4", "计算机", ["计算机", "人工智能", "大数据"], "国家级", "团队赛", "较高", "大二,大三,大四,研究生", 1, 5, 33),
    ("全国大学生机械创新设计大赛", "机械创新设计大赛", "机械工程", ["机械工程", "科技创新"], "国家级", "团队赛", "较高", "大二,大三,大四", 3, 5, 95),
    ("全国大学生生命科学竞赛", "生命科学竞赛", "科技创新", ["科技创新", "综合类"], "国家级", "团队赛", "较高", "大二,大三,大四", 2, 5, 88),
    ("全国大学生体育产业创新创业大赛", "体育双创赛", "体育", ["体育", "创新创业", "市场营销"], "省部级", "团队赛", "中等", "大一,大二,大三,大四", 2, 6, 58),
]

POLICY_TYPES = [
    "recommendation",
    "comprehensive_evaluation",
    "scholarship",
    "competition_reward",
    "innovation_credit",
]


def utc_days_from_now(days: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def get_or_create(db: Session, model: type, defaults: dict[str, Any] | None = None, **lookup: Any):
    instance = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if instance:
        return instance
    payload = {**lookup, **(defaults or {})}
    instance = model(**payload)
    db.add(instance)
    db.flush()
    return instance


def seed_tags(db: Session) -> dict[str, Tag]:
    return {name: get_or_create(db, Tag, name=name, defaults={"category": "competition"}) for name in TAGS}


def seed_universities(db: Session) -> dict[str, University]:
    universities: dict[str, University] = {}
    for item in UNIVERSITIES:
        payload = {
            "short_name": item.get("short_name"),
            "province": item.get("province"),
            "city": item.get("city"),
            "university_type": item.get("university_type"),
            "is_985": item.get("is_985", False),
            "is_211": item.get("is_211", False),
            "is_double_first_class": item.get("is_double_first_class", False),
            "official_website": item.get("official_website"),
        }
        university = get_or_create(db, University, name=item["name"], defaults=payload)
        universities[university.name] = university
        for college_name in COLLEGES[university.name]:
            get_or_create(db, College, university_id=university.id, name=college_name)
    return universities


def seed_majors(db: Session) -> None:
    for item in MAJORS:
        get_or_create(
            db,
            Major,
            name=item["name"],
            defaults={
                "discipline_category": item["discipline_category"],
                "major_category": item["major_category"],
            },
        )


def seed_competitions(db: Session, tags: dict[str, Tag]) -> list[Competition]:
    credibility = SourceCredibilityService()
    competitions: list[Competition] = []
    for index, item in enumerate(COMPETITIONS, start=1):
        name, short_name, category, tag_names, level, team_type, difficulty, grades, min_size, max_size, deadline_days = item
        competition = get_or_create(
            db,
            Competition,
            name=name,
            defaults={
                "short_name": short_name,
                "description": f"{name}的演示条目，用于开发阶段展示筛选、详情、推荐与政策关联能力。demo_data=true。",
                "organizer": "演示主办单位",
                "category": category,
                "competition_level": level,
                "team_type": team_type,
                "min_team_size": min_size,
                "max_team_size": max_size,
                "difficulty_level": difficulty,
                "target_students": "普通高等学校本科生、研究生；具体资格以官方通知为准。",
                "recommended_grade": grades,
                "status": "active",
                "is_cross_major_supported": True,
                "is_cross_university_supported": team_type == "团队赛",
                "is_demo": True,
            },
        )
        competition.tags = [tags[tag_name] for tag_name in tag_names if tag_name in tags]
        db.flush()

        edition = get_or_create(
            db,
            CompetitionEdition,
            competition_id=competition.id,
            year=2026,
            defaults={
                "edition_name": f"2026{name}",
                "registration_start": utc_days_from_now(-10 + index),
                "registration_deadline": utc_days_from_now(deadline_days),
                "competition_start": utc_days_from_now(deadline_days + 20),
                "competition_end": utc_days_from_now(deadline_days + 35),
                "announcement_date": utc_days_from_now(-15 + index),
                "official_url": None,
                "current_status": "registration_open" if deadline_days > 20 else "closing_soon",
            },
        )
        official_score = credibility.score_source("official", is_official=True)
        get_or_create(
            db,
            CompetitionSource,
            competition_id=competition.id,
            competition_edition_id=edition.id,
            source_url=f"https://example.com/demo/competitions/{index}",
            defaults={
                "source_type": "official",
                "source_name": "演示官方来源",
                "source_platform": "demo",
                "published_at": utc_days_from_now(-20 + index),
                "crawled_at": datetime.now(timezone.utc),
                "is_official": True,
                "is_verified": True,
                "credibility_score": official_score,
                "raw_title": f"{name}演示来源",
                "raw_content": "演示数据，非真实通知原文。demo_data=true。",
                "content_hash": f"demo-{index}",
                "metadata_json": {"demo_data": True},
                "is_demo": True,
            },
        )
        competitions.append(competition)
    return competitions


def seed_policies(db: Session, universities: dict[str, University]) -> list[UniversityPolicy]:
    policies: list[UniversityPolicy] = []
    counter = 1
    for university in universities.values():
        for policy_type in POLICY_TYPES[:2]:
            policy = get_or_create(
                db,
                UniversityPolicy,
                university_id=university.id,
                policy_name=f"{university.name} {2026} {policy_type} 演示政策",
                defaults={
                    "policy_type": policy_type,
                    "year": 2026,
                    "source_url": f"https://example.com/demo/policies/{counter}",
                    "official_file_url": None,
                    "published_at": utc_days_from_now(-120 + counter),
                    "effective_date": utc_days_from_now(-90 + counter),
                    "content": "演示政策文本，仅用于开发联调；不代表该校真实竞赛认可或加分规则。demo_data=true。",
                    "is_verified": False,
                    "is_demo": True,
                },
            )
            policies.append(policy)
            counter += 1
    return policies


def seed_recognition_links(
    db: Session,
    universities: dict[str, University],
    competitions: list[Competition],
    policies: list[UniversityPolicy],
) -> None:
    policy_cycle = policies or []
    usage_cycle = ["recommendation", "comprehensive_evaluation", "scholarship", "innovation_credit"]
    for index in range(20):
        university = list(universities.values())[index % len(universities)]
        competition = competitions[index % len(competitions)]
        policy = policy_cycle[index % len(policy_cycle)] if policy_cycle else None
        usage_type = usage_cycle[index % len(usage_cycle)]
        exists = db.execute(
            select(UniversityCompetitionPolicy).filter_by(
                university_id=university.id,
                competition_id=competition.id,
                policy_id=policy.id if policy else None,
                year=2026,
                usage_type=usage_type,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        db.add(
            UniversityCompetitionPolicy(
                university_id=university.id,
                competition_id=competition.id,
                policy_id=policy.id if policy else None,
                year=2026,
                recognition_status="recognized" if index % 4 != 0 else "uncertain",
                recognized_level="演示级别",
                recognized_award=None,
                score=None,
                usage_type=usage_type,
                notes="演示数据：仅用于展示学校×比赛×政策关系，不代表真实认可结论。",
                evidence_text="demo_data=true；请以后以学校官方政策文件核验为准。",
                is_demo=True,
            )
        )


def main() -> None:
    db = SessionLocal()
    try:
        tags = seed_tags(db)
        universities = seed_universities(db)
        seed_majors(db)
        competitions = seed_competitions(db, tags)
        policies = seed_policies(db, universities)
        seed_recognition_links(db, universities, competitions, policies)
        db.commit()
        print("Demo data seeded successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
