from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from heapq import heappop, heappush
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.crawler.base import CrawlError, DiscoveredLink
from app.crawler.discovery.attachment_discovery import AttachmentDiscoveryService
from app.crawler.discovery.url_normalizer import OfficialUrlNormalizer
from app.crawler.extractors.policy_classifier import PolicyClassifier
from app.crawler.fetchers.html_fetcher import FetchResult, HtmlFetcher
from app.crawler.parsers.html_parser import HtmlContentParser


SearchProvider = Callable[[str, str], list[dict[str, str]]]


class _SearchFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "form":
            self.current = {
                "action": values.get("action", ""),
                "method": values.get("method", "get"),
                "inputs": [],
            }
        elif tag.lower() == "input" and self.current is not None:
            self.current["inputs"].append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


@dataclass(slots=True)
class DiscoveredPolicy:
    url: str
    title: str
    source_url: str
    discovery_stage: str
    document_type: str
    category: str | None = None
    recognition_eligible: bool = False


@dataclass(slots=True)
class GeneralPolicyDiscoveryResult:
    school: str
    official_domain: str
    status: str = "DISCOVERY_FAILED"
    pages_fetched: int = 0
    documents: list[DiscoveredPolicy] = field(default_factory=list)
    rejected_pages: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    channels_attempted: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "school": self.school,
            "official_domain": self.official_domain,
            "status": self.status,
            "pages_fetched": self.pages_fetched,
            "documents": [asdict(item) for item in self.documents],
            "rejected_pages": self.rejected_pages,
            "failures": self.failures,
            "channels_attempted": self.channels_attempted,
            "queries": self.queries,
        }


class GeneralUndergraduatePolicyDiscoveryService:
    """Bounded, policy-first discovery for ordinary undergraduate schools."""

    query_templates = (
        '"{school}" 学科竞赛 认定目录',
        '"{school}" 大学生竞赛 管理办法',
        '"{school}" 学科竞赛 分类',
        '"{school}" 创新学分 竞赛',
        '"{school}" 第二课堂 竞赛',
        '"{school}" 竞赛奖励 办法',
        '"{school}" 大学生学科竞赛 PDF',
        'site:{domain} "学科竞赛"',
        'site:{domain} "竞赛管理办法"',
        'site:{domain} filetype:pdf "竞赛"',
    )
    stage_priority = {
        "official_root": 0,
        "teaching_undergraduate": 10,
        "innovation": 20,
        "student_youth": 30,
        "disclosure_rules": 40,
        "downloads_attachments": 50,
        "internal_search": 60,
        "sitemap": 70,
        "external_site_search": 5,
    }
    navigation_terms = {
        "teaching_undergraduate": ("教务处", "本科生院", "本科教学", "jwc", "bksy", "undergraduate", "teaching"),
        "innovation": ("创新创业", "双创", "创新中心", "cxcy", "innovation"),
        "student_youth": ("学生处", "学生工作", "团委", "xgb", "xsc", "youth"),
        "disclosure_rules": ("信息公开", "规章制度", "管理制度", "政策文件", "xxgk", "rules"),
        "downloads_attachments": ("下载中心", "资料下载", "附件", "download", "upload", "file"),
        "internal_search": ("站内搜索", "搜索", "检索", "search", "ssjg", "sousuo"),
    }
    policy_terms = (
        "学科竞赛",
        "学术科技竞赛",
        "大学生竞赛",
        "学生竞赛",
        "竞赛目录",
        "竞赛清单",
        "竞赛分类",
        "竞赛管理办法",
        "竞赛奖励",
        "创新创业学分",
        "创新实践学分",
        "创新学分",
        "第二课堂",
    )

    def __init__(self, *, html_fetcher: HtmlFetcher | None = None) -> None:
        self.html_fetcher = html_fetcher or HtmlFetcher(respect_robots=True)
        self.html_parser = HtmlContentParser()
        self.attachments = AttachmentDiscoveryService()
        self.classifier = PolicyClassifier()
        self.urls = OfficialUrlNormalizer()

    def build_queries(self, school: str, domain: str) -> list[str]:
        return [template.format(school=school, domain=domain) for template in self.query_templates]

    def discover(
        self,
        *,
        school: str,
        official_website: str,
        official_domain: str,
        search_provider: SearchProvider | None = None,
        search_results: list[dict[str, str]] | None = None,
        max_pages: int = 24,
        exhaustive: bool = False,
    ) -> GeneralPolicyDiscoveryResult:
        result = GeneralPolicyDiscoveryResult(school=school, official_domain=official_domain)
        queue: list[tuple[int, int, str, str, str, str]] = []
        queued: set[str] = set()
        visited: set[str] = set()
        documents: dict[str, DiscoveredPolicy] = {}
        serial = 0

        def enqueue(stage: str, url: str, title: str, source_url: str) -> None:
            nonlocal serial
            normalized = self.urls.normalize(url, base_url=source_url)
            if not normalized or normalized in queued or not self.urls.is_official(normalized, official_domain):
                return
            queued.add(normalized)
            serial += 1
            heappush(queue, (self.stage_priority[stage], serial, stage, normalized, title, source_url))

        root = self.urls.normalize(official_website)
        enqueue("official_root", root, school, root)
        for sitemap_path in ("/robots.txt", "/sitemap.xml", "/sitemap_index.xml"):
            parts = urlsplit(root)
            enqueue("sitemap", f"{parts.scheme}://{parts.netloc}{sitemap_path}", "sitemap", root)

        result.queries = self.build_queries(school, official_domain)
        supplied_results = list(search_results or [])
        if search_provider:
            result.channels_attempted.append("external_site_search")
            for query in result.queries:
                supplied_results.extend(search_provider(query, official_domain))
        if supplied_results:
            result.channels_attempted.append("external_site_search")
            for item in supplied_results:
                enqueue("external_site_search", item.get("url", ""), item.get("title", ""), root)

        while queue and result.pages_fetched < max_pages:
            _, _, stage, url, title_hint, source_url = heappop(queue)
            if url in visited:
                continue
            visited.add(url)
            if stage not in result.channels_attempted:
                result.channels_attempted.append(stage)

            attachment = self.attachments.discover(
                [DiscoveredLink(url=url, text=title_hint, source_url=source_url)]
            )
            if attachment:
                item = attachment[0]
                documents[url] = DiscoveredPolicy(
                    url=url,
                    title=title_hint or item.filename or url,
                    source_url=item.source_url or source_url or root,
                    discovery_stage=stage,
                    document_type=item.extension or "attachment_endpoint",
                )
                continue

            fetched = self.html_fetcher.fetch(url)
            result.pages_fetched += 1
            if isinstance(fetched, CrawlError):
                result.failures.append(
                    {"url": url, "stage": stage, "status_code": fetched.status_code, "error": fetched.message}
                )
                continue
            final_url = self.urls.normalize(fetched.final_url)
            if not self.urls.is_official(final_url, official_domain):
                result.failures.append({"url": url, "stage": stage, "error": "redirected_off_official_domain"})
                continue
            if stage == "sitemap" or "xml" in (fetched.content_type or "").lower():
                for discovered_url in re.findall(r"<loc>\s*([^<]+)\s*</loc>", fetched.text, re.I):
                    if self._has_policy_signal(discovered_url):
                        enqueue("sitemap", discovered_url, discovered_url.rsplit("/", 1)[-1], final_url)
                continue

            page = self.html_parser.parse(fetched.text, final_url)
            title = page.title or title_hint or final_url
            for search_url in self._internal_search_urls(fetched.text, final_url):
                enqueue("internal_search", search_url, "学科竞赛", final_url)
            classification = self.classifier.classify(title, page.text)
            page_is_policy = self._looks_like_policy_document(title, classification.category)
            if page_is_policy:
                documents[final_url] = DiscoveredPolicy(
                    url=final_url,
                    title=title,
                    source_url=final_url,
                    discovery_stage=stage,
                    document_type="html",
                    category=classification.category,
                    recognition_eligible=classification.recognition_eligible,
                )
            elif self._has_policy_signal(title, page.text):
                result.rejected_pages.append(
                    {"url": final_url, "title": title, "category": classification.category}
                )

            for item in self.attachments.discover(page.links):
                attachment_title = item.link_text or item.filename or ""
                if not page_is_policy and not self._looks_like_policy_document(
                    attachment_title,
                    self.classifier.classify(attachment_title, "").category,
                ):
                    continue
                normalized = self.urls.normalize(item.url, base_url=final_url)
                if normalized and self.urls.is_official(normalized, official_domain):
                    documents[normalized] = DiscoveredPolicy(
                        url=normalized,
                        title=attachment_title or normalized,
                        source_url=final_url,
                        discovery_stage="downloads_attachments",
                        document_type=item.extension or "attachment_endpoint",
                    )
            for link in page.links:
                link_url = self.urls.normalize(link.url, base_url=final_url)
                if not link_url or not self.urls.is_official(link_url, official_domain):
                    continue
                if self.attachments.discover([link]):
                    continue
                policy_marker = f"{link.text} {link_url}".lower()
                if self._has_policy_signal(policy_marker):
                    enqueue(stage if stage != "official_root" else "teaching_undergraduate", link_url, link.text, final_url)
                    continue
                nav_marker = link.text.lower()
                if stage == "official_root":
                    nav_marker = f"{nav_marker} {urlsplit(link_url).netloc.lower()}"
                next_stage = self._navigation_stage(nav_marker)
                if next_stage and self.stage_priority[next_stage] > self.stage_priority.get(stage, 0):
                    enqueue(next_stage, link_url, link.text, final_url)

        result.documents = sorted(documents.values(), key=lambda item: (item.discovery_stage, item.url))
        if result.documents:
            result.status = "VERIFIED_DATA"
        else:
            technical = [item for item in result.failures if self._is_technical_failure(item)]
            reachable = result.pages_fetched - len(result.failures)
            if technical and reachable == 0:
                result.status = "ACCESS_LIMITED"
            elif result.rejected_pages:
                result.status = "AMBIGUOUS"
            elif exhaustive and {"official_root", "sitemap", "external_site_search"}.issubset(result.channels_attempted):
                result.status = "VERIFIED_NO_PUBLIC_POLICY"
            else:
                result.status = "DISCOVERY_FAILED"
        return result

    def _internal_search_urls(self, html: str, base_url: str) -> list[str]:
        """Expand ordinary GET search forms without treating result snippets as evidence."""
        parser = _SearchFormParser()
        parser.feed(html)
        urls: list[str] = []
        for form in parser.forms:
            if str(form.get("method", "get")).lower() != "get":
                continue
            action = self.urls.normalize(str(form.get("action") or base_url), base_url=base_url)
            if not action:
                continue
            inputs = form["inputs"]
            fields = [
                item for item in inputs
                if item.get("name") and str(item.get("type", "text")).lower() in {"text", "search"}
            ]
            if not fields:
                continue
            preferred = next(
                (
                    item for item in fields
                    if any(term in str(item.get("name", "")).lower() for term in (
                        "keyword", "query", "search", "key", "word", "showkeycode",
                    ))
                ),
                fields[0],
            )
            parts = urlsplit(action)
            base_params = dict(parse_qsl(parts.query, keep_blank_values=True))
            for hidden in inputs:
                if str(hidden.get("type", "")).lower() == "hidden" and hidden.get("name"):
                    base_params[str(hidden["name"])] = str(hidden.get("value", ""))
            for query in ("学科竞赛", "竞赛管理办法", "竞赛目录"):
                params = dict(base_params)
                params[str(preferred["name"])] = query
                urls.append(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), "")))
        return list(dict.fromkeys(urls))

    def _looks_like_policy_document(self, title: str, category: str) -> bool:
        if category not in {
            "competition_policy",
            "competition_catalog",
            "innovation_credit_policy",
            "second_classroom_policy",
        }:
            return False
        normalized = " ".join((title or "").split())
        formal_markers = (
            "管理办法",
            "实施办法",
            "管理规定",
            "实施细则",
            "奖励办法",
            "奖励方案",
            "认定办法",
            "认定标准",
            "认定目录",
            "竞赛目录",
            "竞赛清单",
            "分类一览表",
            "项目目录",
            "分级目录",
            "项目库",
            "章程",
        )
        return self._has_policy_signal(normalized) and any(marker in normalized for marker in formal_markers)

    def _navigation_stage(self, marker: str) -> str | None:
        for stage, terms in self.navigation_terms.items():
            if any(term.lower() in marker for term in terms):
                return stage
        return None

    @staticmethod
    def _is_technical_failure(item: dict[str, Any]) -> bool:
        error = str(item.get("error", "")).lower()
        return item.get("status_code") in {403, 412} or any(
            term in error for term in (
                "blocked by robots", "login", "timeout", "timed out", "ssl", "connect",
                "name resolution", "dns", "attachment", "download",
            )
        )

    def _has_policy_signal(self, *values: str) -> bool:
        corpus = " ".join(values)
        return any(term.lower() in corpus.lower() for term in self.policy_terms)
