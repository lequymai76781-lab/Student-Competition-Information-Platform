from app.models import CompetitionSource


class SourceCredibilityService:
    score_by_source_type: dict[str, int] = {
        "official": 100,
        "university": 100,
        "government": 100,
        "official_wechat": 95,
        "competition_platform": 75,
        "wechat": 60,
        "xiaohongshu": 40,
        "weibo": 40,
        "zhihu": 45,
        "bilibili": 45,
        "github": 50,
        "manual": 70,
        "other": 30,
    }
    official_types = {"official", "university", "government", "official_wechat"}
    discovery_only_types = {"wechat", "xiaohongshu", "weibo", "zhihu", "bilibili"}

    def score_source(self, source_type: str, is_official: bool = False) -> int:
        if is_official:
            return 100
        return self.score_by_source_type.get(source_type, self.score_by_source_type["other"])

    def verification_status(self, sources: list[CompetitionSource]) -> str:
        if not sources:
            return "暂无来源"
        if any(source.is_verified or source.is_official or source.source_type in self.official_types for source in sources):
            return "已核验"
        if all(source.source_type in self.discovery_only_types for source in sources):
            return "待官方核验"
        return "部分可信，待复核"

