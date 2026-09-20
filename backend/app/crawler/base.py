from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CrawlerResult(BaseModel):
    title: str
    url: str
    source_type: str
    source_platform: str | None = None
    published_at: datetime | None = None
    raw_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    crawler_name: str
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BaseCrawler(ABC):
    name: str = "base"

    @abstractmethod
    def crawl(self, keyword: str | None = None) -> list[CrawlerResult]:
        raise NotImplementedError

