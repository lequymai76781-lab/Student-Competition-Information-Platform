from dataclasses import dataclass
import urllib.error
import urllib.parse
import urllib.request
from time import sleep
from urllib.parse import urlparse


@dataclass(slots=True)
class RateLimitConfig:
    min_delay_seconds: float = 0.5
    max_retries: int = 2
    backoff_factor: float = 1.8


class BaseCrawler:
    user_agent = "StudentCompetitionIntelligenceBot/0.2 (+policy-research; contact: local-dev)"

    def __init__(self, *, rate_limit: RateLimitConfig | None = None, respect_robots: bool = True) -> None:
        self.rate_limit = rate_limit or RateLimitConfig()
        self.respect_robots = respect_robots
        self._last_request_by_domain: dict[str, float] = {}
        self._robots_cache: dict[str, bool] = {}

    def wait_for_domain(self, url: str) -> None:
        domain = urlparse(url).netloc
        if not domain:
            return
        import time

        last_request = self._last_request_by_domain.get(domain)
        now = time.monotonic()
        if last_request is not None:
            elapsed = now - last_request
            if elapsed < self.rate_limit.min_delay_seconds:
                sleep(self.rate_limit.min_delay_seconds - elapsed)
        self._last_request_by_domain[domain] = time.monotonic()

    def can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        allowed = self._robots_cache.get(robots_url)
        if allowed is None:
            allowed = self._robots_allows(robots_url, url)
            self._robots_cache[robots_url] = allowed
        return allowed

    def _robots_allows(self, robots_url: str, url: str) -> bool:
        """RFC 9309-ish handling: robots.txt unavailable -> allow; parse rules otherwise."""
        try:
            request = urllib.request.Request(
                robots_url,
                headers={"User-Agent": self.user_agent, "Accept": "text/plain,*/*"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
            content_type = response.headers.get("content-type", "")
            if b"<html" in raw[:2000].lower() and b"disallow" not in raw.lower():
                return True
            try:
                text = raw.decode("utf-8", "ignore")
            except Exception:
                text = raw.decode("latin-1", "ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return True
        groups: list[dict] = []
        current: dict | None = None
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip().lower()
            if not line:
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "user-agent":
                current = {"agents": [value], "rules": []}
                groups.append(current)
            elif key in {"allow", "disallow"} and current is not None:
                rule_path = urllib.parse.unquote(value) or "/"
                if not rule_path.startswith("/"):
                    rule_path = f"/{rule_path}"
                current["rules"].append({"path": rule_path, "allowed": key == "allow"})
        if not groups:
            return True
        target_agent = self.user_agent.lower()
        selected = next(
            (group for group in groups if any(agent == "*" for agent in group["agents"])),
            None,
        )
        for group in groups:
            if any(target_agent == agent for agent in group["agents"]):
                selected = group
                break
        if selected is None:
            return True
        target_path = urlparse(url).path or "/"
        best_length = -1
        allowed = True
        for rule in selected["rules"]:
            rule_path = rule["path"]
            if target_path.startswith(rule_path) and len(rule_path) > best_length:
                best_length = len(rule_path)
                allowed = rule["allowed"]
        return allowed
