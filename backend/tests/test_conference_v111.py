"""Academic Conference V1.1.1 behavior tests.

Covers the ten V1.1.1 test targets: Series->Edition tag isolation,
historical-student-track isolation, recognition evidence status, primary
discipline uniqueness, secondary-discipline duplication, SchoolConference
evidence, pending Edition visibility, NULL-deadline status, actionable
conference judgement and 2026 Edition date-status calculation.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    ConferenceEdition,
    ConferenceSeries,
    SchoolConference,
)
from app.services.conference_authority_service import (
    edition_actionable_status,
    edition_has_actionable_official_info,
    recognition_has_evidence,
    student_opportunity_tags,
)
from app.services.conference_seed_import_service import ConferenceSeedImportService
from scripts.build_conference_v1_seeds import (
    _validate_recognition_evidence,
    _validate_series,
)


def _write_seed_dir(
    tmp_path: Path,
    *,
    series: list[dict] | None = None,
    editions: list[dict] | None = None,
) -> Path:
    seed_dir = tmp_path / "conference_v111_seed"
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
    (seed_dir / "organizations_catalog.json").write_text(
        json.dumps({"entries": []}, ensure_ascii=False), encoding="utf-8"
    )
    return seed_dir


def _series(
    key: str,
    name: str,
    short_name: str,
    *,
    discipline: str = "journalism_communication",
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
        "conference_scope": "national",
        "is_international": False,
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
        "start_date": "2026-08-01",
        "end_date": "2026-08-03",
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


def _validate_series_payload(
    key: str,
    *,
    discipline: str = "journalism_communication",
    secondaries: list[str] | None = None,
) -> dict:
    payload = {
        "key": key,
        "name": f"会议{key}",
        "english_name": f"English {key}",
        "short_name": key.upper(),
        "discipline": discipline,
        "conference_frequency": "annual",
        "conference_scope": "international",
        "is_international": True,
        "official_website": f"https://{key}.example.org",
        "organizations": [],
        "sources": [],
    }
    if secondaries is not None:
        payload["secondary_disciplines"] = secondaries
    return payload


# ---------------------- 1. Series 学生标签不自动传播到 Edition
def test_series_student_tags_do_not_propagate_to_edition(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[
            _series(
                "stag",
                "系列级学生价值会议",
                "STAG",
                extra={"student_value_tags": ["graduate_friendly"]},
            )
        ],
        editions=[_edition("stag")],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert "graduate_friendly" in (series.student_value_tags or [])
    assert edition.student_value_tags is None or edition.student_value_tags == []
    assert "graduate_friendly" not in (edition.student_value_tags or [])


# ---------------------- 2. 历史 Student Track 不自动传播到新 Edition
def test_historical_student_track_does_not_flow_to_new_edition(
    db_session, tmp_path
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("hist", "历史学生会议", "HIST")],
        editions=[
            _edition(
                "hist",
                year=2025,
                start_date="2025-06-01",
                end_date="2025-06-03",
                student_value_tags=["doctoral_consortium"],
            ),
            _edition("hist", year=2026),
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    rows = list(
        db_session.execute(
            select(ConferenceEdition).order_by(ConferenceEdition.year)
        ).scalars()
    )
    old, new = rows
    assert "doctoral_consortium" in (old.student_value_tags or [])
    assert "doctoral_consortium" not in (new.student_value_tags or [])


# ---------------------- 3. recognition 必须保留 evidence 状态
def test_recognition_records_keep_evidence_status() -> None:
    missing = [
        {
            "key": "missing",
            "external_classifications": [
                {"system": "CCF", "level": "A", "version_year": 2022}
            ],
        }
    ]
    with pytest.raises(AssertionError):
        _validate_recognition_evidence(missing)

    with_evidence = [
        {
            "key": "evidenced",
            "external_classifications": [
                {
                    "system": "CCF",
                    "level": "B",
                    "version_year": 2022,
                    "source_url": "https://www.ccf.org.cn/Academic_Evaluation/",
                    "evidence": "CCF 2022 版目录官方公告。",
                    "evidence_status": "legacy",
                }
            ],
        }
    ]
    assert _validate_recognition_evidence(with_evidence) == 1
    assert recognition_has_evidence(with_evidence[0]["external_classifications"][0])
    assert recognition_has_evidence(
        {"system": "CCF", "level": "A", "version_year": 2022}
    ) is False


# ---------------------- 4. primary discipline 唯一
def test_primary_discipline_is_single_and_never_repeated() -> None:
    # A valid single-primary Series passes.
    _validate_series([_validate_series_payload("only")])
    # The primary must not reappear inside a secondary list.
    bad = _validate_series_payload(
        "dup", secondaries=["journalism_communication", "education"]
    )
    with pytest.raises(AssertionError):
        _validate_series([bad])


# ---------------------- 5. secondary discipline 不重复
def test_secondary_disciplines_never_duplicate_each_other() -> None:
    bad = _validate_series_payload(
        "dupes", secondaries=["education", "education"]
    )
    with pytest.raises(AssertionError):
        _validate_series([bad])
    ok = _validate_series_payload(
        "ok", secondaries=["education", "sports_science"]
    )
    _validate_series([ok])


# ---------------------- 6. SchoolConference 关系必须有证据
def test_school_relation_requires_evidence(db_session, tmp_path) -> None:
    no_evidence = _edition(
        "school",
        sources=[],
        school_relations=[
            {
                "school_name": "测试大学",
                "relation_type": "host",
                "source_type": "university_official",
                "notes": "没有任何 notice_url 或 Edition S/A 来源。",
            }
        ],
    )
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("school", "高校关系测试会议", "SCH")],
        editions=[no_evidence],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    assert (
        db_session.scalar(select(func.count()).select_from(SchoolConference)) == 0
    )

    with_evidence = _edition(
        "school",
        school_relations=[
            {
                "school_name": "测试大学",
                "relation_type": "host",
                "source_type": "university_official",
                "notice_url": "https://univ.example.edu.cn/notice/2026",
                "source_name": "测试大学官网通知",
            }
        ],
    )
    seed_dir2 = _write_seed_dir(
        tmp_path,
        series=[_series("school", "高校关系测试会议", "SCH")],
        editions=[with_evidence],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir2)
    relation = db_session.execute(select(SchoolConference)).scalars().first()
    assert relation is not None
    assert relation.notice_url is not None


# ---------------------- 7. pending Edition 不展示为 confirmed
def test_pending_edition_is_never_confirmed(db_session, tmp_path) -> None:
    pending = _edition(
        "pend",
        sources=[
            {
                "source_type": "university_official",
                "source_name": "高校官方页面",
                "source_url": "https://pend.example.edu.cn/notice",
                "official_domain": "pend.example.edu.cn",
            }
        ],
    )
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("pend", "待核验会议", "PEND")],
        editions=[pending],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert edition.verification_status == "pending_verification"
    assert edition.authority_status == "pending_verification"
    assert edition.is_verified is False


# ---------------------- 8. deadline 为 NULL 时不能自动生成状态
def test_null_deadline_does_not_invent_status(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("nulls", "无日期会议", "NULLS")],
        editions=[
            _edition(
                "nulls",
                year=2026,
                start_date=None,
                end_date=None,
                abstract_deadline=None,
                paper_deadline=None,
                poster_deadline=None,
                registration_deadline=None,
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert edition.paper_deadline is None
    assert edition.start_date is None
    assert edition.edition_status == "unknown"
    assert edition_has_actionable_official_info(edition) is False
    assert edition_actionable_status(edition) is None


# ---------------------- 9. actionable conference 判定
def test_actionable_conference_judgement(db_session, tmp_path, client) -> None:
    assert edition_has_actionable_official_info({"year": 2026}) is False
    assert (
        edition_has_actionable_official_info(
            {"year": 2026, "paper_deadline": "2026-12-01"}
        )
        is True
    )
    assert student_opportunity_tags(["doctoral_consortium", "graduate_friendly"]) == [
        "doctoral_consortium",
        "graduate_friendly",
    ]
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[
            _series(
                "act",
                "可行动会议",
                "ACT",
                extra={"student_value_tags": ["paper_submission"]},
            )
        ],
        editions=[
            _edition(
                "act",
                year=2026,
                start_date="2026-12-10",
                end_date="2026-12-15",
                paper_deadline="2026-12-01",
            ),
            _edition("act", year=2025),
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    response = client.get("/api/conferences/editions?year=2026&actionable=true")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    response = client.get("/api/conferences/series?actionable=true")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1


# ---------------------- 10. 2026 Edition 日期状态计算
def test_2026_edition_date_status_calculation() -> None:
    today = date(2026, 9, 6)
    assert (
        edition_actionable_status(
            {
                "year": 2026,
                "paper_deadline": "2026-12-01",
                "start_date": "2026-12-10",
                "end_date": "2026-12-15",
            },
            today=today,
        )
        == "open"
    )
    assert (
        edition_actionable_status(
            {
                "year": 2026,
                "student_value_tags": ["doctoral_consortium"],
                "start_date": "2026-11-05",
                "end_date": "2026-11-08",
            },
            today=today,
        )
        == "upcoming"
    )
    assert (
        edition_actionable_status(
            {
                "year": 2026,
                "paper_deadline": "2026-03-01",
                "start_date": "2026-03-20",
                "end_date": "2026-04-01",
            },
            today=today,
        )
        == "closed"
    )
    assert (
        edition_actionable_status(
            {"year": 2026, "student_value_tags": ["student_forum"]},
            today=today,
        )
        == "unknown"
    )
    # 2027 Edition is never treated as a 2026 actionable item.
    assert (
        edition_actionable_status(
            {"year": 2027, "paper_deadline": "2027-01-01"},
            today=today,
        )
        is None
    )
