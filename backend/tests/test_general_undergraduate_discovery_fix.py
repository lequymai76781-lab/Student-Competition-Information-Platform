from hashlib import sha256
from pathlib import Path

import httpx

from app.crawler.base import CrawlError, DiscoveredLink
from app.crawler.base.base_crawler import RateLimitConfig
from app.crawler.discovery.attachment_discovery import AttachmentDiscoveryService
from app.crawler.discovery.general_undergraduate_policy_discovery import (
    GeneralUndergraduatePolicyDiscoveryService,
)
from app.crawler.discovery.university_discovery import UniversitySeed
from app.crawler.discovery.url_normalizer import OfficialUrlNormalizer
from app.crawler.extractors.policy_classifier import PolicyClassifier
from app.crawler.extractors.policy_relation_extractor import PolicyRelationExtractor
from app.crawler.fetchers.document_fetcher import DocumentFetcher
from app.crawler.fetchers.html_fetcher import FetchResult, HtmlFetcher
from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline


def _html(url: str, body: str) -> FetchResult:
    content = body.encode("utf-8")
    return FetchResult(
        url=url,
        status_code=200,
        final_url=url,
        content=content,
        text=body,
        content_type="text/html",
        content_hash=sha256(content).hexdigest(),
    )


class GraphFetcher:
    pages = {
        "https://www.example.edu.cn/": """
            <html><title>示例大学</title><a href="https://jwc.example.edu.cn/">教务处</a></html>
        """,
        "https://jwc.example.edu.cn/": """
            <html><title>教务处</title><a href="/policy.html">学科竞赛管理办法</a></html>
        """,
        "https://jwc.example.edu.cn/policy.html": """
            <html><title>示例大学学科竞赛管理办法</title>
            <body>本办法规定竞赛目录和奖励范围。
            <a href="/system/_content/download.jsp?owner=1&amp;wbfileid=2">附件1：学科竞赛目录.pdf</a>
            </body></html>
        """,
    }

    def fetch(self, url: str):
        body = self.pages.get(url)
        if body is None:
            return CrawlError(url=url, message="not found", status_code=404)
        return _html(url, body)


class ProjectCatalogNoticeFetcher:
    pages = {
        "https://www.example.edu.cn/": """
            <html><title>示例大学</title>
            <a href="https://cxcy.example.edu.cn/notice.html">创新创业学院</a></html>
        """,
        "https://cxcy.example.edu.cn/notice.html": """
            <html><title>附件下载</title><body>
            <a href="/b-list.pdf">附件：学校B类学科竞赛认定项目目录（2023年）.pdf</a>
            </body></html>
        """,
    }

    def fetch(self, url: str):
        body = self.pages.get(url)
        if body is None:
            return CrawlError(url=url, message="not found", status_code=404)
        return _html(url, body)

class BlockedFetcher:
    def fetch(self, url: str):
        return CrawlError(url=url, message="HTTP 403", status_code=403)


class TimeoutFetcher:
    def fetch(self, url: str):
        return CrawlError(url=url, message="SSL handshake timed out")


class SearchFormFetcher:
    def fetch(self, url: str):
        if url == "https://www.example.edu.cn/":
            return _html(url, """
                <html><title>示例大学</title><form action="/search.htm" method="get">
                <input type="hidden" name="wbtreeid" value="1001">
                <input type="text" name="showkeycode"></form></html>
            """)
        if url.startswith("https://www.example.edu.cn/search.htm?"):
            return _html(url, '<html><a href="/files/catalog.pdf">学科竞赛目录附件</a></html>')
        return CrawlError(url=url, message="not found", status_code=404)


class PolicyListingFetcher:
    pages = {
        "https://www.example.edu.cn/": """
            <html><title>\u793a\u4f8b\u5927\u5b66</title>
            <a href="https://cxcy.example.edu.cn/rules.htm">\u521b\u65b0\u521b\u4e1a\u5b66\u9662</a></html>
        """,
        "https://cxcy.example.edu.cn/rules.htm": """
            <html><title>\u89c4\u7ae0\u5236\u5ea6</title><body>
            \u5b66\u79d1\u7ade\u8d5b\u7ba1\u7406\u529e\u6cd5\u76f8\u5173\u6587\u4ef6
            <a href="/policy.html">\u793a\u4f8b\u5927\u5b66\u5b66\u79d1\u7ade\u8d5b\u7ba1\u7406\u529e\u6cd5</a>
            <a href="/apply.docx">\u8d5b\u4e8b\u62a5\u540d\u8868</a>
            </body></html>
        """,
        "https://cxcy.example.edu.cn/policy.html": """
            <html><title>\u793a\u4f8b\u5927\u5b66\u5b66\u79d1\u7ade\u8d5b\u7ba1\u7406\u529e\u6cd5</title>
            <body>\u672c\u529e\u6cd5\u89c4\u5b9a\u5927\u5b66\u751f\u5b66\u79d1\u7ade\u8d5b\u7ec4\u7ec7\u548c\u7ba1\u7406\u3002</body></html>
        """,
    }

    def fetch(self, url: str):
        body = self.pages.get(url)
        if body is None:
            return CrawlError(url=url, message="not found", status_code=404)
        return _html(url, body)

def test_html_fetcher_uses_system_curl_after_transport_error(monkeypatch) -> None:
    fetcher = HtmlFetcher(
        respect_robots=False,
        rate_limit=RateLimitConfig(min_delay_seconds=0, max_retries=0),
    )
    url = "https://school.edu.cn/policy.htm"
    native = httpx.Response(
        200,
        content="<title>学科竞赛管理办法</title>".encode("utf-8"),
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )

    def fail_httpx(*args, **kwargs):
        raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]")

    monkeypatch.setattr(httpx, "get", fail_httpx)
    monkeypatch.setattr(fetcher, "_fetch_with_system_curl", lambda *args, **kwargs: native, raising=False)

    result = fetcher.fetch(url)

    assert isinstance(result, FetchResult)
    assert result.final_url == url
    assert "学科竞赛管理办法" in result.text

def test_url_normalization_preserves_download_query_and_removes_tracking() -> None:
    normalizer = OfficialUrlNormalizer()
    url = normalizer.normalize(
        "../../system/_content/download.jsp?owner=2&wbfileid=8&utm_source=x#top",
        base_url="https://cxcy.example.edu.cn/info/1/2.htm",
    )
    assert url == "https://cxcy.example.edu.cn/system/_content/download.jsp?owner=2&wbfileid=8"
    assert normalizer.is_official(url, "example.edu.cn")
    assert not normalizer.is_official("https://example.edu.cn.evil.test/a.pdf", "example.edu.cn")


def test_attachment_discovery_supports_static_query_and_endpoint_urls() -> None:
    links = [
        DiscoveredLink(url="https://x.edu.cn/a.pdf", text="附件1"),
        DiscoveredLink(url="https://x.edu.cn/get?name=rules.docx", text="附件2"),
        DiscoveredLink(url="https://x.edu.cn/system/_content/download.jsp?wbfileid=3", text="附件3：目录.xlsx"),
        DiscoveredLink(url="https://x.edu.cn/upload/files/form.xls", text="表格"),
        DiscoveredLink(url="https://x.edu.cn/download?file=legacy.doc", text="附件4"),
        DiscoveredLink(url="https://x.edu.cn/read.htm", text="普通页面"),
    ]
    attachments = AttachmentDiscoveryService().discover(links)
    assert [item.extension for item in attachments] == ["pdf", "docx", "xlsx", "xls", "doc"]


def test_document_fetcher_uses_content_disposition_and_mime_for_download_endpoints(tmp_path: Path) -> None:
    fetcher = DocumentFetcher(tmp_path, respect_robots=False)
    request = httpx.Request("GET", "https://x.edu.cn/download?id=1")
    response = httpx.Response(
        200,
        request=request,
        headers={"content-disposition": "attachment; filename*=UTF-8''rules.docx"},
    )
    assert fetcher._filename_from_response(str(request.url), response, "a" * 64) == "rules.docx"
    mime_response = httpx.Response(200, request=request, headers={"content-type": "application/pdf"})
    assert fetcher._filename_from_response(str(request.url), mime_response, "b" * 64).endswith(".pdf")


def test_document_fetcher_sends_referer_for_download_endpoint(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_get(url: str, headers=None, **kwargs):
        captured.update(headers or {})
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4 test")

    monkeypatch.setattr(httpx, "get", fake_get)
    fetcher = DocumentFetcher(tmp_path, respect_robots=False)
    result = fetcher.fetch(
        "https://x.edu.cn/system/_content/download.jsp?wbfileid=1",
        referer="https://x.edu.cn/info/1007/1758.htm",
    )
    assert not isinstance(result, CrawlError)
    assert captured.get("Referer") == "https://x.edu.cn/info/1007/1758.htm"


def test_policy_classifier_distinguishes_all_required_categories() -> None:
    classifier = PolicyClassifier()
    cases = {
        "competition_policy": ("大学生学科竞赛管理办法", "本办法规定竞赛组织。"),
        "competition_catalog": ("学科竞赛分级目录", "A类 全国大学生数学建模竞赛"),
        "competition_notice": ("关于组织参加大学生数学竞赛的通知", "请报名参赛。"),
        "competition_result": ("大学生数学竞赛获奖结果", "现公布成绩。"),
        "participation_news": ("喜报：我校学生竞赛再创佳绩", "荣获一等奖。"),
        "general_policy": ("学生管理规定", "学生参加学科竞赛按规定办理。"),
        "innovation_credit_policy": ("本科生创新创业学分认定办法", "学科竞赛获奖可认定创新学分。"),
        "second_classroom_policy": ("第二课堂学分实施细则", "学科竞赛纳入第二课堂学分。"),
        "irrelevant": ("优秀学生人物风采", "该生曾参加学科竞赛。"),
    }
    for expected, (title, text) in cases.items():
        assert classifier.classify(title, text).category == expected


def test_recognition_requires_formal_scope_and_named_competition() -> None:
    classifier = PolicyClassifier()
    assert classifier.classify(
        "学科竞赛分级目录",
        "A类 全国大学生数学建模竞赛，纳入学校认定范围。",
    ).recognition_eligible
    assert not classifier.classify(
        "大学生学科竞赛管理办法",
        "学校鼓励学生参加竞赛，并负责竞赛组织。",
    ).recognition_eligible
    assert not classifier.classify(
        "关于参加全国大学生数学建模竞赛的通知",
        "请同学报名。",
    ).recognition_eligible
    assert PolicyRelationExtractor().extract([], "普通政策背景介绍", "general_policy") == []


def test_non_policy_schedules_and_training_plans_are_rejected() -> None:
    classifier = PolicyClassifier()
    schedule = "本周更新学科竞赛目录，涉及挑战杯、互联网+和数学建模竞赛。"
    plan = "第二课堂学分管理办法适用于学生竞赛活动。"

    assert classifier.classify("教务处第8周工作日程安排表", schedule).category == "irrelevant"
    assert classifier.classify("计算机科学与技术专业人才培养方案", plan).category == "irrelevant"


def test_multistage_discovery_reaches_department_policy_and_dynamic_pdf() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=GraphFetcher())
    result = service.discover(
        school="示例大学",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=8,
    )
    urls = {item.url for item in result.documents}
    assert "https://jwc.example.edu.cn/policy.html" in urls
    assert "https://jwc.example.edu.cn/system/_content/download.jsp?owner=1&wbfileid=2" in urls
    assert result.status == "VERIFIED_DATA"


def test_multistage_discovery_preserves_attachment_parent_as_referer() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=GraphFetcher())
    result = service.discover(
        school="Example University",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=8,
    )
    attachment = next(item for item in result.documents if "download.jsp" in item.url)
    assert attachment.source_url == "https://jwc.example.edu.cn/policy.html"


def test_academic_technology_competition_catalog_title_is_policy() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService()
    title = "附件1：河北大学学生课外学术科技竞赛分级目录2024版.pdf"
    category = service.classifier.classify(title, "").category

    assert service._looks_like_policy_document(title, category)

def test_multistage_discovery_keeps_project_catalog_from_notice_page() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=ProjectCatalogNoticeFetcher())
    result = service.discover(
        school="Example University",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=8,
    )
    assert "https://cxcy.example.edu.cn/b-list.pdf" in {item.url for item in result.documents}

def test_multistage_discovery_excludes_navigation_pages_and_unrelated_attachments() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=PolicyListingFetcher())
    result = service.discover(
        school="Example University",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=8,
    )
    assert {item.url for item in result.documents} == {
        "https://cxcy.example.edu.cn/policy.html",
    }

def test_internal_get_search_form_is_expanded_before_external_search() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=SearchFormFetcher())
    result = service.discover(
        school="示例大学",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=5,
    )
    assert "internal_search" in result.channels_attempted
    assert "https://www.example.edu.cn/files/catalog.pdf" in {item.url for item in result.documents}


def test_pdf_search_result_is_discovery_not_off_domain_evidence() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=GraphFetcher())
    result = service.discover(
        school="示例大学",
        official_website="https://www.example.edu.cn/",
        official_domain="example.edu.cn",
        search_results=[
            {"title": "学科竞赛目录", "url": "https://jwc.example.edu.cn/catalog.pdf"},
            {"title": "摘要镜像", "url": "https://search.example.com/cache/catalog.pdf"},
        ],
        max_pages=8,
    )
    assert "https://jwc.example.edu.cn/catalog.pdf" in {item.url for item in result.documents}
    assert all("search.example.com" not in item.url for item in result.documents)


def test_access_limited_is_reserved_for_technical_restrictions() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=BlockedFetcher())
    result = service.discover(
        school="受限大学",
        official_website="https://blocked.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=4,
    )
    assert result.status == "ACCESS_LIMITED"


def test_ssl_timeout_is_access_limited_when_nothing_is_reachable() -> None:
    service = GeneralUndergraduatePolicyDiscoveryService(html_fetcher=TimeoutFetcher())
    result = service.discover(
        school="超时大学",
        official_website="https://timeout.example.edu.cn/",
        official_domain="example.edu.cn",
        max_pages=4,
    )
    assert result.status == "ACCESS_LIMITED"


def test_general_seed_does_not_set_double_first_class(db_session, tmp_path: Path) -> None:
    seed = UniversitySeed(
        name="普通本科测试大学",
        english_name=None,
        short_name=None,
        province="测试省",
        city="测试市",
        official_website="https://ordinary.example.edu.cn/",
        official_domain="example.edu.cn",
        aliases=[],
        is_985=False,
        is_211=False,
        is_double_first_class=False,
    )
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, respect_robots=False)
    university = pipeline._upsert_university(db_session, seed)
    assert university.is_double_first_class is False
