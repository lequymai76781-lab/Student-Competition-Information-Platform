"""Academic Conference V1.1 behavior tests.

Covers the ten V1.1 test targets:
alias de-duplication, Series/Edition boundary, source priority, recognition
evidence, student_value_tags, unknown fields, duplicate/idempotent import,
Edition date validation, DiscoveryCandidate rejected states, and the rule that
SchoolConference can never verify conference identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    ConferenceDiscoveryCandidate,
    ConferenceEdition,
    ConferenceSeries,
    ConferenceSource,
    SchoolConference,
)
from app.services.conference_authority_service import (
    recognition_has_evidence,
    recognition_summary,
    validate_audience,
    validate_recognition,
    validate_student_value_tags,
)
from app.services.conference_seed_import_service import (
    ConferenceSeedImportService,
    validate_edition_payload,
)


def _write_seed_dir(
    tmp_path: Path,
    *,
    series: list[dict] | None = None,
    editions: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> Path:
    seed_dir = tmp_path / "conference_v11_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "series_seed.json").write_text(
        json.dumps({"series": series or []}, ensure_ascii=False), encoding="utf-8"
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


def _series(
    key: str,
    name: str,
    short_name: str,
    *,
    source_type: str = "conference_official_site",
    extra: dict | None = None,
) -> dict:
    payload = {
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
                "source_url": f"https://{key}.example.org/{source_type}",
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


# --------------------------------------------------------- alias de-duplication
def test_alias_dedup_www_and_the_web_conference_are_one_series(
    db_session, tmp_path
) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("www", "The Web Conference", "WWW")],
    )
    service = ConferenceSeedImportService()
    first = service.import_folder(db_session, seed_dir)
    assert first["series"]["created"] == 1

    second_dir = _write_seed_dir(
        tmp_path,
        series=[
            _series("www", "The Web Conference", "WWW"),
            _series("www_legacy", "International World Wide Web Conference", "WWW"),
        ],
    )
    second = service.import_folder(db_session, second_dir)
    rows = list(db_session.execute(select(ConferenceSeries)).scalars())
    assert len(rows) == 1
    assert second["series"]["created"] == 0
    assert second["series"]["alias_linked"] >= 1
    assert "International World Wide Web Conference" in (rows[0].aliases or [])


# --------------------------------------------------------- Series / Edition boundary
def test_series_and_edition_own_disjoint_fields() -> None:
    series_columns = set(ConferenceSeries.__table__.columns.keys())
    edition_columns = set(ConferenceEdition.__table__.columns.keys())
    assert "year" in edition_columns and "year" not in series_columns
    assert "short_name" in series_columns and "short_name" not in edition_columns
    assert "start_date" in edition_columns and "start_date" not in series_columns


# --------------------------------------------------------- source priority
def test_source_priority_s_beats_b_and_b_never_verified(db_session, tmp_path) -> None:
    series_payload = _series("prio", "优先级测试会议", "PRIO", source_type="university_official")
    series_payload["sources"].append(
        {
            "source_type": "conference_official_site",
            "source_name": "官网来源",
            "source_url": "https://prio.example.org/official",
            "official_domain": "prio.example.org",
        }
    )
    seed_dir = _write_seed_dir(tmp_path, series=[series_payload])
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    assert series.authority_status == "verified_official"
    sources = list(db_session.execute(select(ConferenceSource)).scalars())
    b_source = next(s for s in sources if s.authority_level == "B")
    s_source = next(s for s in sources if s.authority_level == "S")
    assert b_source.is_verified is False
    assert s_source.is_verified is True


# --------------------------------------------------------- recognition evidence
def test_recognition_validation_and_evidence_rule() -> None:
    with pytest.raises(ValueError):
        validate_recognition({"system": "STARS", "level": "A"})
    with pytest.raises(ValueError):
        validate_recognition({"system": "CCF", "level": "D"})
    ok = validate_recognition({"system": "CCF", "level": "A", "version_year": 2022})
    assert ok["system"] == "CCF"
    summary = recognition_summary([{"system": "CCF", "level": "A", "version_year": 2022}])
    assert summary[0]["display"] == "CCF推荐A类（2022版目录）"
    # Evidence rule: classification alone is not "with evidence".
    assert recognition_has_evidence({"system": "CCF", "level": "A"}) is False
    assert (
        recognition_has_evidence(
            {
                "system": "CCF",
                "level": "A",
                "source_url": "https://www.ccf.org.cn/Academic_Evaluation/",
            }
        )
        is True
    )


def test_importer_accepts_ccf_levels_but_keeps_them_flagable(db_session, tmp_path) -> None:
    payload = _series(
        "ccfrec",
        "带CCF分级的会议",
        "CCFREC",
        extra={"external_classifications": [{"system": "CCF", "level": "A", "version_year": 2022}]},
    )
    seed_dir = _write_seed_dir(tmp_path, series=[payload])
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    stored = list(series.external_classifications or [])
    assert stored and stored[0]["system"] == "CCF"
    assert recognition_has_evidence(stored[0]) is False  # audit marks it for V1.2 backfill


# --------------------------------------------------------- student value tags / audience
def test_student_value_tags_and_audience_vocabulary_are_enforced(
    db_session, tmp_path
) -> None:
    assert validate_student_value_tags(["paper_submission", "poster"]) == [
        "paper_submission",
        "poster",
    ]
    with pytest.raises(ValueError):
        validate_student_value_tags(["五星推荐"])
    assert validate_audience(["undergraduate", "phd"]) == ["undergraduate", "phd"]
    with pytest.raises(ValueError):
        validate_audience(["小学生"])

    payload = _series(
        "tags",
        "学生价值标签会议",
        "TAGS",
        extra={"student_value_tags": ["paper_submission", "poster"], "audience": ["undergraduate"]},
    )
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[payload],
        editions=[
            _edition(
                "tags",
                student_value_tags=["doctoral_consortium"],
                audience=["phd"],
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert series.student_value_tags == ["paper_submission", "poster"]
    assert series.audience == ["undergraduate"]
    assert edition.student_value_tags == ["doctoral_consortium"]
    assert edition.audience == ["phd"]

    bad = _series(
        "badtag",
        "非法标签会议",
        "BADTAG",
        extra={"student_value_tags": ["虚假标签"]},
    )
    bad_dir = _write_seed_dir(tmp_path, series=[bad])
    with pytest.raises(ValueError):
        ConferenceSeedImportService().import_folder(db_session, bad_dir)
    db_session.rollback()


# --------------------------------------------------------- unknown fields stay None
def test_unknown_fields_stay_null(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("unknowns", "未填字段会议", "UNK")],
        editions=[
            _edition(
                "unknowns",
                year=2025,
                start_date=None,
                end_date=None,
                city=None,
                country_or_region=None,
                student_value_tags=None,
                audience=None,
            )
        ],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    assert series.student_value_tags is None
    assert series.audience is None
    assert edition.student_value_tags is None
    assert edition.audience is None
    assert edition.start_date is None
    assert edition.end_date is None
    assert edition.city is None


# --------------------------------------------------------- duplicate import idempotent
def test_rerun_v11_seed_import_is_idempotent(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("idem", "幂等会议", "IDEM")],
        editions=[_edition("idem")],
        candidates=[
            {
                "raw_name": "候选会议（C 级）",
                "year": 2026,
                "source_type": "third_party_directory",
                "source_name": "导航站",
                "source_url": "https://third.example.org/item",
                "source_domain": "third.example.org",
                "status": "pending",
            }
        ],
    )
    service = ConferenceSeedImportService()
    first = service.import_folder(db_session, seed_dir)
    second = service.import_folder(db_session, seed_dir)
    assert first["series"]["created"] == 1
    assert first["editions"]["created"] == 1
    assert first["candidates"]["created"] == 1
    assert second["series"]["created"] == 0
    assert second["editions"]["created"] == 0
    assert second["candidates"]["created"] == 0
    assert (
        db_session.scalar(select(func.count()).select_from(ConferenceSeries)) == 1
    )
    assert (
        db_session.scalar(select(func.count()).select_from(ConferenceEdition)) == 1
    )


# --------------------------------------------------------- edition date validation
def test_edition_date_validation_rules() -> None:
    with pytest.raises(ValueError):
        validate_edition_payload(
            {"start_date": "2026-08-05", "end_date": "2026-08-01"}
        )
    with pytest.raises(ValueError):
        validate_edition_payload(
            {
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "paper_deadline": "2026-08-10",
            }
        )
    # Equal dates are allowed; unknown dates simply stay NULL.
    validate_edition_payload(
        {"start_date": "2026-08-01", "end_date": "2026-08-01", "paper_deadline": "2026-07-01"}
    )
    validate_edition_payload({"year": 2026})


def test_same_series_same_year_edition_is_a_single_row(db_session, tmp_path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[_series("sy", "同系列同年会议", "SY")],
        editions=[_edition("sy", year=2026, end_date="2026-08-05")],
    )
    service = ConferenceSeedImportService()
    service.import_folder(db_session, seed_dir)
    second = _write_seed_dir(
        tmp_path,
        series=[_series("sy", "同系列同年会议", "SY")],
        editions=[_edition("sy", year=2026, end_date="2026-08-06")],
    )
    service.import_folder(db_session, second)
    rows = list(db_session.execute(select(ConferenceEdition)).scalars())
    assert len(rows) == 1
    assert rows[0].year == 2026


def test_orm_unique_series_year_constraint() -> None:
    import pytest

    from app.database.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Local = sessionmaker(bind=engine)
    with Local() as db:
        series = ConferenceSeries(name="唯一系列", short_name="UNIQ", discipline="computer_science")
        db.add(series)
        db.flush()
        db.add_all(
            [
                ConferenceEdition(conference_series_id=series.id, year=2026),
                ConferenceEdition(conference_series_id=series.id, year=2026),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()
    engine.dispose()


# --------------------------------------------------------- discovery rejected
def test_discovery_rejected_requires_controlled_reason(db_session, tmp_path) -> None:
    base = {
        "raw_name": "垃圾商业会议条目",
        "year": 2026,
        "source_type": "commercial_conference_platform",
        "source_name": "商业会议平台",
        "source_url": "https://junk.example.org/cfp",
        "source_domain": "junk.example.org",
        "status": "rejected",
        "rejection_reason": None,
    }
    seed_dir = _write_seed_dir(tmp_path, candidates=[base])
    with pytest.raises(ValueError):
        ConferenceSeedImportService().import_folder(db_session, seed_dir)
    db_session.rollback()

    bad_reason = {**base, "rejection_reason": "随便拒绝"}
    bad_dir = _write_seed_dir(tmp_path, candidates=[bad_reason])
    with pytest.raises(ValueError):
        ConferenceSeedImportService().import_folder(db_session, bad_dir)
    db_session.rollback()

    ok = {
        **base,
        "rejection_reason": "commercial_conference",
        "notes": "无法找到主办学会/官网，仅有商业会议平台宣传。",
    }
    ok_dir = _write_seed_dir(tmp_path, candidates=[ok])
    ConferenceSeedImportService().import_folder(db_session, ok_dir)
    candidate = db_session.execute(select(ConferenceDiscoveryCandidate)).scalars().first()
    assert candidate.status == "rejected"
    assert candidate.rejection_reason == "commercial_conference"


# --------------------------------------------------------- school relation cannot verify edition
def test_school_relation_never_verifies_edition_identity(db_session, tmp_path) -> None:
    series_payload = _series("sch", "高校承办会议", "SCH")
    relations = [
        {
            "school_name": "测试大学",
            "relation_type": "organizer",
            "source_type": "university_official",
            "notice_url": "https://univ.example.edu.cn/notice/2026",
            "source_name": "测试大学官网通知",
            "notes": "高校通知页面出现'承办'字样，仅证明校内关系。",
        }
    ]
    edition_payload = {
        **_edition("sch"),
        "sources": [],  # no official source on the edition itself
        "school_relations": relations,
    }
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[series_payload],
        editions=[edition_payload],
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)
    series = db_session.execute(select(ConferenceSeries)).scalars().first()
    edition = db_session.execute(select(ConferenceEdition)).scalars().first()
    relation = db_session.execute(select(SchoolConference)).scalars().first()
    assert series.authority_status == "verified_official"  # series identity from S source
    assert relation is not None
    assert relation.is_verified is True  # school fact itself can be confirmed
    assert edition.authority_status == "pending_verification"
    assert edition.verification_status == "pending_verification"
    assert edition.is_verified is False  # school relation never upgrades Edition


# --------------------------------------------------------- read-only API filter params
def test_v11_api_filter_params_are_readonly(client, db_session, tmp_path) -> None:
    series_payload = _series(
        "apifilter",
        "过滤参数测试会议",
        "APIF",
        extra={
            "student_value_tags": ["paper_submission"],
            "audience": ["undergraduate", "phd"],
            "external_classifications": [
                {
                    "system": "CCF",
                    "level": "A",
                    "version_year": 2022,
                    "source_url": "https://www.ccf.org.cn/Academic_Evaluation/",
                }
            ],
        },
    )
    editions_payload = [
        _edition(
            "apifilter",
            year=2026,
            country_or_region="美国",
            city="波士顿",
            student_value_tags=["doctoral_consortium"],
            audience=["phd"],
        ),
        _edition(
            "apifilter",
            year=2025,
            country_or_region="中国",
            city="北京",
            start_date="2025-08-01",
            end_date="2025-08-03",
        ),
    ]
    seed_dir = _write_seed_dir(
        tmp_path,
        series=[series_payload],
        editions=editions_payload,
    )
    ConferenceSeedImportService().import_folder(db_session, seed_dir)

    response = client.get("/api/conferences/series?student_value_tag=doctoral_consortium")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/series?recognition_level=CCF-A")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/series?discipline=computer_science&year=2026&country=美国")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/series?verification_status=verified_official")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/editions?student_value_tag=doctoral_consortium")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1

    response = client.get("/api/conferences/series?organization=不存在的组织")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 0
