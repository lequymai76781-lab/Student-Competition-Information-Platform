from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from time import sleep
from urllib.parse import unquote, urlparse

import httpx

from app.crawler.base import BaseCrawler, CrawlError


@dataclass(slots=True)
class DocumentFetchResult:
    url: str
    path: Path
    filename: str
    content_type: str | None
    extension: str
    file_hash: str
    file_size: int


class DocumentFetcher(BaseCrawler):
    timeout_seconds = 30.0

    def __init__(self, storage_dir: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, url: str, referer: str | None = None) -> DocumentFetchResult | CrawlError:
        if not self.can_fetch(url):
            return CrawlError(url=url, message="Blocked by robots.txt", retryable=False)

        headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if referer:
            headers["Referer"] = referer
        last_error: CrawlError | None = None
        for attempt in range(self.rate_limit.max_retries + 1):
            self.wait_for_domain(url)
            try:
                response = httpx.get(url, headers=headers, follow_redirects=True, timeout=self.timeout_seconds)
                if response.status_code >= 400:
                    retryable = response.status_code in {403, 408, 429, 500, 502, 503, 504}
                    last_error = CrawlError(
                        url=url,
                        message=f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        retryable=retryable,
                    )
                    if not retryable:
                        break
                else:
                    content = response.content
                    file_hash = sha256(content).hexdigest()
                    filename = self._filename_from_response(url, response, file_hash)
                    path = self.storage_dir / filename
                    path.write_bytes(content)
                    return DocumentFetchResult(
                        url=url,
                        path=path,
                        filename=filename,
                        content_type=response.headers.get("content-type"),
                        extension=Path(filename).suffix.lower().lstrip("."),
                        file_hash=file_hash,
                        file_size=len(content),
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = CrawlError(url=url, message=str(exc), retryable=True)

            if attempt < self.rate_limit.max_retries:
                sleep(self.rate_limit.backoff_factor**attempt)

        return last_error or CrawlError(url=url, message="Unknown document fetch failure", retryable=True)

    def _filename_from_url(self, url: str, file_hash: str) -> str:
        name = Path(unquote(urlparse(url).path)).name
        if not name or "." not in name:
            name = f"document-{file_hash[:12]}.bin"
        return self._safe_filename(name)

    def _filename_from_response(self, url: str, response: httpx.Response, file_hash: str) -> str:
        disposition = response.headers.get("content-disposition", "")
        encoded = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.I)
        plain = re.search(r'filename="?([^";]+)', disposition, re.I)
        name = unquote(encoded.group(1)) if encoded else (plain.group(1).strip() if plain else "")
        if not name:
            name = Path(unquote(urlparse(str(response.url)).path)).name
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
        mime_extensions = {
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }
        if not Path(name).suffix and content_type in mime_extensions:
            name = f"{name or 'document'}{mime_extensions[content_type]}"
        if not name or "." not in name:
            name = f"document-{file_hash[:12]}.bin"
        return self._safe_filename(name)

    def _safe_filename(self, name: str) -> str:
        return "".join(char if char.isalnum() or char in ".-_" else "_" for char in name)[:180]