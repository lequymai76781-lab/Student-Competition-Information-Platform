from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

from app.crawler.base import DiscoveredLink


@dataclass(slots=True)
class CollegeCandidate:
    name: str
    official_website: str
    official_domain: str
    source_url: str | None
    source_hash: str
    confidence: float


class CollegeDiscoveryService:
    directory_keywords = ["学院", "学部", "院系", "教学单位", "二级单位", "院系设置", "机构设置"]

    def discover(self, links: list[DiscoveredLink], official_domain: str) -> list[CollegeCandidate]:
        candidates: list[CollegeCandidate] = []
        seen: set[tuple[str, str]] = set()
        for link in links:
            if not self._is_allowed_domain(link.url, official_domain):
                continue
            text = link.text.strip()
            if not text or not any(keyword in text for keyword in self.directory_keywords):
                continue
            name = self._normalize_name(text)
            if not name or len(name) > 80:
                continue
            domain = urlparse(link.url).netloc.lower()
            key = (name, domain)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                CollegeCandidate(
                    name=name,
                    official_website=link.url,
                    official_domain=domain,
                    source_url=link.source_url,
                    source_hash=sha256(f"{link.source_url}|{link.url}|{name}".encode("utf-8")).hexdigest(),
                    confidence=0.8 if "学院" in name else 0.6,
                )
            )
        return candidates

    def _normalize_name(self, text: str) -> str:
        for sep in ["-", "_", "|", "·", "：", ":"]:
            text = text.split(sep)[0]
        return text.strip()

    def _is_allowed_domain(self, url: str, official_domain: str) -> bool:
        netloc = urlparse(url).netloc.lower()
        domain = official_domain.lower()
        return netloc == domain or netloc.endswith(f".{domain}")
