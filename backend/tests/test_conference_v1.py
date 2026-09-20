"""Academic Conference V1 behavior tests.

Covers the ten required behaviors plus migration/API smoke and provenance
guards. Conference seeds are written to tmp_path per test so the shared demo
seed used by other suites is untouched.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    ConferenceEdition,
    ConferenceSeries,
    ConferenceSource,
    University,
)
from app.services.conference_authority_service import (
    authority_status_from_sources,
    can_prove_identity,
    publication_state,
    summarize_indexing_claims,
)
from app.services.conference_seed_import_service import ConferenceSeedImportService


def _write_seed_dir(
    tmp_path: Path,
    *,
    series: list[dict],
    editions: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> Path:
    seed_dir = tmp_path / "conference_v1_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "series_seed.json").write_text(
        json.dumps({"series": series}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "editions_seed.json").write_text(
        json.dumps({"editions": editions or []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "discovery_candidates.json").write_text(
        json.dumps({"candidates": candidates or []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "organizations_catalog.json").write_text(
        json.dumps({"entries": []}, ensure_ascii=False), encoding="utf-8"
    )
    return seed_dir


def _base_series(key: str, name: str, short_name: str, source_level: str) -> dict:
    source_type = {
        "S": "conference_official_site",
        "A": "organizer_official",
        "B": "university_official",
        "C": "third_party_directory",
    }[source_level]
    return {
        "key": key,
        "name": name,
        "english_name": f"English {name}",
        "short_name": short_name,
        "aliases": [short_name],
        "discipline": "computer_science",
        "conference_frequency": "annual",
        "conference_scope": "international",
        "is_international": True,
        "official_website": f"https://{key}.example.org",
        "organizations": [],
        "sources": [
            {
                "source_type": source_type,
                "source_name": f"{name} 来源",
                "source_url": f"https://{key}.example.org/{source_level}",
                "official_domain": f"{key}.example.org",
            }
        ],
    }


# 1. university source cannot verify conference identity
def test_university_source_cannot_verify_conference_identity(db_session, tmp_path) -> None:
    assert can_prove_identity("university_official") is False
    assert can_prove_identity("conference_official_site") is True
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_base_series("b_only", "测试高校来源会议", "BONLY", "B")],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    assert series.authority_status == "pending_verification"
    assert series.verification_status == "pending_verification"
    assert series.is_verified is False
    source = db_session.execute(select(ConferenceSource)).scalars().first()
    assert source.authority_level == "B"
    assert source.is_verified is False


# 1b. third-party source cannot verify identity
def test_third_party_source_cannot_verify_conference_identity(db_session) -> None:
    assert can_prove_identity("third_party_directory") is False
    assert can_prove_identity("commercial_conference_platform") is False
    status = authority_status_from_sources(
        ["third_party_directory", "search_summary"],
        has_any_source=True,
    )
    assert status == "pending_verification"


# 2. series and edition authority are independent
def test_series_and_edition_authority_are_independent(db_session, tmp_path) -> None:
    series_payload = {
        **_base_series("aseries", "权威系列会议", "ASER", "S"),
        "official_website": "https://aseries.example.org",
        "sources": [
            {
                "source_type": "conference_official_site",
                "source_name": "系列官网",
                "source_url": "https://aseries.example.org/",
                "official_domain": "aseries.example.org",
            }
        ],
    }
    editions_payload = [
        {
            "series_key": "aseries",
            "year": 2026,
            "edition_name": "2026 Edition",
            "start_date": "2026-08-01",
            "end_date": "2026-08-03",
            "country_or_region": "中国",
            "city": "北京",
            "edition_official_url": "https://school.example.edu.cn/notice",
            "sources": [
                {
                    "source_type": "university_official",
                    "source_name": "高校通知",
                    "source_url": "https://school.example.edu.cn/notice",
                    "official_domain": "example.edu.cn",
                }
            ],
        }
    ]
    seed_dir = _write_seed_dir(tmp_path, series=[series_payload], editions=editions_payload)
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert series.authority_status == "verified_official"
    assert series.is_verified is True
    assert edition.authority_status == "pending_verification"
    assert edition.is_verified is False


# 3. one series can have multiple editions
def test_one_series_can_have_multiple_editions(db_session) -> None:
    series = ConferenceSeries(
        name="多届系列会议",
        short_name="MULTI",
        discipline="computer_science",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add_all(
        [
            ConferenceEdition(conference_series_id=series.id, year=2025),
            ConferenceEdition(conference_series_id=series.id, year=2026),
            ConferenceEdition(conference_series_id=series.id, year=2027),
        ]
    )
    db_session.commit()
    count = db_session.scalar(
        select(func.count()).select_from(ConferenceEdition).where(
            ConferenceEdition.conference_series_id == series.id
        )
    )
    assert count == 3


# 4. edition deadline does not overwrite another year
def test_edition_deadline_does_not_overwrite_another_year(db_session, tmp_path) -> None:
    series = [_base_series("dl_series", "截止测试系列", "DL", "S")]
    editions = [
        {
            "series_key": "dl_series",
            "year": 2025,
            "edition_name": "2025届",
            "paper_deadline": "2025-02-01",
            "start_date": "2025-06-01",
            "end_date": "2025-06-03",
            "country_or_region": "中国",
            "city": "北京",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://dl.example.org/2025",
                    "official_domain": "dl.example.org",
                }
            ],
        },
        {
            "series_key": "dl_series",
            "year": 2026,
            "edition_name": "2026届",
            "paper_deadline": "2026-05-06",
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "country_or_region": "中国",
            "city": "上海",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://dl.example.org/2026",
                    "official_domain": "dl.example.org",
                }
            ],
        },
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series, editions=editions)
    service = ConferenceSeedImportService()
    service.import_folder(db_session, seed_dir)
    rows = list(db_session.execute(select(ConferenceEdition)).scalars())
    by_year = {row.year: row for row in rows}
    assert by_year[2025].paper_deadline is not None
    assert by_year[2026].paper_deadline is not None
    assert by_year[2025].paper_deadline.date().isoformat() == "2025-02-01"

    # Rerun: updating 2026 rows must not change 2025 rows.
    service.import_folder(db_session, seed_dir)
    by_year = {row.year: row for row in db_session.execute(select(ConferenceEdition)).scalars()}
    assert by_year[2025].paper_deadline.date().isoformat() == "2025-02-01"
    assert by_year[2026].paper_deadline.date().isoformat() == "2026-05-06"


# 5. indexing claim is not equivalent to indexed
def test_indexing_claim_is_not_equivalent_to_indexed() -> None:
    assert summarize_indexing_claims(
        [{"status": "organizer_claimed", "system": "EI", "detail": "拟提交 EI 检索"}]
    ) == "organizer_claimed"
    assert summarize_indexing_claims(
        [{"status": "publisher_confirmed", "system": "Scopus"}]
    ) == "publisher_confirmed"
    assert summarize_indexing_claims(None) == "unknown"
    assert "database_confirmed" in {
        "organizer_claimed",
        "publisher_confirmed",
        "database_confirmed",
        "historical_indexed",
        "unknown",
    }


# 6. planned publication is not equivalent to published
def test_planned_publication_is_not_published() -> None:
    assert publication_state("planned") == "planned"
    assert publication_state("published") == "published"
    assert publication_state("unknown") == "unknown"
    assert publication_state("planned") != "published"


# 7. duplicate acronym does not auto merge
def test_duplicate_acronym_does_not_auto_merge(db_session, tmp_path) -> None:
    series = [
        _base_series("alpha_conf", "Alpha 学术会议", "DUPE", "S"),
        _base_series("beta_conf", "Beta 学术会议", "DUPE", "S"),
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series)
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    names = set(
        db_session.execute(select(ConferenceSeries.name)).scalars().all()
    )
    assert names == {"Alpha 学术会议", "Beta 学术会议"}
    count = db_session.scalar(select(func.count()).select_from(ConferenceSeries))
    assert count == 2


# 8. rerun seed import is idempotent
def test_rerun_seed_import_is_idempotent(db_session, tmp_path) -> None:
    series = [
        {
            **_base_series("idem_conf", "幂等测试会议", "IDEM", "S"),
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://idem.example.org/",
                    "official_domain": "idem.example.org",
                }
            ],
        }
    ]
    editions = [
        {
            "series_key": "idem_conf",
            "year": 2026,
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "country_or_region": "中国",
            "city": "北京",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://idem.example.org/2026",
                    "official_domain": "idem.example.org",
                }
            ],
        }
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series, editions=editions)
    service = ConferenceSeedImportService()
    first = service.import_folder(db_session, seed_dir)
    second = service.import_folder(db_session, seed_dir)
    assert first["series"]["created"] == 1
    assert first["editions"]["created"] == 1
    assert second["series"]["created"] == 0
    assert second["editions"]["created"] == 0
    assert db_session.scalar(select(func.count()).select_from(ConferenceSeries)) == 1
    assert db_session.scalar(select(func.count()).select_from(ConferenceEdition)) == 1


# 9. no fabricated deadline
def test_no_fabricated_deadline(db_session, tmp_path) -> None:
    series = [_base_series("null_dl", "无截止会议", "NODL", "S")]
    editions = [
        {
            "series_key": "null_dl",
            "year": 2026,
            "edition_name": "2026届",
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "country_or_region": "中国",
            "city": "北京",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://nulldl.example.org/2026",
                    "official_domain": "nulldl.example.org",
                }
            ],
        }
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series, editions=editions)
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert edition.paper_deadline is None
    assert edition.registration_deadline is None
    assert edition.abstract_deadline is None


# provenance: B source rows must not be marked identity-verified
def test_source_provenance_flags_b_vs_s(db_session) -> None:
    series = ConferenceSeries(
        name="来源标记测试",
        short_name="PROV",
        discipline="computer_science",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add_all(
        [
            ConferenceSource(
                conference_series_id=series.id,
                source_type="conference_official_site",
                authority_level="S",
                source_url="https://prov.example.org/s",
                is_official=True,
                is_verified=True,
                verification_status="verified_official",
                raw_title="官方公告",
            ),
            ConferenceSource(
                conference_series_id=series.id,
                source_type="university_official",
                authority_level="B",
                source_url="https://school.example.edu.cn/notice",
                is_official=False,
                is_verified=False,
                verification_status="pending_verification",
                raw_title="高校通知",
            ),
            ConferenceSource(
                conference_series_id=series.id,
                source_type="third_party_directory",
                authority_level="C",
                source_url="https://agg.example.com/conf",
                is_official=False,
                is_verified=False,
                verification_status="discovery_only",
                raw_title="聚合站条目",
            ),
        ]
    )
    db_session.commit()
    rows = list(db_session.execute(select(ConferenceSource)).scalars())
    assert len(rows) == 3
    assert sum(1 for row in rows if row.verification_status == "verified_official") == 1
    assert sum(1 for row in rows if row.authority_level == "B" and row.is_verified) == 0
    assert sum(1 for row in rows if row.authority_level == "C" and row.is_verified) == 0


# school relation can only attach to a registered university
def test_school_relation_requires_registered_university(db_session, tmp_path) -> None:
    db_session.add(University(name="会议测试大学", province="湖北", city="武汉"))
    db_session.commit()
    series = [_base_series("school_conf", "高校关系测试会议", "SCH", "S")]
    editions = [
        {
            "series_key": "school_conf",
            "year": 2026,
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "country_or_region": "中国",
            "city": "武汉",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://schoolconf.example.org/2026",
                    "official_domain": "schoolconf.example.org",
                }
            ],
            "school_relations": [
                {
                    "school_name": "会议测试大学",
                    "relation_type": "undertaker",
                    "notice_url": "https://school.example.edu.cn/notice",
                    "source_type": "university_official",
                },
                {
                    "school_name": "不在注册表的高校",
                    "relation_type": "undertaker",
                    "notice_url": "https://other.example.edu.cn/notice",
                    "source_type": "university_official",
                },
                {
                    "school_name": "会议测试大学",
                    "relation_type": "co_undertaker",
                    "notice_url": None,
                    "source_type": "conference_official_site",
                },
            ],
        }
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series, editions=editions)
    stats = ConferenceSeedImportService().import_folder(db_session, seed_dir)
    assert stats["editions"]["school_relations_created"] == 2
    assert stats["editions"]["school_relations_skipped"] == 1
    # Repeat run must stay idempotent for both notice-bearing and notice-less rows.
    stats = ConferenceSeedImportService().import_folder(db_session, seed_dir)
    assert stats["editions"]["school_relations_created"] == 0


# API smoke
def test_conference_api_smoke(client, db_session, tmp_path) -> None:
    series = [_base_series("api_conf", "API 测试会议", "API", "S")]
    editions = [
        {
            "series_key": "api_conf",
            "year": 2026,
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "country_or_region": "中国",
            "city": "北京",
            "sources": [
                {
                    "source_type": "conference_official_site",
                    "source_url": "https://apiconf.example.org/2026",
                    "official_domain": "apiconf.example.org",
                }
            ],
        }
    ]
    seed_dir = _write_seed_dir(tmp_path, series=series, editions=editions)
    ConferenceSeedImportService().import_folder(db_session, seed_dir)

    response = client.get("/api/conferences/summary")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["series_total"] == 1
    assert body["editions_total"] == 1

    response = client.get("/api/conferences/series")
    assert response.status_code == 200
    series_list = response.json()["data"]
    assert len(series_list) == 1
    series_id = series_list[0]["id"]

    response = client.get(f"/api/conferences/series/{series_id}")
    assert response.status_code == 200
    assert len(response.json()["data"]["editions"]) == 1

    response = client.get("/api/conferences/editions?has_dates=true")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/vocabulary")
    assert response.status_code == 200
    assert "indexing_claim_statuses" in response.json()["data"]


# migration smoke: fresh DB upgrade to head exposes conference schema
def test_conference_migration_smoke(tmp_path) -> None:
    db_path = tmp_path / "migration_smoke.sqlite"
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    with sqlite3.connect(db_path) as con:
        tables = {
            row[0]
            for row in con.execute(
                "select name from sqlite_master where type='table'"
            ).fetchall()
        }
    assert {"conference_series", "conference_editions", "school_conferences",
            "conference_sources", "conference_organizations",
            "conference_discovery_candidates"} <= tables
    with sqlite3.connect(db_path) as con:
        version = con.execute("select version_num from alembic_version").fetchone()[0]
    assert version == "202609060005"


def test_conference_source_fields_are_readable(db_session) -> None:
    series = ConferenceSeries(name="证据链测试会议", short_name="EVID", discipline="computer_science")
    db_session.add(series)
    db_session.flush()
    db_session.add(
        ConferenceSource(
            conference_series_id=series.id,
            source_type="conference_official_site",
            authority_level="S",
            source_url="https://evid.example.org/",
            raw_title="Official CFP",
            raw_content="拟提交 EI 检索（官网声明）",
            is_verified=True,
            verification_status="verified_official",
        )
    )
    db_session.commit()
    source = db_session.execute(select(ConferenceSource)).scalars().first()
    assert source.raw_title == "Official CFP"
    assert "拟提交" in (source.raw_content or "")
