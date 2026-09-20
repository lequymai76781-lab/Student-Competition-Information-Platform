from app.crawler.base import BaseCrawler, CrawlerResult


class CompetitionCrawler(BaseCrawler):
    name = "competition_crawler"

    def crawl(self, keyword: str | None = None) -> list[CrawlerResult]:
        return []

