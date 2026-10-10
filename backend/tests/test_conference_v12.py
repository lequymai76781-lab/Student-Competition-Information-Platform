"""Academic Conference V1.2 behavior tests.

Covers the eighteen V1.2 targets: multi-opportunity Editions, independent
deadlines, Edition vs Opportunity status separation, audience vocabulary,
historical isolation, discipline uniqueness/dedupe, major alias mapping,
actionable status/date rules, closing_soon, NULL deadline, source evidence,
S/A verification, API backward compatibility, idempotent import and
duplicate prevention.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    ConferenceDisciplineMapping,
    ConferenceEdition,
    ConferenceOpportunity,
    ConferenceSeries,
)
from app.services.conference_authority_service import (
    edition_lifecycle_status,
    opportunity_status,
)
from app.services.conference_seed_import_service import ConferenceSeedImportService
from scripts.build_conference_v1_seeds import _validate_series


def _write_seed_dir(
    tmp_path: Path,
    *,
    series: list[dict] | None = None,
    editions: list[dict] | None = None,
    mappings: list[dict] | None = None,
) -> Path:
    seed_dir = tmp_path / "conference_v12_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "series_seed.json").write_text(
        json.dumps({"series": series or []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "editions_seed.json").write_text(
        json.dumps({"editions": editions or []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "discovery_candidates.json").write_text(
        json.dumps({"candidates": []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "discipline_mappings.json").write_text(
        json.dumps({"mappings": mappings or []}, ensure_ascii=False), encoding="utf-8"
    )
    (seed_dir / "organizations_catalog.json").write_text(
        json.dumps({"entries": []}, ensure_ascii=False), encoding="utf-8"
    )
    return seed_dir


def _series(
    key: str,
    name: str,
    short_name: str,
    *,
    discipline: str = "computer_science",
    extra: dict | None = None,
) -> dict:
    payload = {
        "key": key,
        "name": name,
        "english_name": f"English {name}",
        "short_name": short_name,
        "aliases": [short_name],
        "discipline": discipline,
        "conference_frequency": "annual",
        "conference_scope": "international",
        "is_international": True,
        "official_website": f"https://{key}.example.org",
        "organizations": [],
        "sources": [
            {
                "source_type": "conference_official_site",
                "source_name": f"{name} 来源",
                "source_url": f"https://{key}.example.org",
                "official_domain": f"{key}.example.org",
            }
        ],
    }
    if extra:
        payload.update(extra)
    return payload


def _edition(series_key: str, year: int = 2026, **extra: object) -> dict:
    payload = {
        "series_key": series_key,
        "year": year,
        "edition_name": f"{series_key} {year}",
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "country_or_region": "中国",
        "city": "北京",
        "edition_official_url": f"https://{series_key}.example.org/{year}",
        "sources": [
            {
                "source_type": "conference_official_site",
                "source_name": f"{series_key} {year} 官网",
                "source_url": f"https://{series_key}.example.org/{year}",
                "official_domain": f"{series_key}.example.org",
            }
        ],
    }
    payload.update(extra)
    return payload


def _opportunity(
    series_key: str,
    year: int,
    opportunity_type: str,
    *,
    title: str,
    official_url: str | None = None,
    audience: list[str] | None = None,
    deadline: str | None = None,
    open_date: str | None = None,
    evidence_status: str = "full_page_verified",
    source: dict | None = None,
) -> dict:
    url = official_url or f"https://{series_key}.example.org/{year}/opp/{opportunity_type}"
    return {
        "series_key": series_key,
        "year": year,
        "opportunity_type": opportunity_type,
        "title": title,
        "official_label": title,
        "audience": audience,
        "deadline": deadline,
        "open_date": open_date,
        "official_url": url,
        "evidence": "官方页面记录（测试）。",
        "evidence_status": evidence_status,
        "source": source
        or {
            "source_type": "conference_official_site",
            "source_name": "测试官方来源",
            "source_url": url,
            "official_domain": f"{series_key}.example.org",
        },
    }


# 1/2. 一个 Edition 多个 Opportunity，各自独立 deadline
def test_edition_can_have_multiple_independent_opportunities(
    db_session, tmp_path
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("multi", "多机会会议", "MULTI")],
        editions=[
            _edition(
                "multi",
                opportunities=[
                    _opportunity("multi", 2026, "paper_submission", title="论文", deadline="2026-08-01"),
                    _opportunity("multi", 2026, "poster", title="海报", deadline="2026-10-20"),
                    _opportunity(
                        "multi",
                        2026,
                        "doctoral_consortium",
                        title="博士论坛",
                        audience=["phd"],
                    ),
                ],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    rows = list(db_session.execute(select(ConferenceOpportunity)).scalars())
    assert len(rows) == 3
    deadlines = {row.opportunity_type: row.deadline for row in rows}
    assert deadlines["paper_submission"] is not None
    assert deadlines["poster"] is not None
    assert deadlines["paper_submission"] != deadlines["poster"]


# 3/4. Paper closed 不关闭 Edition；Poster open 保持 actionable
def test_paper_closed_does_not_close_edition_and_poster_open_keeps_actionable(
    db_session, tmp_path
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("status", "状态分离会议", "STATUS")],
        editions=[
            _edition(
                "status",
                opportunities=[
                    _opportunity("status", 2026, "paper_submission", title="论文", deadline="2026-08-01"),
                    _opportunity("status", 2026, "poster", title="海报", deadline="2026-10-20"),
                ],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    rows = list(db_session.execute(select(ConferenceOpportunity)).scalars())
    paper = next(r for r in rows if r.opportunity_type == "paper_submission")
    poster = next(r for r in rows if r.opportunity_type == "poster")
    # The independent opportunity example is observed before the 14-day
    # closing-soon window; it must not depend on the machine's calendar date.
    observed_on = date(2026, 9, 1)
    assert opportunity_status(paper, edition=edition, today=observed_on) == "closed"
    assert opportunity_status(poster, edition=edition, today=observed_on) == "open"
    assert edition_lifecycle_status(edition, today=observed_on) == "upcoming"


# 5/6. Audience 受控且不扩散
def test_opportunity_audience_vocabulary_and_generic_student(
    db_session, tmp_path
) -> None:
    with pytest.raises(ValueError):
        ConferenceSeedImportService().import_folder(
            db_session,
            _write_seed_dir(
                tmp_path,
                series=[_series("aud", "受众会议", "AUD")],
                editions=[
                    _edition(
                        "aud",
                        opportunities=[
                            _opportunity(
                                "aud",
                                2026,
                                "student_forum",
                                title="学生论坛",
                                audience=["freshman"],  # 非法受众
                            )
                        ],
                    )
                ],
            ),
        )
    db_session.rollback()

    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("aud", "受众会议", "AUD")],
        editions=[
            _edition(
                "aud",
                opportunities=[
                    _opportunity(
                        "aud",
                        2026,
                        "student_forum",
                        title="学生论坛",
                        audience=["student"],
                    )
                ],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    row = db_session.execute(select(ConferenceOpportunity)).scalars().first()
    assert row.audience == ["student"]
    assert "undergraduate" not in row.audience
    assert "master" not in row.audience


# 7. 历史机会不传播到新 Edition
def test_historical_opportunity_does_not_flow_to_new_edition(
    db_session, tmp_path
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("past", "历史机会会议", "PAST")],
        editions=[
            _edition(
                "past",
                year=2025,
                start_date="2025-08-01",
                end_date="2025-08-03",
                opportunities=[
                    _opportunity(
                        "past",
                        2025,
                        "doctoral_consortium",
                        title="博士论坛",
                        audience=["phd"],
                    )
                ],
            ),
            _edition("past", year=2026),
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    by_year = {
        edition.year: edition
        for edition in db_session.execute(select(ConferenceEdition)).scalars()
    }
    old = by_year[2025]
    new = by_year[2026]
    old_opps = list(
        db_session.execute(
            select(ConferenceOpportunity).where(
                ConferenceOpportunity.conference_edition_id == old.id
            )
        ).scalars()
    )
    new_opps = list(
        db_session.execute(
            select(ConferenceOpportunity).where(
                ConferenceOpportunity.conference_edition_id == new.id
            )
        ).scalars()
    )
    assert len(old_opps) == 1
    assert new_opps == []


# 8/9. primary/secondary discipline
def test_primary_and_secondary_discipline_rules() -> None:
    valid = {
        "key": "d1",
        "name": "会议",
        "english_name": "Conf",
        "short_name": "D1",
        "discipline": "journalism_communication",
        "secondary_disciplines": ["data_science"],
        "conference_frequency": "annual",
        "conference_scope": "international",
        "is_international": True,
        "official_website": "https://d1.example.org",
        "organizations": [],
        "sources": [],
    }
    _validate_series([valid])
    bad_primary = {**valid, "key": "d2", "secondary_disciplines": ["journalism_communication"]}
    with pytest.raises(AssertionError):
        _validate_series([bad_primary])
    bad_dup = {**valid, "key": "d3", "secondary_disciplines": ["data_science", "data_science"]}
    with pytest.raises(AssertionError):
        _validate_series([bad_dup])


# 10. Major alias 映射
def test_major_alias_mapping(db_session, tmp_path, client) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        mappings=[
            {
                "major_alias": "新闻学",
                "discipline": "journalism_communication",
                "relationship_type": "direct",
                "mapping_basis": "专业目录对照",
                "evidence": "测试映射",
                "status": "active",
            },
            {
                "major_alias": "数据新闻",
                "discipline": "data_science",
                "relationship_type": "interdisciplinary",
                "mapping_basis": "专业目录对照",
                "evidence": "测试映射",
                "status": "active",
            },
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    rows = list(db_session.execute(select(ConferenceDisciplineMapping)).scalars())
    assert len(rows) == 2
    response = client.get("/api/conferences/discipline-mappings?major_alias=新闻学")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1


# 11/12/13. opportunity status / closing_soon / NULL deadline
def test_opportunity_status_date_calculation() -> None:
    today = date(2026, 9, 6)
    assert (
        opportunity_status(
            {"deadline": "2026-09-10"}, edition={"end_date": "2026-10-01"}, today=today
        )
        == "closing_soon"
    )
    assert (
        opportunity_status(
            {"deadline": "2026-10-20"}, edition={"end_date": "2026-11-01"}, today=today
        )
        == "open"
    )
    assert (
        opportunity_status(
            {"deadline": "2026-08-01"}, edition={"end_date": "2026-11-01"}, today=today
        )
        == "closed"
    )
    assert (
        opportunity_status(
            {"open_date": "2026-10-01"},
            edition={"end_date": "2026-11-01"},
            today=today,
        )
        == "upcoming"
    )
    assert (
        opportunity_status(
            {}, edition={"end_date": "2026-01-01"}, today=today
        )
        == "held"
    )
    assert opportunity_status({}, edition={}, today=today) == "unknown"


# 14. source evidence 要求
def test_opportunity_source_evidence_required(db_session, tmp_path) -> None:
    missing_url = {
        "series_key": "src",
        "year": 2026,
        "opportunity_type": "poster",
        "title": "无链接海报",
        "official_url": None,
        "audience": ["student"],
        "evidence_status": "full_page_verified",
    }
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("src", "来源会议", "SRC")],
        editions=[_edition("src", opportunities=[missing_url])],
    )
    with pytest.raises(ValueError):
        ConferenceSeedImportService().import_folder(db_session, seed_dir)
    db_session.rollback()


# 15. S/A 才能 verified
def test_only_sa_sources_verify_opportunity(db_session, tmp_path) -> None:
    b_source = {
        "source_type": "university_official",
        "source_name": "高校页",
        "source_url": "https://univ.example.edu.cn/opp",
        "official_domain": "univ.example.edu.cn",
    }
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("verify", "验证会议", "VER")],
        editions=[
            _edition(
                "verify",
                opportunities=[
                    _opportunity(
                        "verify",
                        2026,
                        "poster",
                        title="B 级海报",
                        official_url="https://univ.example.edu.cn/opp",
                        source=b_source,
                    ),
                    _opportunity(
                        "verify",
                        2026,
                        "paper_submission",
                        title="S 级论文",
                        official_url="https://verify.example.org/2026/paper",
                    ),
                ],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    rows = {
        row.opportunity_type: row
        for row in db_session.execute(select(ConferenceOpportunity)).scalars()
    }
    assert rows["poster"].is_verified is False
    assert rows["poster"].verification_status == "pending_verification"
    assert rows["paper_submission"].is_verified is True
    assert rows["paper_submission"].verification_status == "verified_official"


# 16. API 向后兼容 + 新端点
def test_api_backward_compatible_and_opportunity_endpoint(
    db_session, tmp_path, client
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("api", "API 会议", "API")],
        editions=[
            _edition(
                "api",
                year=2026,
                start_date="2026-11-01",
                end_date="2026-11-03",
                opportunities=[
                    _opportunity("api", 2026, "poster", title="海报", deadline="2026-10-20"),
                ],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    assert client.get("/api/conferences/series").status_code == 200
    assert client.get("/api/conferences/editions?year=2026").status_code == 200
    assert client.get("/api/conferences/editions?has_opportunity=true").status_code == 200
    assert (
        client.get("/api/conferences/editions?year=2026&actionable=true").json()["meta"][
            "total"
        ]
        == 1
    )
    opp_response = client.get("/api/conferences/opportunities?opportunity_type=poster")
    assert opp_response.status_code == 200
    assert opp_response.json()["meta"]["total"] == 1
    actionable = client.get("/api/conferences/actionable?year=2026")
    assert actionable.status_code == 200
    summary = client.get("/api/conferences/actionable-summary?year=2026")
    assert summary.status_code == 200
    assert summary.json()["data"]["current_actionable_opportunities"] == 1


# 17/18. 幂等导入与防重
def test_opportunity_import_idempotent_and_dedup(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("idem", "幂等机会会议", "IDEM")],
        editions=[
            _edition(
                "idem",
                opportunities=[
                    _opportunity("idem", 2026, "poster", title="海报"),
                    _opportunity("idem", 2026, "poster", title="海报(同类型同链接)"),
                ],
            )
        ],
    )
    service = ConferenceSeedImportService()
    service.import_folder(db_session, seed_dir)
    assert (
        db_session.scalar(select(func.count()).select_from(ConferenceOpportunity)) == 1
    )
    service.import_folder(db_session, seed_dir)
    assert (
        db_session.scalar(select(func.count()).select_from(ConferenceOpportunity)) == 1
    )
    row = db_session.execute(select(ConferenceOpportunity)).scalars().first()
    assert row.title == "海报(同类型同链接)" or row.title == "海报"
