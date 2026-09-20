from hashlib import sha256
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawler.base import CrawlError, CrawlerRunResult, DiscoveredLink
from app.crawler.discovery.policy_discovery import PolicyDiscoveryService
from app.crawler.discovery.university_discovery import UniversitySeed
from app.crawler.fetchers.html_fetcher import FetchResult
from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline
from app.models import CompetitionPolicyRecognition, CrawlerJob, PolicyDocument, ReviewQueue, University
from scripts.seed_demo_data import seed_universities


class FakeHtmlFetcher:
    def fetch(self, url: str) -> FetchResult | CrawlError:
        if "bad.example.edu.cn" in url:
            return CrawlError(url=url, message="network unavailable", retryable=True)
        if url.endswith("policy2026.html"):
            html = """
            <html><head><title>2026推免竞赛目录</title></head>
            <body>测试计算机设计大赛列入竞赛目录，获奖可计入推免综合评价加分。</body></html>
            """
        else:
            html = """
            <html><head><title>测试大学</title></head>
            <body><a href="/policy2026.html">2026推免竞赛目录</a></body></html>
            """
        content = html.encode("utf-8")
        return FetchResult(
            url=url,
            status_code=200,
            final_url=url,
            content=content,
            text=html,
            content_type="text/html",
            content_hash=sha256(content).hexdigest(),
        )


def _seed(name: str, domain: str) -> UniversitySeed:
    return UniversitySeed(
        name=name,
        english_name=None,
        short_name=name[:2],
        province="测试省",
        city="测试市",
        official_website=f"https://{domain}/",
        official_domain=domain,
        aliases=[],
        is_985=True,
        is_211=True,
    )


def test_pipeline_failure_is_nonfatal_for_batch(db_session: Session, tmp_path: Path) -> None:
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, html_fetcher=FakeHtmlFetcher())
    results = pipeline.run_batch(
        db_session,
        [_seed("好大学", "good.example.edu.cn"), _seed("坏大学", "bad.example.edu.cn")],
        max_pages_per_university=1,
    )

    assert [result.status for result in results] == ["completed", "failed"]
    assert db_session.scalar(select(func.count()).select_from(CrawlerJob)) == 2
    assert db_session.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))) == 1
    assert (
        db_session.scalar(
            select(func.count()).select_from(CompetitionPolicyRecognition).where(CompetitionPolicyRecognition.is_demo.is_(False))
        )
        == 1
    )
    assert db_session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.reason == "homepage_fetch_failed")) == 1
    assert results[1].review_items == 1


def test_policy_discovery_requires_policy_semantics() -> None:
    links = [
        DiscoveredLink(
            url="https://www.example.edu.cn/news/2026-opening.html",
            text="2026级研究生开学典礼举行",
            source_url="https://www.example.edu.cn",
        ),
        DiscoveredLink(
            url="https://www.example.edu.cn/research-achievements.html",
            text="科研成果",
            source_url="https://www.example.edu.cn",
        ),
        DiscoveredLink(
            url="https://www.example.edu.cn/policy/2026-recommendation.html",
            text="2026年推荐免试实施细则",
            source_url="https://www.example.edu.cn",
        ),
    ]

    discovered = PolicyDiscoveryService().discover(links, "example.edu.cn")

    assert [item.url for item in discovered] == ["https://www.example.edu.cn/policy/2026-recommendation.html"]


def test_low_confidence_candidate_is_reviewed_not_persisted(db_session: Session, tmp_path: Path) -> None:
    university = db_session.execute(select(University)).scalars().first()
    assert university is not None
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, html_fetcher=FakeHtmlFetcher())
    result = CrawlerRunResult(target_name=university.name, target_url="https://example.edu.cn")

    document = pipeline._persist_policy_document(
        db_session,
        university=university,
        title="科研成果-测试大学",
        source_url="https://example.edu.cn/research-achievements.html",
        attachment_url=None,
        original_filename=None,
        official_domain="example.edu.cn",
        content_text="展示学校近期科研成果与科研平台。",
        content_markdown="展示学校近期科研成果与科研平台。",
        document_hash=sha256("research achievements".encode("utf-8")).hexdigest(),
        parser_type="html",
        source_type="university",
        crawler_job_id=None,
        review_result=result,
        dry_run=False,
    )

    assert document is None
    assert result.review_items == 1
    db_session.flush()
    assert db_session.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))) == 0
    assert db_session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.reason == "low_policy_confidence")) == 1


def test_policy_document_dedupes_by_url_and_hash(db_session: Session, tmp_path: Path) -> None:
    university = db_session.execute(select(University)).scalars().first()
    assert university is not None
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, html_fetcher=FakeHtmlFetcher())
    digest = sha256("same policy".encode("utf-8")).hexdigest()

    first = pipeline._persist_policy_document(
        db_session,
        university=university,
        title="2026推免竞赛目录",
        source_url="https://example.edu.cn/policy.html",
        attachment_url=None,
        original_filename=None,
        official_domain="example.edu.cn",
        content_text="same policy",
        content_markdown="same policy",
        document_hash=digest,
        parser_type="html",
        source_type="university",
        crawler_job_id=None,
        dry_run=False,
    )
    second = pipeline._persist_policy_document(
        db_session,
        university=university,
        title="2026推免竞赛目录重复镜像",
        source_url="https://mirror.example.edu.cn/policy.html",
        attachment_url=None,
        original_filename=None,
        official_domain="example.edu.cn",
        content_text="same policy",
        content_markdown="same policy",
        document_hash=digest,
        parser_type="html",
        source_type="university",
        crawler_job_id=None,
        dry_run=False,
    )

    assert first is not None and second is not None
    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(PolicyDocument).where(PolicyDocument.document_hash == digest)) == 1


def test_demo_seed_does_not_overwrite_existing_real_university(db_session: Session) -> None:
    real = University(
        name="武汉大学",
        short_name="武大",
        official_website="https://www.whu.edu.cn",
        official_domain="whu.edu.cn",
        is_985=True,
        is_211=True,
        is_double_first_class=True,
        is_demo=False,
    )
    db_session.add(real)
    db_session.flush()

    seed_universities(db_session)
    db_session.flush()

    assert real.official_domain == "whu.edu.cn"
    assert real.is_demo is False
