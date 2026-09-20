from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.crawler.fetchers.html_fetcher import FetchResult
from app.services.university_radar_discovery_service import (
    CrawlBudget,
    DiscoveryFunnel,
    UniversityRadarDiscoveryService,
)


class FakeFetchError:
    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code


def make_fetch_result(url: str, html: str, final_url: str | None = None) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=200,
        final_url=final_url or url,
        content=html.encode("utf-8"),
        text=html,
        content_type="text/html",
        content_hash="hash",
    )


def make_service() -> UniversityRadarDiscoveryService:
    service = UniversityRadarDiscoveryService()
    service._search_multi = lambda *args, **kwargs: ([], None)
    service._search_sogou = lambda *args, **kwargs: ([], None)
    return service


def test_canonical_url() -> None:
    service = UniversityRadarDiscoveryService()
    assert service._canonical_url("https://example.edu.cn/a/?x=1#frag") == "https://example.edu.cn/a/?x=1"
    assert service._canonical_url("ftp://example.edu.cn/a") == ""
    assert service._canonical_url("/relative") == ""
    assert service._canonical_url("https://jwc.example.edu.cn/a") != service._canonical_url("https://www.example.edu.cn/a")


def test_department_match_and_priority() -> None:
    service = UniversityRadarDiscoveryService()
    match = service._department_match("https://jwc.example.edu.cn/", "教务处")
    assert match == ("教务处", 1)
    assert service._department_match("https://graduate.example.edu.cn/", "研究生院") == ("研究生院", 2)
    assert service._department_match("https://example.edu.cn/x", "通知公告") == ("通知公告", 3)
    assert service._department_match("https://example.edu.cn/x", "关于我们") is None


def test_department_candidates_are_sorted_and_budgeted() -> None:
    service = UniversityRadarDiscoveryService()
    service.budget = CrawlBudget(max_department_entries=2)
    links = [
        ("https://graduate.example.edu.cn/", "研究生院"),
        ("https://jwc.example.edu.cn/", "教务处"),
        ("https://tw.example.edu.cn/", "团委"),
    ]
    result = service._department_candidates(links, "https://www.example.edu.cn", "example.edu.cn")
    assert [item["label"] for item in result] == ["教务处", "团委"]
    assert result[0]["priority"] == 1


def test_department_merge_deduplicates_and_keeps_priority() -> None:
    service = UniversityRadarDiscoveryService()
    primary = [
        {"url": "https://jwc.example.edu.cn/", "label": "教务处", "priority": 1, "source": "homepage"},
        {"url": "https://tw.example.edu.cn/", "label": "团委", "priority": 1, "source": "homepage"},
    ]
    supplemental = [
        {"url": "https://jwc.example.edu.cn/", "label": "通知公告", "priority": 3, "source": "known_path"},
        {"url": "https://graduate.example.edu.cn/", "label": "研究生院", "priority": 2, "source": "known_path"},
    ]
    merged = service._merge_departments(primary, supplemental)
    assert len(merged) == 3
    jwc = next(item for item in merged if item["url"] == "https://jwc.example.edu.cn/")
    assert jwc["priority"] == 1


def test_known_entry_probe_respects_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    service.budget = CrawlBudget(max_known_entry_probes=3)
    attempted = 0

    def fake_fetch(url: str):
        nonlocal attempted
        attempted += 1
        return make_fetch_result(url, "<title>教务处</title>")

    monkeypatch.setattr(service.fetcher, "fetch", fake_fetch)
    found, outcome = service._probe_known_entries(
        "https://www.example.edu.cn",
        "example.edu.cn",
        DiscoveryFunnel(),
        [],
    )
    assert attempted == 3
    assert outcome.pages == 3
    assert found


def test_school_specific_entries_are_official_entry_hints_not_result_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    visited: list[str] = []

    def fake_fetch(url: str):
        visited.append(url)
        return make_fetch_result(url, "<title>通知公告</title>")

    monkeypatch.setattr(service.fetcher, "fetch", fake_fetch)
    found, _ = service._probe_known_entries(
        "https://www.hzau.edu.cn",
        "hzau.edu.cn",
        DiscoveryFunnel(),
        [],
    )
    assert "https://coi.hzau.edu.cn/tzgg.htm" in visited
    assert any(item["source"] == "known_path" for item in found)


def test_internal_search_candidates_only_discover_official_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    links = [("https://www.example.edu.cn/search?q=", "搜索")]
    html = '<a href="https://jwc.example.edu.cn/info/1001/1.html">数学建模竞赛报名通知</a>'
    monkeypatch.setattr(
        service.fetcher,
        "fetch",
        lambda url: make_fetch_result(url, html),
    )
    candidates, outcome = service._internal_search_candidates(
        links,
        "example.edu.cn",
        DiscoveryFunnel(),
    )
    assert outcome.status == "ok"
    assert candidates == [("https://jwc.example.edu.cn/info/1001/1.html", "数学建模竞赛报名通知")]


def test_sitemap_candidates_and_parse_sitemap() -> None:
    service = UniversityRadarDiscoveryService()
    items = service._parse_sitemap(
        """<urlset><url><loc>https://jwc.example.edu.cn/info/1.html</loc><lastmod>2026-09-01</lastmod></url></urlset>"""
    )
    assert items
    assert items[0]["url"] == "https://jwc.example.edu.cn/info/1.html"
    assert items[0]["kind"] == "url"


def test_sitemap_candidates_follows_robots_and_filters_official_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    responses = {
        "https://www.example.edu.cn/robots.txt": "Sitemap: https://www.example.edu.cn/sitemap.xml",
        "https://www.example.edu.cn/sitemap.xml": "<urlset><url><loc>https://jwc.example.edu.cn/notice/1.html</loc></url></urlset>",
    }
    monkeypatch.setattr(
        service.fetcher,
        "fetch",
        lambda url: make_fetch_result(url, responses.get(url, "")),
    )
    candidates = service._sitemap_candidates(
        "https://www.example.edu.cn",
        "example.edu.cn",
        DiscoveryFunnel(),
    )
    assert any(item["url"] == "https://jwc.example.edu.cn/notice/1.html" for item in candidates)


@pytest.mark.parametrize("status", [403, 412])
def test_blocked_fetch_is_source_unavailable(status: int) -> None:
    service = UniversityRadarDiscoveryService()
    assert service._is_blocked(FakeFetchError("HTTP 412" if status == 412 else "HTTP 403", status))
    funnel = DiscoveryFunnel()
    funnel.fetched("https://example.edu.cn/", FakeFetchError("HTTP 412" if status == 412 else "HTTP 403", status))
    assert funnel.as_dict()["source_unavailable"] == 1


def test_discovery_funnel_counts_candidates_leads_and_outcomes() -> None:
    funnel = DiscoveryFunnel()
    funnel.discover("https://www.example.edu.cn/", "homepage", entry=True)
    funnel.discover("https://jwc.example.edu.cn/", "department", entry=True)
    funnel.candidate_urls.add("https://jwc.example.edu.cn/notice/1.html")
    funnel.lead_urls.add("https://jwc.example.edu.cn/notice/1.html")
    funnel.fetched("https://blocked.example.edu.cn/", FakeFetchError("HTTP 403", 403))
    data = funnel.as_dict()
    assert data["entry_urls_discovered"] == 2
    assert data["competition_candidate_pages"] == 1
    assert data["valid_competition_leads"] == 1
    assert data["http_403"] == 1
    assert data["source_unavailable"] == 1


def test_crawl_budget_defaults_are_finite() -> None:
    budget = CrawlBudget()
    assert budget.max_department_entries <= 32
    assert budget.max_page_fetches <= 500
    assert budget.max_candidate_urls <= 500
    assert budget.max_known_entry_probes <= 16


def test_main_discovery_path_runs_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    homepage = """
    <a href="https://jwc.example.edu.cn/">教务处</a>
    <a href="https://jwc.example.edu.cn/notice/1.html">2026年全国大学生数学建模竞赛校内选拔报名通知</a>
    """
    monkeypatch.setattr(
        service.fetcher,
        "fetch",
        lambda url: make_fetch_result(url, homepage),
    )
    result = service._discover_university(
        {
            "name": "测试大学",
            "short_name": "测试",
            "aliases": [],
            "official_domain": "example.edu.cn",
            "official_website": "https://www.example.edu.cn",
        },
        "v082-test-batch",
        {},
        [],
        datetime.now(timezone.utc),
    )
    report = result["report"]
    assert report["seed_version"] == "v0.8.2"
    assert "discovery_funnel" in report
    assert report["discovery_funnel"]["entry_urls_discovered"] >= 1
