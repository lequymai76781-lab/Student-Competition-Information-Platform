from app.crawler.base import BaseCrawler, CrawlerResult


class UniversityCrawler(BaseCrawler):
    name = "university_crawler"

    def crawl(self, keyword: str | None = None) -> list[CrawlerResult]:
        return []

