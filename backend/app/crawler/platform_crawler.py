from app.crawler.base import BaseCrawler, CrawlerResult


class CompetitionPlatformCrawler(BaseCrawler):
    name = "competition_platform_crawler"

    def crawl(self, keyword: str | None = None) -> list[CrawlerResult]:
        return []
