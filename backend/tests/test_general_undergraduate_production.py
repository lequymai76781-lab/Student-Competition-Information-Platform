from argparse import Namespace
import json
from pathlib import Path

from app.crawler.base import CrawlError, CrawlerRunResult
from app.crawler.discovery.general_undergraduate_policy_discovery import (
    DiscoveredPolicy,
    GeneralPolicyDiscoveryResult,
)
from app.crawler.discovery.university_discovery import UniversitySeed
from app.crawler.pipelines.university_policy_pipeline import UniversityPolicyPipeline
from scripts.run_general_undergraduate_policy_pipeline import build_seed, run_school
import scripts.run_general_undergraduate_policy_pipeline as production_runner
import scripts.verify_general_undergraduate_production_gold as production_verifier


def _seed() -> UniversitySeed:
    return UniversitySeed(
        name="测试大学",
        english_name=None,
        short_name=None,
        province="",
        city="",
        official_website="https://school.edu.cn/",
        official_domain="school.edu.cn",
        aliases=[],
        is_985=False,
        is_211=False,
        is_double_first_class=False,
    )


def test_run_university_from_discovered_dedupes_skips_off_domain_and_passes_referer(db_session, tmp_path: Path) -> None:
    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, respect_robots=False)
    calls: list[tuple[str, str | None]] = []

    def fake_fetch(url: str, referer: str | None = None):
        calls.append((url, referer))
        return CrawlError(url=url, message="stop", retryable=False)

    pipeline.document_fetcher.fetch = fake_fetch
    docs = [
        DiscoveredPolicy("https://school.edu.cn/a.pdf", "A", "https://school.edu.cn/page.htm", "downloads_attachments", "pdf"),
        DiscoveredPolicy("https://school.edu.cn/a.pdf", "A dup", "https://school.edu.cn/page.htm", "downloads_attachments", "pdf"),
        DiscoveredPolicy("https://evil.com/x.pdf", "off", "https://school.edu.cn/", "external_site_search", "pdf"),
    ]
    result = pipeline.run_university_from_discovered(db_session, _seed(), docs, dry_run=True)
    assert [url for url, _ in calls] == ["https://school.edu.cn/a.pdf"]
    assert calls[0][1] == "https://school.edu.cn/page.htm"
    assert result.target_name == "测试大学"


def test_run_university_keeps_one_hop_discovery(db_session, tmp_path: Path, monkeypatch) -> None:
    from app.crawler.discovery.policy_discovery import PolicyDiscoveryService
    from app.crawler.fetchers.html_fetcher import FetchResult

    captured: list[int] = []

    def fake_discover(self, links, domain):
        captured.append(len(links))
        return []

    monkeypatch.setattr(PolicyDiscoveryService, "discover", fake_discover)

    pipeline = UniversityPolicyPipeline(storage_root=tmp_path, respect_robots=False)

    def fake_fetch(url: str) -> FetchResult:
        html = '<html><title>政策</title><a href="https://school.edu.cn/jwc">教务处</a></html>'
        return FetchResult(
            url=url,
            status_code=200,
            final_url=url,
            content=html.encode("utf-8"),
            text=html,
            content_type="text/html",
            content_hash="h",
        )

    pipeline.html_fetcher.fetch = fake_fetch
    pipeline.run_university(db_session, _seed(), dry_run=True)
    assert captured == [1]


def test_run_school_wires_discovery_to_pipeline(db_session) -> None:
    class StubDiscovery:
        def discover(self, **kwargs):
            self.kwargs = kwargs
            return GeneralPolicyDiscoveryResult(
                school="测试大学",
                official_domain="school.edu.cn",
                status="VERIFIED_DATA",
                documents=[
                    DiscoveredPolicy("https://school.edu.cn/a.pdf", "A", "https://school.edu.cn/page.htm", "downloads_attachments", "pdf"),
                ],
            )

    class StubPipeline:
        def run_university_from_discovered(self, db, seed, documents, **kwargs):
            self.seed = seed
            self.documents = documents
            return CrawlerRunResult(target_name=seed.name, target_url=seed.official_website)

    discovery = StubDiscovery()
    pipeline = StubPipeline()
    school = {
        "school": "测试大学",
        "province": "x",
        "official_website": "https://school.edu.cn/",
        "official_domain": "school.edu.cn",
    }
    search = [{"url": "https://school.edu.cn/a.pdf", "title": "A"}]
    result = run_school(db_session, school=school, search_results=search, discovery=discovery, pipeline=pipeline)

    assert discovery.kwargs["search_results"] == search
    assert pipeline.seed.name == "测试大学"
    assert len(pipeline.documents) == 1
    assert result["school"] == "测试大学"
    assert result["discovery_status"] == "VERIFIED_DATA"


def test_build_seed_sets_ordinary_undergraduate_flags() -> None:
    seed = build_seed({
        "school": "普通大学",
        "province": "??",
        "official_website": "https://u.edu.cn/",
        "official_domain": "u.edu.cn",
    })
    assert seed.is_985 is False
    assert seed.is_211 is False
    assert seed.is_double_first_class is False
    assert seed.official_domain == "u.edu.cn"


def test_master_source_never_selects_general_b(tmp_path: Path, monkeypatch) -> None:
    master = tmp_path / "master.json"
    master.write_text(json.dumps({
        "institutions": [
            {
                "name": "General A University",
                "province": "A",
                "official_url": "https://a.edu.cn/",
                "collection_batch": "general_a",
            },
            {
                "name": "General B University",
                "province": "B",
                "official_url": "https://b.edu.cn/",
                "collection_batch": "general_b",
            },
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(production_runner, "MASTER", master)

    rows = production_runner.load_master_schools(limit=None, names=None)

    assert [row["school"] for row in rows] == ["General A University"]


def test_write_mode_skips_general_b_gold_rows() -> None:
    rows = [
        {"school": "General A University", "collection_batch": "general_a"},
        {"school": "General B University", "collection_batch": "general_b"},
    ]

    selected, skipped = production_runner.select_run_schools(rows, dry_run=False)

    assert [row["school"] for row in selected] == ["General A University"]
    assert [row["school"] for row in skipped] == ["General B University"]

def test_verifier_defaults_to_general_a_gold_scope(tmp_path: Path, monkeypatch) -> None:
    gold = tmp_path / "gold.json"
    master = tmp_path / "master.json"
    gold.write_text(json.dumps({
        "schools": [
            {"school": "General A University", "expected_evidence": []},
            {"school": "General B University", "expected_evidence": []},
        ]
    }), encoding="utf-8")
    master.write_text(json.dumps({
        "institutions": [
            {"name": "General A University", "collection_batch": "general_a"},
            {"name": "General B University", "collection_batch": "general_b"},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(production_verifier, "GOLD", gold)
    monkeypatch.setattr(production_verifier, "MASTER", master)

    schools = production_verifier.load_gold_schools(scope="general_a")

    assert [row["school"] for row in schools] == ["General A University"]

def test_partial_or_dry_run_does_not_overwrite_canonical_report() -> None:
    canonical_report, canonical_checkpoint = production_runner.report_paths(
        Namespace(source="gold", names=None, dry_run=False)
    )
    partial_report, partial_checkpoint = production_runner.report_paths(
        Namespace(source="gold", names=["Example University"], dry_run=False)
    )
    dry_report, dry_checkpoint = production_runner.report_paths(
        Namespace(source="gold", names=None, dry_run=True)
    )

    assert canonical_report == production_runner.REPORT
    assert canonical_checkpoint == production_runner.CHECKPOINT
    assert partial_report != production_runner.REPORT
    assert partial_checkpoint != production_runner.CHECKPOINT
    assert dry_report != production_runner.REPORT
    assert dry_checkpoint != production_runner.CHECKPOINT