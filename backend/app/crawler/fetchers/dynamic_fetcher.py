from app.crawler.base import CrawlError


class DynamicFetcher:
    def fetch(self, url: str) -> CrawlError:
        return CrawlError(
            url=url,
            message="Dynamic JS rendering is not enabled in V0.2 local crawler. Mark for manual review or run a browser-capable worker.",
            retryable=False,
        )
