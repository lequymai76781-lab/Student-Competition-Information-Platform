from app.crawler.base import BaseCrawler, CrawlerResult


class SocialMediaCrawler(BaseCrawler):
    name = "social_media_crawler"

    def crawl(self, keyword: str | None = None) -> list[CrawlerResult]:
        return []

