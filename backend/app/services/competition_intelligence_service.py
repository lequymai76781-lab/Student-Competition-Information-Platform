from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionPolicyRecognition,
    CompetitionSource,
    CompetitionStatistics,
    Tag,
    University,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.source_authority_service import authority_level_for


TAG_TAXONOMY = {
    "学科领域": ["工科", "理科", "商科", "文科", "艺术设计", "传媒", "体育", "医学", "外语", "综合"],
    "能力方向": [
        "创新创业",
        "数学建模",
        "程序设计",
        "人工智能",
        "机器人",
        "电子信息",
        "机械制造",
        "商业分析",
        "调研",
        "写作演讲",
        "视觉设计",
        "新闻传播",
        "职业发展",
        "团队协作",
    ],
}

TAG_KEYWORDS = {
    "工科": ["工程", "机械", "电子", "智能制造", "结构", "化工", "机器人", "汽车", "计算机", "软件"],
    "理科": ["数学", "物理", "化学", "生命科学", "统计", "力学"],
    "商科": ["商业", "电子商务", "市场", "物流", "企业", "创业", "财会", "金融"],
    "文科": ["文学", "哲学", "社会", "法治", "历史", "外语", "英语", "新闻"],
    "艺术设计": ["艺术", "设计", "广告", "舞蹈", "视觉", "动漫", "创意"],
    "传媒": ["新闻", "传播", "广告", "短视频", "摄影", "主持", "写作"],
    "体育": ["体育", "运动"],
    "医学": ["医学", "医药", "护理", "健康", "生命科学"],
    "外语": ["英语", "外语", "翻译", "演讲", "阅读", "写作", "国才杯"],
    "创新创业": ["创新创业", "创业", "挑战杯", "创客", "三创", "互联网+"],
    "数学建模": ["数学建模", "建模"],
    "程序设计": ["程序设计", "软件", "编程", "ACM", "ICPC", "蓝桥"],
    "人工智能": ["人工智能", "AI", "智能", "大数据"],
    "机器人": ["机器人", "Robo", "机甲"],
    "电子信息": ["电子", "信息技术", "通信", "网络技术", "ICT", "嵌入式"],
    "机械制造": ["机械", "制造", "成图", "结构设计", "工程训练"],
    "商业分析": ["商业", "市场", "数据分析", "电子商务", "物流"],
    "调研": ["调查", "调研", "社会实践", "市场"],
    "写作演讲": ["写作", "演讲", "辩论", "翻译", "阅读", "讲解"],
    "视觉设计": ["视觉", "设计", "广告", "摄影", "短视频", "动漫"],
    "新闻传播": ["新闻", "传播", "广告", "主持", "短视频"],
    "职业发展": ["职业规划", "就业", "生涯"],
}

SERIES_DEFINITIONS = [
    {
        "contains": "外研社全国大学生英语系列赛",
        "canonical": "外研社·国才杯“理解当代中国”全国大学生外语能力大赛",
        "children": [
            "外研社·国才杯英语演讲赛项",
            "外研社·国才杯英语写作赛项",
            "外研社·国才杯英语阅读赛项",
            "外研社·国才杯英语辩论赛项",
            "外研社·国才杯国际传播综合能力赛项",
            "外研社·国才杯笔译赛项",
            "外研社·国才杯短视频赛项",
            "外研社·国才杯“四新”专项赛",
        ],
    },
    {
        "contains": "全国大学生机器人大赛",
        "canonical": "全国大学生机器人大赛",
        "children": ["RoboMaster机甲大师赛", "ABU RoboCon全国大学生机器人大赛"],
    },
    {
        "contains": "中国高校计算机大赛",
        "canonical": "中国高校计算机大赛",
        "children": [
            "中国高校计算机大赛团体程序设计天梯赛",
            "中国高校计算机大赛人工智能创意赛",
            "中国高校计算机大赛网络技术挑战赛",
            "中国高校计算机大赛大数据挑战赛",
            "中国高校计算机大赛移动应用创新赛",
        ],
    },
    {
        "contains": "全国高校商业精英挑战赛",
        "canonical": "全国高校商业精英挑战赛",
        "children": [
            "全国高校商业精英挑战赛品牌策划竞赛",
            "全国高校商业精英挑战赛会展专业创新创业实践竞赛",
            "全国高校商业精英挑战赛国际贸易竞赛",
            "全国高校商业精英挑战赛创新创业竞赛",
            "全国高校商业精英挑战赛文旅与会展创新创业实践竞赛",
        ],
    },
]


class CompetitionIntelligenceService:
    def __init__(self) -> None:
        self.normalizer = CompetitionNormalizationService()

    def build_hierarchy(self, db: Session) -> dict[str, int]:
        result = {"series": 0, "tracks_created": 0, "tracks_linked": 0}
        competitions = list(db.execute(select(Competition)).scalars().all())
        for definition in SERIES_DEFINITIONS:
            parent = self._find_exact(competitions, definition["canonical"]) or self._find_contains(
                competitions,
                definition["contains"],
            )
            if parent is None:
                parent = Competition(
                    name=definition["canonical"],
                    category="综合",
                    competition_type="series",
                    status="active",
                    is_demo=False,
                )
                db.add(parent)
                db.flush()
                competitions.append(parent)
            elif parent.name != definition["canonical"]:
                previous_name = parent.name
                parent.name = definition["canonical"]
                self.normalizer.ensure_alias(db, parent, previous_name, source="hierarchy_normalization", is_verified=True)
            parent.competition_type = "series"
            result["series"] += 1

            for child_name in definition["children"]:
                child = self._find_exact(competitions, child_name)
                if child is None:
                    child = Competition(
                        name=child_name,
                        category=parent.category,
                        competition_type="track",
                        parent_competition_id=parent.id,
                        status="active",
                        is_demo=False,
                    )
                    db.add(child)
                    db.flush()
                    competitions.append(child)
                    result["tracks_created"] += 1
                else:
                    child.parent_competition_id = parent.id
                    child.competition_type = "track"
                    result["tracks_linked"] += 1
        db.commit()
        return result

    def apply_tags(self, db: Session) -> dict[str, int]:
        tags: dict[str, Tag] = {}
        for category, names in TAG_TAXONOMY.items():
            for name in names:
                tag = db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
                if tag is None:
                    tag = Tag(name=name, category=category)
                    db.add(tag)
                    db.flush()
                tags[name] = tag

        tagged = 0
        assignments = 0
        competitions = list(
            db.execute(
                select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
            ).scalars().all()
        )
        taxonomy_names = {name for names in TAG_TAXONOMY.values() for name in names}
        for competition in competitions:
            competition.tags = [tag for tag in competition.tags if tag.name not in taxonomy_names]
            usable_description = (
                competition.description
                if competition.description and not competition.description.startswith("由已验证高校政策")
                else ""
            )
            usable_category = competition.category if competition.category != "学科竞赛" else ""
            haystack = " ".join(
                value or ""
                for value in (competition.name, usable_category, usable_description, competition.organizer)
            )
            names = {
                tag_name
                for tag_name, keywords in TAG_KEYWORDS.items()
                if any(keyword.lower() in haystack.lower() for keyword in keywords)
            }
            if competition.team_type == "团队赛" or (competition.max_team_size or 0) > 1:
                names.add("团队协作")
            if not names:
                names.add("综合")
            existing = {tag.name for tag in competition.tags}
            for name in sorted(names - existing):
                competition.tags.append(tags[name])
                assignments += 1
            if competition.tags:
                tagged += 1
        db.commit()
        return {"tags": len(tags), "tagged_competitions": tagged, "assignments": assignments}

    def refresh_all(self, db: Session, *, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        competitions = list(
            db.execute(
                select(Competition).where(Competition.is_demo.is_(False), Competition.is_competition.is_(True))
            ).scalars().all()
        )
        for competition in competitions:
            self._refresh_edition_statuses(competition, now)
            recognitions = list(
                db.execute(
                    select(CompetitionPolicyRecognition, University)
                    .join(University, University.id == CompetitionPolicyRecognition.university_id)
                    .where(
                        CompetitionPolicyRecognition.competition_id == competition.id,
                        CompetitionPolicyRecognition.is_demo.is_(False),
                    )
                ).all()
            )
            policy_count = len({recognition.policy_document_id for recognition, _ in recognitions})
            distinct_universities = len({university.id for _, university in recognitions})
            university_985_count = len(
                {university.id for recognition, university in recognitions if university.is_985 and recognition.college_id is None}
            )
            college_985_count = len(
                {
                    (university.id, recognition.college_id)
                    for recognition, university in recognitions
                    if university.is_985 and recognition.college_id is not None
                }
            )
            latest_year = max((recognition.year for recognition, _ in recognitions if recognition.year), default=None)
            official_sources = [
                source
                for source in competition.sources
                if source.is_verified
                and not source.is_demo
                and (source.authority_level or authority_level_for(source.source_type))
                in {"S", "A"}
            ]
            all_sources = [source for source in competition.sources if not source.is_demo]
            university_sources = [
                source
                for source in all_sources
                if source.source_type in {"university_official", "university_official_notice", "college_official_notice"}
            ]
            notice_relations = list(
                db.execute(
                    select(UniversityCompetitionEditionRelation)
                    .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
                    .where(
                        CompetitionEdition.competition_id == competition.id,
                        UniversityCompetitionEditionRelation.is_demo.is_(False),
                    )
                ).scalars()
            )
            verified_sources = [source for source in official_sources if source.is_verified]
            verified_editions = [edition for edition in competition.editions if edition.is_verified]
            competition.is_official_verified = bool(verified_sources or verified_editions)
            completeness = self._completeness(competition, official_sources, verified_editions)
            competition.data_completeness_score = completeness

            policy_score = min(35.0, college_985_count * 9 + university_985_count * 12 + distinct_universities * 5 + policy_count * 2)
            official_level_score = self._official_level_score(competition.competition_level)
            registration_score = self._registration_score(competition.editions)
            discipline_score = min(10.0, len(competition.tags) * 2.5)
            activity_score = self._activity_score(verified_editions, now.year)
            completeness_score = round(completeness * 0.05, 2)
            breakdown = {
                "policy_coverage": round(policy_score, 2),
                "official_level": round(official_level_score, 2),
                "registration_status": round(registration_score, 2),
                "discipline_breadth": round(discipline_score, 2),
                "recent_activity": round(activity_score, 2),
                "data_completeness": completeness_score,
            }
            priority_score = round(sum(breakdown.values()), 2)
            competition.crawl_priority = priority_score
            statistics = db.execute(
                select(CompetitionStatistics).where(CompetitionStatistics.competition_id == competition.id)
            ).scalar_one_or_none()
            payload = {
                "university_985_recognition_count": university_985_count,
                "college_985_recognition_count": college_985_count,
                "policy_reference_count": policy_count,
                "latest_policy_year": latest_year,
                "official_source_count": len(official_sources),
                "source_count": len(all_sources),
                "university_source_count": len(university_sources),
                "university_count": len({relation.university_id for relation in notice_relations}),
                "college_count": len({relation.college_id for relation in notice_relations if relation.college_id is not None}),
                "last_seen_at": max(
                    (
                        self._aware(item)
                        for item in [
                            *(source.retrieved_at for source in all_sources),
                            *(source.crawled_at for source in all_sources),
                            *(relation.observed_at for relation in notice_relations),
                        ]
                        if item is not None
                    ),
                    default=None,
                ),
                "verification_count": sum(
                    1 for recognition, _ in recognitions if not recognition.needs_manual_review and recognition.confidence >= 0.9
                ),
                "priority_score": priority_score,
                "score_breakdown": breakdown,
            }
            if statistics is None:
                db.add(CompetitionStatistics(competition_id=competition.id, **payload))
            else:
                for key, value in payload.items():
                    setattr(statistics, key, value)
        db.commit()
        return {"competitions_scored": len(competitions)}

    def _refresh_edition_statuses(self, competition: Competition, now: datetime) -> None:
        for edition in competition.editions:
            start = self._aware(edition.registration_start)
            deadline = self._aware(edition.registration_deadline)
            competition_start = self._aware(edition.competition_start)
            competition_end = self._aware(edition.competition_end)
            submission_deadline = self._aware(edition.submission_deadline)
            if start and now < start:
                edition.current_status = "registration_upcoming"
            elif deadline and now <= deadline:
                edition.current_status = "registration_open"
            elif submission_deadline and now <= submission_deadline:
                edition.current_status = "submission_open"
            elif competition_start and now < competition_start:
                edition.current_status = "registration_closed"
            elif competition_end and now <= competition_end:
                edition.current_status = "ongoing"
            elif competition_end and now > competition_end:
                edition.current_status = "finished"
            elif deadline and now > deadline:
                edition.current_status = "registration_closed"

    def _completeness(
        self,
        competition: Competition,
        official_sources: list[CompetitionSource],
        verified_editions: list[CompetitionEdition],
    ) -> float:
        score = 8.0
        score += 10 if competition.description else 0
        score += 10 if competition.organizer else 0
        score += 10 if competition.official_website else 0
        score += 8 if competition.category and competition.category != "学科竞赛" else 0
        score += 6 if competition.team_type else 0
        score += 4 if competition.recommended_grade else 0
        score += 5 if competition.aliases else 0
        score += 12 if competition.tags else 0
        score += 10 if competition.sources else 0
        score += 7 if official_sources else 0
        score += 10 if verified_editions else 0
        return min(100.0, score)

    def _official_level_score(self, level: str | None) -> float:
        if not level:
            return 0.0
        if "国际" in level:
            return 20.0
        if "国家" in level or "全国" in level:
            return 16.0
        if "省" in level or "部" in level:
            return 10.0
        if "校" in level:
            return 4.0
        return 0.0

    def _registration_score(self, editions: list[CompetitionEdition]) -> float:
        statuses = {edition.current_status for edition in editions if edition.is_verified}
        if "registration_open" in statuses:
            return 20.0
        if "upcoming" in statuses:
            return 12.0
        if "ongoing" in statuses:
            return 6.0
        return 0.0

    def _activity_score(self, editions: list[CompetitionEdition], current_year: int) -> float:
        if any(edition.year == current_year for edition in editions):
            return 10.0
        if any(edition.year == current_year - 1 for edition in editions):
            return 6.0
        return 0.0

    def _find_contains(self, competitions: list[Competition], token: str) -> Competition | None:
        normalized_token = self.normalizer._normalize_text(token)
        return next(
            (
                competition
                for competition in competitions
                if normalized_token in self.normalizer._normalize_text(competition.name)
            ),
            None,
        )

    def _find_exact(self, competitions: list[Competition], name: str) -> Competition | None:
        normalized = self.normalizer._normalize_text(name)
        return next(
            (competition for competition in competitions if self.normalizer._normalize_text(competition.name) == normalized),
            None,
        )

    def _aware(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
