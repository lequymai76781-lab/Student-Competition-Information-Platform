from dataclasses import dataclass
from hashlib import sha256
import shutil
import subprocess
from time import sleep

import httpx

from app.crawler.base import BaseCrawler, CrawlError


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    final_url: str
    content: bytes
    text: str
    content_type: str | None
    content_hash: str


class HtmlFetcher(BaseCrawler):
    timeout_seconds = 15.0
    _curl_marker = b"\n__HTML_FETCH_META__"

    def fetch(self, url: str) -> FetchResult | CrawlError:
        if not self.can_fetch(url):
            return CrawlError(url=url, message="Blocked by robots.txt", retryable=False)

        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        last_error: CrawlError | None = None
        for attempt in range(self.rate_limit.max_retries + 1):
            self.wait_for_domain(url)
            response: httpx.Response | None = None
            try:
                response = httpx.get(url, headers=headers, follow_redirects=True, timeout=self.timeout_seconds)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                response = self._fetch_with_system_curl(url, headers)
                if response is None:
                    last_error = CrawlError(url=url, message=str(exc), retryable=True)

            if response is not None:
                content_type = response.headers.get("content-type")
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
                    return FetchResult(
                        url=url,
                        status_code=response.status_code,
                        final_url=str(response.url),
                        content=content,
                        text=response.text,
                        content_type=content_type,
                        content_hash=sha256(content).hexdigest(),
                    )

            if attempt < self.rate_limit.max_retries:
                sleep(self.rate_limit.backoff_factor**attempt)

        return last_error or CrawlError(url=url, message="Unknown fetch failure", retryable=True)

    def _fetch_with_system_curl(self, url: str, headers: dict[str, str]) -> httpx.Response | None:
        """Use Windows Schannel through curl.exe when Python OpenSSL transport fails."""
        executable = shutil.which("curl.exe")
        if not executable:
            return None
        command = [
            executable,
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            str(int(self.timeout_seconds)),
        ]
        for name, value in headers.items():
            command.extend(["--header", f"{name}: {value}"])
        command.extend([
            "--write-out",
            "\n__HTML_FETCH_META__%{http_code}\t%{content_type}\t%{url_effective}",
            url,
        ])
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds + 5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        marker_at = completed.stdout.rfind(self._curl_marker)
        if marker_at < 0:
            return None
        content = completed.stdout[:marker_at]
        try:
            status_text, content_type, final_url = completed.stdout[
                marker_at + len(self._curl_marker):
            ].decode("utf-8", "replace").split("\t", 2)
            status_code = int(status_text)
        except (ValueError, TypeError):
            return None
        return httpx.Response(
            status_code,
            content=content,
            headers={"content-type": content_type},
            request=httpx.Request("GET", final_url or url),
        )