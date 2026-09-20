from app.crawler.base import CrawlerResult


class DataNormalizationService:
    """Converts crawler output into normalized domain payloads.

    V0.1 keeps this intentionally conservative and returns candidate fields for manual review.
    """

    def normalize_competition_candidate(self, result: CrawlerResult) -> dict:
        return {
            "name": result.title,
            "source_url": result.url,
            "source_type": result.source_type,
            "source_platform": result.source_platform,
            "raw_content": result.raw_content,
            "metadata": result.metadata,
            "verification_status": "待官方核验" if result.source_type in {"wechat", "xiaohongshu", "weibo"} else "待复核",
        }

