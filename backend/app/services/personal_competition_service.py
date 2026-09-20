"""V0.9 fact-based personal competition center.

No scores / no model training: personalized views are produced by filtering and
explaining with facts (edition status, tags, verified university/college
relations, recognized directories, and the personalized deadline resolution).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    College,
    Competition,
    CompetitionEdition,
    CompetitionPolicyRecognition,
    CompetitionTag,
    Favorite,
    Major,
    Tag,
    University,
    UniversityCompetitionEditionRelation,
    User,
    UserCompetitionStatus,
)
from app.services.deadline_resolution_service import DeadlineResolutionService
from app.services.user_facing_data_policy import UserFacingDataPolicy


INTEREST_SYNONYMS: dict[str, list[str]] = {
    "AIGC": ["人工智能", "视觉设计", "新闻传播"],
    "人工智能": ["人工智能"],
    "大数据": ["人工智能", "商业分析"],
    "影视制作": ["传媒", "视觉设计"],
    "广告设计": ["视觉设计", "艺术设计"],
    "市场营销": ["商业分析"],
    "新闻传播": ["新闻传播"],
    "传媒": ["传媒"],
    "写作": ["写作演讲"],
    "演讲": ["写作演讲"],
    "社会调查": ["调研"],
    "调研": ["调研"],
    "英语": ["外语"],
    "外语": ["外语"],
    "电子信息": ["电子信息"],
    "机器人": ["机器人"],
    "自动化": ["电子信息", "机器人"],
    "嵌入式": ["电子信息"],
    "机械": ["机械制造"],
    "创新创业": ["创新创业"],
    "创业": ["创新创业"],
    "商业分析": ["商业分析"],
    "程序设计": ["程序设计"],
    "编程": ["程序设计"],
    "网络安全": ["程序设计"],
    "数学建模": ["数学建模"],
    "体育": ["体育"],
    "艺术设计": ["艺术设计", "视觉设计"],
    "设计": ["视觉设计", "艺术设计"],
    "医学": ["医学"],
    "商科": ["商科"],
    "职业发展": ["职业发展"],
    "写作演讲": ["写作演讲"],
    "视觉设计": ["视觉设计"],
    "团队协作": ["团队协作"],
}

MAJOR_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("新闻", "传播", "播音", "编导", "广告", "影视", "数字媒体"), ["新闻传播", "传媒", "写作演讲"]),
    (("计算机", "软件", "人工智能", "智能科学", "网络安全", "网络工程"), ["程序设计", "人工智能"]),
    (("数学", "统计"), ["数学建模", "人工智能"]),
    (("电子", "通信", "自动化", "电气", "信息工程", "集成电路"), ["电子信息", "机器人"]),
    (("机械", "车辆", "材料", "航空", "航天"), ["机械制造", "机器人"]),
    (("经济", "工商", "管理", "金融", "会计", "市场营销", "国际贸易"), ["商业分析", "创新创业"]),
    (("设计", "艺术", "美术"), ["视觉设计", "艺术设计", "传媒"]),
    (("外语", "英语", "翻译", "日语", "法语"), ["外语"]),
    (("医学", "临床", "药学", "护理"), ["医学"]),
    (("体育", "运动"), ["体育"]),
    (("法学", "心理", "社会", "公共管理", "教育"), ["调研", "写作演讲"]),
    (("创新", "创业"), ["创新创业"]),
]


class PersonalCompetitionService:
    def __init__(self) -> None:
        self.deadline_service = DeadlineResolutionService()
        self.policy = UserFacingDataPolicy

    # ------------------------------------------------------------------ #
    # Context loaders
    # ------------------------------------------------------------------ #
    def _load_catalog(self, db: Session) -> dict[str, Any]:
        competitions = list(
            db.execute(
                select(Competition).where(
                    Competition.is_demo.is_(False),
                    Competition.is_competition.is_(True),
                )
            ).scalars()
        )
        editions = list(db.execute(select(CompetitionEdition)).scalars())
        tags = {tag.id: tag for tag in db.execute(select(Tag)).scalars()}
        competition_tag_rows = list(db.execute(select(CompetitionTag)).scalars())
        tag_ids_by_competition: dict[int, list[int]] = {}
        for row in competition_tag_rows:
            tag_ids_by_competition.setdefault(row.competition_id, []).append(row.tag_id)
        return {
            "competitions": {item.id: item for item in competitions},
            "editions": editions,
            "tags": tags,
            "tag_ids_by_competition": tag_ids_by_competition,
        }

    def _user_tags(self, profile) -> set[str]:
        result: set[str] = set()
        major_name = profile.major_name or ""
        for keywords, tag_names in MAJOR_RULES:
            if any(keyword in major_name for keyword in keywords):
                result.update(tag_names)
        for interest in profile.interest_tags or []:
            result.update(INTEREST_SYNONYMS.get(interest, [interest]))
        return result

    def _competition_tags(
        self,
        competition_id: int,
        catalog: dict[str, Any],
    ) -> list[dict[str, str]]:
        tag_ids = catalog["tag_ids_by_competition"].get(competition_id, [])
        rows = []
        for tag_id in tag_ids:
            tag = catalog["tags"].get(tag_id)
            if tag:
                rows.append({"id": tag.id, "name": tag.name, "category": tag.category})
        return rows

    def _latest_edition(
        self,
        competition_id: int,
        catalog: dict[str, Any],
    ) -> CompetitionEdition | None:
        rows = [
            edition
            for edition in catalog["editions"]
            if edition.competition_id == competition_id and edition.year >= 2025
        ]
        return max(rows, key=lambda item: item.year, default=None)

    # ------------------------------------------------------------------ #
    # Personalized competition rows
    # ------------------------------------------------------------------ #
    def personalized_competitions(
        self,
        db: Session,
        user: User,
        *,
        only_ids: set[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        profile = user.profile
        if profile is None:
            return {}
        catalog = self._load_catalog(db)
        user_tags = self._user_tags(profile)
        relations = list(
            db.execute(
                select(UniversityCompetitionEditionRelation).where(
                    UniversityCompetitionEditionRelation.university_id == profile.university_id
                )
            ).scalars()
        ) if profile.university_id else []
        relations = [row for row in relations if self.policy.relation_allowed(row)]
        relation_by_edition: dict[int, list] = {}
        for relation in relations:
            relation_by_edition.setdefault(relation.competition_edition_id, []).append(relation)
        university_recognitions = {
            row.competition_id
            for row in db.execute(
                select(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.university_id == profile.university_id,
                    CompetitionPolicyRecognition.recognition_status == "recognized",
                    CompetitionPolicyRecognition.is_demo.is_(False),
                )
            ).scalars()
        } if profile.university_id else set()
        college_recognitions = {
            row.competition_id
            for row in db.execute(
                select(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.college_id == profile.college_id,
                    CompetitionPolicyRecognition.recognition_status == "recognized",
                    CompetitionPolicyRecognition.is_demo.is_(False),
                )
            ).scalars()
        } if profile.college_id else set()
        favorites = {
            row.competition_id
            for row in db.execute(
                select(Favorite).where(Favorite.user_id == user.id)
            ).scalars()
        }
        statuses = {
            row.competition_id: row.status
            for row in db.execute(
                select(UserCompetitionStatus).where(UserCompetitionStatus.user_id == user.id)
            ).scalars()
        }

        now = datetime.now(timezone.utc)
        rows: dict[int, dict[str, Any]] = {}
        for competition_id, competition in catalog["competitions"].items():
            if only_ids is not None and competition_id not in only_ids:
                continue
            edition = self._latest_edition(competition_id, catalog)
            edition_relations = (
                relation_by_edition.get(edition.id, []) if edition is not None else []
            )
            school_relations = [r for r in edition_relations if r.college_id is None]
            college_relations = [
                r for r in edition_relations
                if profile.college_id is not None and r.college_id == profile.college_id
            ]
            if not school_relations:
                # relations may target any edition of this competition
                school_relations = [
                    r for r in relations
                    if r.competition_edition_id in {
                        e.id for e in catalog["editions"] if e.competition_id == competition_id
                    } and r.college_id is None
                ]
            if not college_relations:
                college_relations = [
                    r for r in relations
                    if r.competition_edition_id in {
                        e.id for e in catalog["editions"] if e.competition_id == competition_id
                    } and profile.college_id is not None and r.college_id == profile.college_id
                ]

            tags = self._competition_tags(competition_id, catalog)
            tag_names = {item["name"] for item in tags}
            matched_tags = sorted(tag_names & user_tags)
            reasons: list[dict[str, str]] = []
            current_status = edition.current_status if edition else None
            effective_deadline: datetime | None = None
            effective_label: str | None = None
            deadline_resolution: dict[str, Any] | None = None
            if edition is not None:
                deadline, label, resolution = self.deadline_service.resolve_action(
                    edition,
                    university_id=profile.university_id,
                    college_id=profile.college_id,
                )
                effective_deadline = self._aware(deadline) if deadline else None
                effective_label = label
                deadline_resolution = self._resolution_dict(resolution)
                if current_status in self.policy.EDITION_OPEN_STATUSES:
                    if current_status == "submission_open":
                        reasons.append({"type": "current_registration", "text": "当前正在作品提交中"})
                    elif current_status in {"registration_upcoming", "upcoming"}:
                        reasons.append({"type": "upcoming", "text": "即将开始报名"})
                    else:
                        reasons.append({"type": "current_registration", "text": "当前正在报名"})
            if matched_tags:
                reasons.append({"type": "interest_related", "text": f"与你的方向相关：{'/'.join(matched_tags[:4])}"})
            elif profile.college_id is None and profile.university_id is None:
                reasons.append({"type": "profile_incomplete", "text": "完善学校/专业后可获得更准的筛选"})
            if school_relations:
                relation = sorted(
                    school_relations,
                    key=lambda r: self._aware(r.last_seen_at or r.observed_at),
                    reverse=True,
                )[0]
                reasons.append({"type": "school_notice", "text": "你的学校有该赛事通知"})
            if college_relations:
                reasons.append({"type": "college_notice", "text": "你的学院有该赛事通知"})
            if competition_id in university_recognitions:
                reasons.append({"type": "school_directory", "text": "你的学校竞赛目录中已收录"})
            if competition_id in college_recognitions:
                reasons.append({"type": "college_directory", "text": "你的学院竞赛目录中已收录"})
            if competition.competition_level:
                reasons.append({"type": "level", "text": f"{competition.competition_level}赛事"})
            if profile.preferred_team_type and competition.team_type:
                if competition.team_type == profile.preferred_team_type or "团队" in profile.preferred_team_type and "团队" in competition.team_type:
                    reasons.append({"type": "team_preference_match", "text": "参赛形式符合你的偏好"})

            relation_info = None
            if school_relations or college_relations:
                source = (college_relations or school_relations)[0]
                college = db.get(College, source.college_id) if source.college_id else None
                relation_info = {
                    "notice_title": source.notice_title,
                    "notice_url": source.internal_notice_url,
                    "notice_type": source.notice_type,
                    "college_name": college.name if college else None,
                    "published_at": source.published_at.isoformat() if source.published_at else None,
                }
            rows[competition_id] = {
                "competition_id": competition_id,
                "name": competition.name,
                "short_name": competition.short_name,
                "category": competition.category,
                "competition_level": competition.competition_level,
                "team_type": competition.team_type,
                "target_students": competition.target_students,
                "recommended_grade": competition.recommended_grade,
                "tags": tags,
                "current_status": current_status,
                "edition_year": edition.year if edition else None,
                "edition_name": edition.edition_name if edition else None,
                "official_url": competition.official_website,
                "effective_deadline": effective_deadline.isoformat() if effective_deadline else None,
                "effective_deadline_label": effective_label,
                "official_deadline": (
                    deadline_resolution or {}
                ).get("official_deadline"),
                "university_deadline": (
                    deadline_resolution or {}
                ).get("university_deadline"),
                "college_deadline": (deadline_resolution or {}).get("college_deadline"),
                "reasons": reasons,
                "relation": relation_info,
                "school_notice": bool(school_relations),
                "college_notice": bool(college_relations),
                "school_directory": competition_id in university_recognitions,
                "college_directory": competition_id in college_recognitions,
                "favorite": competition_id in favorites,
                "user_status": statuses.get(competition_id),
                "open": current_status in self.policy.EDITION_OPEN_STATUSES,
                "relevant_flag": bool(
                    any(
                        reason["type"]
                        in {
                            "interest_related",
                            "school_notice",
                            "college_notice",
                            "school_directory",
                            "college_directory",
                            "current_registration",
                            "upcoming",
                            "team_preference_match",
                        }
                        for reason in reasons
                    )
                    or competition_id in favorites
                    or competition_id in statuses
                ),
                "content_relevant": bool(
                    any(
                        reason["type"]
                        in {
                            "interest_related",
                            "school_notice",
                            "college_notice",
                            "school_directory",
                            "college_directory",
                            "team_preference_match",
                        }
                        for reason in reasons
                    )
                    or competition_id in favorites
                    or competition_id in statuses
                ),
                "_effective_dt": effective_deadline,
            }
        return rows

    # ------------------------------------------------------------------ #
    # Public overview
    # ------------------------------------------------------------------ #
    def overview(self, db: Session, user: User) -> dict[str, Any]:
        profile = user.profile
        if profile is None:
            return {"profile_complete": False, "message": "请先完成资料设置"}
        rows = self.personalized_competitions(db, user)
        now = datetime.now(timezone.utc)

        def deadline_key(item: dict[str, Any]) -> str:
            return item["effective_deadline"] or "9999-12-31T00:00:00+00:00"

        open_rows = [item for item in rows.values() if item["open"]]
        direction_rows = [
            item
            for item in rows.values()
            if any(reason["type"] == "interest_related" for reason in item["reasons"])
            and not (item["current_status"] in {"finished", "ended", "archived"})
        ]
        now_available = [
            item
            for item in open_rows
            if any(
                reason["type"] in {"interest_related", "school_notice", "college_notice", "school_directory", "college_directory"}
                for reason in item["reasons"]
            )
        ]
        now_available.sort(key=deadline_key)
        direction_rows.sort(key=deadline_key)
        relevant_for_deadlines = [
            item
            for item in rows.values()
            if item["content_relevant"]
        ]
        upcoming = [
            item
            for item in relevant_for_deadlines
            if item["_effective_dt"] is not None and item["_effective_dt"] >= now
        ]
        upcoming.sort(key=lambda item: item["_effective_dt"])
        school_notices = [
            item for item in rows.values() if item["school_notice"]
        ]
        college_notices = [
            item for item in rows.values() if item["college_notice"]
        ]
        school_directory = [
            item for item in rows.values() if item["school_directory"]
        ]
        college_directory = [
            item for item in rows.values() if item["college_directory"]
        ]
        favorites = [item for item in rows.values() if item["favorite"]]
        status_views = {
            status_name: [item for item in rows.values() if item["user_status"] == status_name]
            for status_name in ("interested", "planning", "registered", "participating", "finished", "abandoned")
        }

        def strip(item: dict[str, Any]) -> dict[str, Any]:
            return {key: value for key, value in item.items() if key != "_effective_dt"}

        return {
            "profile_complete": True,
            "profile": self.profile_context(db, user),
            "now_available": [strip(item) for item in now_available[:24]],
            "direction_related": [strip(item) for item in direction_rows[:24]],
            "school_notices": [strip(item) for item in school_notices[:24]],
            "college_notices": [strip(item) for item in college_notices[:24]],
            "school_directory": [strip(item) for item in school_directory[:24]],
            "college_directory": [strip(item) for item in college_directory[:24]],
            "upcoming_deadline": [strip(item) for item in upcoming[:24]],
            "favorites": [strip(item) for item in favorites],
            "status_views": {
                name: [strip(item) for item in items]
                for name, items in status_views.items()
            },
            "counts": {
                "now_available": len(now_available),
                "direction_related": len(direction_rows),
                "school_notices": len(school_notices),
                "college_notices": len(college_notices),
                "school_directory": len(school_directory),
                "college_directory": len(college_directory),
                "upcoming_deadline": len(upcoming),
                "favorites": len(favorites),
                "personalized_competitions": len(rows),
                "open_total": len(open_rows),
            },
        }

    def competition_context(self, db: Session, user: User, competition_id: int) -> dict[str, Any]:
        row = self.personalized_competitions(db, user, only_ids={competition_id}).get(competition_id)
        if row is None:
            return {"found": False}
        return {"found": True, "item": {key: value for key, value in row.items() if key != "_effective_dt"}}

    def profile_context(self, db: Session, user: User) -> dict[str, Any]:
        profile = user.profile
        if profile is None:
            return {"user_id": user.id, "email": user.email}
        university = db.get(University, profile.university_id) if profile.university_id else None
        college = db.get(College, profile.college_id) if profile.college_id else None
        major = db.get(Major, profile.major_id) if profile.major_id else None
        return {
            "user_id": user.id,
            "email": user.email,
            "university_id": profile.university_id,
            "university_name": university.name if university else profile.university_name,
            "college_id": profile.college_id,
            "college_name": college.name if college else profile.college_name,
            "major_id": profile.major_id,
            "major_name": major.name if major else profile.major_name,
            "grade": profile.grade,
            "graduation_year": profile.graduation_year,
            "interest_tags": profile.interest_tags or [],
            "skills": profile.skills or [],
            "preferred_team_type": profile.preferred_team_type,
            "weekly_available_hours": profile.weekly_available_hours,
            "accept_cross_major": profile.accept_cross_major,
            "accept_cross_university": profile.accept_cross_university,
        }

    def upcoming_events(self, db: Session, user: User) -> list[dict[str, Any]]:
        rows = self.personalized_competitions(db, user)
        now = datetime.now(timezone.utc)
        events = []
        for item in rows.values():
            if item["_effective_dt"] is None or item["_effective_dt"] < now:
                continue
            events.append(
                {
                    "competition_id": item["competition_id"],
                    "name": item["name"],
                    "deadline": item["effective_deadline"],
                    "deadline_label": item["effective_deadline_label"] or "报名截止",
                    "official_deadline": item["official_deadline"],
                    "university_deadline": item["university_deadline"],
                    "college_deadline": item["college_deadline"],
                    "reasons": [reason["text"] for reason in item["reasons"][:3]],
                }
            )
        events.sort(key=lambda item: item["deadline"])
        return events

    # ------------------------------------------------------------------ #
    def _resolution_dict(self, resolution) -> dict[str, Any] | None:
        if resolution is None:
            return None

        def iso(value) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "official_deadline": iso(resolution.official_deadline),
            "official_submission_deadline": iso(resolution.official_submission_deadline),
            "university_deadline": iso(resolution.university_deadline),
            "college_deadline": iso(resolution.college_deadline),
            "effective_deadline": iso(resolution.effective_deadline),
            "effective_deadline_type": resolution.effective_deadline_type,
            "notice_title": resolution.notice_title,
            "source_url": resolution.source_url,
        }

    def _aware(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
