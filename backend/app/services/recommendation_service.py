from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Major, UniversityCompetitionPolicy
from app.repositories.competition_repository import CompetitionRepository
from app.schemas.recommendation import RecommendationRequest, RecommendationResult


class RuleBasedRecommendationService:
    weights = {
        "policy": 25,
        "major": 20,
        "skills": 15,
        "goal": 15,
        "grade": 10,
        "time": 10,
        "interest": 5,
    }

    major_hints: dict[str, list[str]] = {
        "新闻": ["新闻传播", "广告设计", "影视制作", "AIGC", "市场营销"],
        "传播": ["新闻传播", "广告设计", "影视制作", "AIGC"],
        "播音": ["新闻传播", "影视制作", "语言文学", "AIGC"],
        "计算机": ["计算机", "人工智能", "大数据", "AIGC"],
        "软件": ["计算机", "人工智能", "大数据"],
        "数学": ["数学建模", "大数据", "人工智能"],
        "电子": ["电子信息", "机械工程", "科技创新"],
        "外语": ["外语", "语言文学"],
        "体育": ["体育", "电子竞技", "社会实践"],
        "设计": ["艺术设计", "广告设计", "AIGC"],
        "市场": ["市场营销", "商业分析", "创新创业"],
    }

    goal_hints: dict[str, list[str]] = {
        "保研": ["recommendation", "comprehensive_evaluation"],
        "综测": ["comprehensive_evaluation"],
        "奖学金": ["scholarship", "competition_reward"],
        "升学": ["recommendation", "comprehensive_evaluation"],
        "就业": ["innovation_credit", "competition_reward"],
        "创新创业": ["innovation_credit", "competition_reward"],
    }

    difficulty_hours: dict[str, int] = {
        "入门": 2,
        "中等": 5,
        "较高": 8,
        "高": 10,
    }

    def __init__(self) -> None:
        self.repository = CompetitionRepository()

    def recommend(self, db: Session, request: RecommendationRequest) -> list[RecommendationResult]:
        competitions = self.repository.list_competitions(db, limit=200)
        policy_rows = self._load_policy_rows(db, request.university_id)
        policy_by_competition: dict[int, list[UniversityCompetitionPolicy]] = {}
        for row in policy_rows:
            policy_by_competition.setdefault(row.competition_id, []).append(row)

        major_name = request.major_name or self._load_major_name(db, request.major_id)
        results = [
            self._score_competition(competition, request, major_name, policy_by_competition.get(competition.id, []))
            for competition in competitions
        ]
        return sorted(results, key=lambda item: item.score, reverse=True)[: request.limit]

    def _load_major_name(self, db: Session, major_id: int | None) -> str | None:
        if major_id is None:
            return None
        major = db.get(Major, major_id)
        return major.name if major else None

    def _load_policy_rows(self, db: Session, university_id: int | None) -> list[UniversityCompetitionPolicy]:
        if university_id is None:
            return []
        stmt = select(UniversityCompetitionPolicy).where(UniversityCompetitionPolicy.university_id == university_id)
        return list(db.execute(stmt).scalars().all())

    def _score_competition(
        self,
        competition: Competition,
        request: RecommendationRequest,
        major_name: str | None,
        policy_rows: list[UniversityCompetitionPolicy],
    ) -> RecommendationResult:
        score = 0.0
        matched: list[str] = []
        unmatched: list[str] = []
        search_text = self._competition_text(competition)

        policy_score = self._score_policy(policy_rows)
        score += policy_score
        if policy_score:
            matched.append("当前学校政策数据库存在相关认可记录")
        elif request.university_id:
            unmatched.append("暂未找到当前学校对该比赛的明确认可记录")

        if self._matches_major(competition, major_name):
            score += self.weights["major"]
            matched.append(f"与{major_name}方向相关" if major_name else "与专业方向相关")
        elif major_name:
            unmatched.append("专业匹配度暂不明确")

        skill_hits = self._count_hits(request.skills, search_text)
        if skill_hits:
            skill_score = min(self.weights["skills"], skill_hits * 5)
            score += skill_score
            matched.append(f"与技能匹配：{self._join_hits(request.skills, search_text)}")
        elif request.skills:
            unmatched.append("未发现明显技能匹配")

        goal_score = self._score_goal(request.goal, policy_rows, competition)
        score += goal_score
        if goal_score:
            matched.append(f"与目标匹配：{request.goal}")
        elif request.goal:
            unmatched.append("目标收益需要进一步核验")

        if request.grade and competition.recommended_grade and request.grade in competition.recommended_grade:
            score += self.weights["grade"]
            matched.append(f"当前{request.grade}适合参加")
        elif request.grade:
            unmatched.append("年级适配信息不充分")

        if self._matches_time(request.weekly_available_hours, competition.difficulty_level):
            score += self.weights["time"]
            matched.append("可投入时间与比赛难度匹配")
        elif request.weekly_available_hours is not None:
            unmatched.append("可投入时间可能偏紧")

        interest_hits = self._count_hits(request.interest_tags, search_text)
        if interest_hits:
            score += min(self.weights["interest"], interest_hits * 2.5)
            matched.append(f"兴趣方向匹配：{self._join_hits(request.interest_tags, search_text)}")
        elif request.interest_tags:
            unmatched.append("兴趣标签匹配较弱")

        if request.preferred_team_type and competition.team_type and request.preferred_team_type != competition.team_type:
            unmatched.append(f"偏好的参赛形式是{request.preferred_team_type}，该比赛为{competition.team_type}")

        if not request.accept_cross_major and competition.is_cross_major_supported:
            unmatched.append("该比赛可能涉及跨专业协作")
        if not request.accept_cross_university and competition.is_cross_university_supported:
            unmatched.append("该比赛可能支持跨校组队，需要按学校要求核验")

        score = min(100.0, round(score, 1))
        reason = "；".join(matched[:5]) if matched else "当前为基础规则推荐，建议补充学校、专业、技能和目标信息后再评估。"
        return RecommendationResult(
            competition_id=competition.id,
            competition_name=competition.name,
            score=score,
            matched_factors=matched,
            unmatched_factors=unmatched,
            recommendation_reason=reason,
        )

    def _score_policy(self, rows: list[UniversityCompetitionPolicy]) -> float:
        if any(row.recognition_status == "recognized" for row in rows):
            return self.weights["policy"]
        if any(row.recognition_status == "uncertain" for row in rows):
            return self.weights["policy"] * 0.5
        return 0.0

    def _score_goal(
        self,
        goal: str | None,
        rows: list[UniversityCompetitionPolicy],
        competition: Competition,
    ) -> float:
        if not goal:
            return 0.0
        goal_text = goal.lower()
        usage_types = {row.usage_type for row in rows if row.recognition_status in {"recognized", "uncertain"}}
        for goal_key, usage_hints in self.goal_hints.items():
            if goal_key in goal_text and usage_types.intersection(usage_hints):
                return self.weights["goal"]
        if "就业" in goal_text and competition.category in {"商业分析", "计算机", "人工智能", "创新创业", "市场营销"}:
            return self.weights["goal"] * 0.7
        return 0.0

    def _matches_major(self, competition: Competition, major_name: str | None) -> bool:
        if not major_name:
            return False
        category = competition.category or ""
        text = self._competition_text(competition)
        if major_name in text:
            return True
        for major_hint, category_hints in self.major_hints.items():
            if major_hint in major_name and category in category_hints:
                return True
        return False

    def _matches_time(self, weekly_available_hours: int | None, difficulty_level: str | None) -> bool:
        if weekly_available_hours is None:
            return False
        required = self.difficulty_hours.get(difficulty_level or "", 5)
        return weekly_available_hours >= required

    def _competition_text(self, competition: Competition) -> str:
        parts = [
            competition.name,
            competition.short_name or "",
            competition.description or "",
            competition.category or "",
            competition.target_students or "",
            " ".join(tag.name for tag in competition.tags),
        ]
        return " ".join(parts).lower()

    def _count_hits(self, values: list[str], text: str) -> int:
        return sum(1 for value in values if value and value.lower() in text)

    def _join_hits(self, values: list[str], text: str) -> str:
        return "、".join(value for value in values if value and value.lower() in text)

