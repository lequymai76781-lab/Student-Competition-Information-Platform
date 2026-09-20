import re
from urllib.parse import urlparse

from app.crawler.base import DiscoveredLink


class PolicyDiscoveryService:
    policy_keywords = [
        "推免",
        "推荐免试",
        "推荐优秀应届本科毕业生",
        "推免实施办法",
        "推免实施细则",
        "推免综合评价",
        "综合素质评价",
        "综合测评",
        "学科竞赛",
        "竞赛认定",
        "竞赛目录",
        "竞赛清单",
        "竞赛奖励",
        "创新创业",
        "创新成果",
        "科研成果",
        "附加分",
        "加分细则",
        "素质拓展",
        "奖励分",
        "学生竞赛",
        "本科生竞赛",
        "赛事认定",
    ]
    high_priority_keywords = ["推免", "竞赛目录", "竞赛认定", "竞赛清单", "推荐免试"]
    policy_document_markers = [
        "推免",
        "推荐免试",
        "办法",
        "细则",
        "规定",
        "目录",
        "清单",
        "名单",
        "认定",
        "评价",
        "测评",
        "加分",
        "奖励分",
        "学分",
    ]
    years = ["2026", "2025", "2024"]

    def discover(self, links: list[DiscoveredLink], official_domain: str) -> list[DiscoveredLink]:
        candidates: list[DiscoveredLink] = []
        seen: set[str] = set()
        for link in links:
            if link.url in seen or not self._is_allowed_domain(link.url, official_domain):
                continue
            text = f"{link.text} {link.url}"
            score = self._score(text)
            if score <= 0:
                continue
            seen.add(link.url)
            candidates.append(
                DiscoveredLink(
                    url=link.url,
                    text=link.text,
                    source_url=link.source_url,
                    priority=self._priority(score, text),
                    reason=f"policy_keyword_score={score}",
                )
            )
        return sorted(candidates, key=lambda item: (item.priority, item.url))

    def _score(self, text: str) -> int:
        if not any(marker in text for marker in self.policy_document_markers):
            return 0

        high_priority_hits = sum(1 for keyword in self.high_priority_keywords if keyword in text)
        policy_hits = sum(1 for keyword in self.policy_keywords if keyword in text)
        if high_priority_hits == 0 and policy_hits == 0:
            return 0

        score = high_priority_hits * 2 + policy_hits
        score += sum(1 for year in self.years if year in text)
        if re.search(r"20(2[4-6])", text):
            score += 1
        return score

    def _priority(self, score: int, text: str) -> int:
        if any(keyword in text for keyword in ["推免", "竞赛目录", "竞赛认定"]) and any(year in text for year in self.years):
            return 0
        if score >= 4:
            return 1
        if score >= 2:
            return 2
        return 3

    def _is_allowed_domain(self, url: str, official_domain: str) -> bool:
        netloc = urlparse(url).netloc.lower()
        domain = official_domain.lower()
        return netloc == domain or netloc.endswith(f".{domain}")
