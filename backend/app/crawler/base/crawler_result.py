from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CrawlerResult(BaseModel):
    title: str
    url: str
    source_type: str
    source_platform: str | None = None
    published_at: datetime | None = None
    raw_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    crawler_name: str
    crawled_at: datetime = Field(default_factory=utc_now)


@dataclass(slots=True)
class CrawlError:
    url: str
    message: str
    status_code: int | None = None
    retryable: bool = False


@dataclass(slots=True)
class DiscoveredLink:
    url: str
    text: str = ""
    source_url: str | None = None
    priority: int = 3
    reason: str = ""


@dataclass(slots=True)
class AttachmentCandidate:
    url: str
    filename: str | None = None
    extension: str | None = None
    source_url: str | None = None
    link_text: str = ""


@dataclass(slots=True)
class CrawlPage:
    url: str
    title: str | None = None
    text: str = ""
    markdown: str | None = None
    html: str | None = None
    links: list[DiscoveredLink] = field(default_factory=list)
    status_code: int | None = None
    content_hash: str | None = None
    fetched_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ExtractedCompetitionCandidate:
    raw_name: str
    normalized_name: str | None = None
    raw_category: str | None = None
    raw_level: str | None = None
    raw_award: str | None = None
    raw_score: str | None = None
    confidence: float = 0.0
    evidence_text: str = ""
    table_row: str | None = None
    page_number: int | None = None
    source_url: str | None = None
    needs_manual_review: bool = True


@dataclass(slots=True)
class ExtractedRecognitionCandidate:
    raw_competition_name: str
    recognition_status: str
    usage_type: str = "other"
    evidence_text: str = ""
    evidence_page: int | None = None
    evidence_section: str | None = None
    score_text: str | None = None
    confidence: float = 0.0
    needs_manual_review: bool = True


@dataclass(slots=True)
class CrawlerRunResult:
    target_name: str
    target_url: str
    pages_discovered: int = 0
    pages_fetched: int = 0
    documents_found: int = 0
    documents_parsed: int = 0
    competitions_found: int = 0
    colleges_found: int = 0
    policies_found: int = 0
    review_items: int = 0
    errors: list[CrawlError] = field(default_factory=list)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    @property
    def status(self) -> str:
        if self.errors and (self.pages_fetched or self.documents_found or self.policies_found):
            return "partial"
        if self.errors and not self.pages_fetched:
            return "failed"
        return "completed"
