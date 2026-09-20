from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from app.crawler.discovery.general_undergraduate_policy_discovery import (
    DiscoveredPolicy,
    GeneralPolicyDiscoveryResult,
)
from app.crawler.fetchers.html_fetcher import FetchResult
from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline
from app.models import PolicyDocument, University, UniversityPolicy
from scripts.run_general_undergraduate_policy_pipeline import run_school


def _add_policy_document(
    db_session,
    *,
    university: University,
    title: str,
    source_url: str,
    attachment_url: str | None = None,
    content_text: str = "已审核政策正文",
    year: int = 2026,
) -> PolicyDocument:
    document = PolicyDocument(
        university_id=university.id,
        scope_type="university",
        title=title,
        policy_type="competition_policy",
        year=year,
        latest_available_year=year,
        publisher=university.name,
        source_url=source_url,
        attachment_url=attachment_url,
        official_domain="example.edu.cn",
        authority_level="A1",
        published_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        effective_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
        content_text=content_text,
        document_hash=sha256(f"{university.id}|{source_url}".encode()).hexdigest(),
        is_current=True,
        is_verified=True,
        verification_status="official_domain_verified",
        parser_type="html",
        source_type="university",
        is_demo=False,
    )
    db_session.add(document)
    db_session.commit()
    return document


def _add_university(db_session, name: str, *, is_985: bool = False, is_211: bool = False) -> University:
    university = University(
        name=name,
        province="测试省",
        city="测试市",
        official_website="https://example.edu.cn/",
        official_domain="example.edu.cn",
        is_985=is_985,
        is_211=is_211,
        is_double_first_class=is_211,
        is_demo=False,
    )
    db_session.add(university)
    db_session.flush()
    return university


def test_university_policy_api_returns_reviewed_canonical_document(client, db_session) -> None:
    university = _add_university(db_session, "普通本科已审核政策测试大学")
    document = _add_policy_document(
        db_session,
        university=university,
        title="普通本科学生学科竞赛管理办法",
        source_url="https://example.edu.cn/policies/ordinary.html",
    )

    response = client.get(f"/api/universities/{university.id}/policies")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [document.id]
    assert rows[0]["policy_name"] == "普通本科学生学科竞赛管理办法"


def test_general_undergraduate_runner_output_is_queryable_from_university_api(
    client,
    db_session,
    tmp_path: Path,
) -> None:
    school = {
        "school": "普通本科生产链测试大学",
        "province": "测试省",
        "official_website": "https://ordinary.example.edu.cn/",
        "official_domain": "ordinary.example.edu.cn",
    }

    class StubDiscovery:
        def discover(self, **_kwargs):
            return GeneralPolicyDiscoveryResult(
                school=school["school"],
                official_domain=school["official_domain"],
                status="VERIFIED_DATA",
                documents=[
                    DiscoveredPolicy(
                        "https://ordinary.example.edu.cn/policy.html",
                        "2026年学生学科竞赛管理办法",
                        "https://ordinary.example.edu.cn/jwc/",
                        "internal_search",
                        "html",
                    )
                ],
            )

    class StubHtmlFetcher:
        def fetch(self, url: str) -> FetchResult:
            html = """
            <html><head><title>2026年学生学科竞赛管理办法</title></head>
            <body>本办法规定大学生学科竞赛的认定、奖励与创新学分管理。</body></html>
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

    pipeline = UniversityPolicyPipeline(
        storage_root=tmp_path,
        respect_robots=False,
        html_fetcher=StubHtmlFetcher(),
    )
    result = run_school(
        db_session,
        school=school,
        search_results=[],
        discovery=StubDiscovery(),
        pipeline=pipeline,
    )
    university = db_session.query(University).filter(University.name == school["school"]).one()

    response = client.get(f"/api/universities/{university.id}/policies")

    assert result["crawl"]["policies_found"] == 1
    assert response.status_code == 200
    assert [row["source_url"] for row in response.json()["data"]] == [
        "https://ordinary.example.edu.cn/policy.html"
    ]


def test_985_policy_document_remains_queryable_from_university_api(client, db_session) -> None:
    university = _add_university(db_session, "985兼容测试大学", is_985=True, is_211=True)
    document = _add_policy_document(
        db_session,
        university=university,
        title="985高校本科生竞赛认定目录",
        source_url="https://example.edu.cn/policies/985.html",
        year=2025,
    )

    response = client.get(f"/api/universities/{university.id}/policies")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["data"]] == [document.id]


def test_university_policy_api_preserves_frontend_contract(client, db_session) -> None:
    university = _add_university(db_session, "前端契约测试大学")
    _add_policy_document(
        db_session,
        university=university,
        title="前端契约政策",
        source_url="https://example.edu.cn/policies/contract.html",
        attachment_url="https://example.edu.cn/files/contract.pdf",
        content_text="供前端展示的政策正文",
    )

    response = client.get(f"/api/universities/{university.id}/policies")

    row = response.json()["data"][0]
    assert set(row) == {
        "id",
        "university_id",
        "policy_name",
        "policy_type",
        "year",
        "source_url",
        "official_file_url",
        "published_at",
        "effective_date",
        "content",
        "is_verified",
        "is_demo",
    }
    assert row["policy_name"] == "前端契约政策"
    assert row["official_file_url"] == "https://example.edu.cn/files/contract.pdf"
    assert row["effective_date"].startswith("2026-04-01T00:00:00")
    assert row["content"] == "供前端展示的政策正文"
    assert row["is_verified"] is True
    assert row["is_demo"] is False


def test_legacy_shadow_row_does_not_duplicate_or_override_canonical_policy(client, db_session) -> None:
    university = _add_university(db_session, "双表去重测试大学")
    document = _add_policy_document(
        db_session,
        university=university,
        title="同一学生竞赛政策",
        source_url="https://example.edu.cn/policies/same.html",
        content_text="canonical body",
    )
    db_session.add(
        UniversityPolicy(
            university_id=university.id,
            policy_name="同一学生竞赛政策",
            policy_type="competition_policy",
            year=2026,
            source_url="https://example.edu.cn/policies/same.html",
            content="legacy body",
            is_verified=True,
            is_demo=False,
        )
    )
    db_session.commit()

    response = client.get(f"/api/universities/{university.id}/policies")

    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["id"] == document.id
    assert rows[0]["content"] == "canonical body"
