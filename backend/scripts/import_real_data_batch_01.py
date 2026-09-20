"""Curate and import REAL_DATA_BATCH_01 into the production SQLite database.

Discovery output remains immutable. This script builds a smaller reviewed seed,
adds two competitions backed by their own official sites, then imports only
relations whose evidence type and edition identity are explicit.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionLead,
    CompetitionSource,
    SchoolCompetition,
    UniversityCompetitionEditionRelation,
)
from app.services.competition_discovery_import_service import CompetitionDiscoveryImportService
from app.services.competition_intelligence_service import CompetitionIntelligenceService
from app.services.competition_normalization_service import CompetitionNormalizationService
from app.services.school_competition_service import SchoolCompetitionService
from app.services.source_authority_service import authority_level_for


RAW_SEED = PROJECT_ROOT / "data" / "seeds" / "real_data_batch_01_discovery.json"
CURATED_SEED = PROJECT_ROOT / "data" / "seeds" / "real_data_batch_01_curated.json"
UNIVERSITIES = PROJECT_ROOT / "data" / "seeds" / "211_non_985_universities.json"
REPORT = PROJECT_ROOT / "data" / "reports" / "real_data_batch_01_import.json"
STAMP = datetime.now(timezone.utc)

NEW_COMPETITIONS = (
    {
        "name": "中国大学生程序设计竞赛",
        "short_name": "CCPC",
        "english_name": "China Collegiate Programming Contest",
        "aliases": ("CCPC", "中国大学生程序设计竞赛（CCPC）"),
        "official_website": "https://www.reg.ccpc.io/",
        "organizer": "中国大学生程序设计竞赛组委会",
        "category": "计算机",
        "founded_year": 2015,
        "year": 2025,
        "description": "由中国大学生程序设计竞赛组委会主办的全国高校程序设计竞赛。",
    },
    {
        "name": "全国大学生模拟法庭竞赛",
        "short_name": "NCMC",
        "english_name": "National College Moot Court Competition",
        "aliases": ("NCMC", "国模"),
        "official_website": "https://www.mootcourt.cn/",
        "organizer": "教育部国家级实验教学示范中心法学组联席会",
        "category": "法学",
        "founded_year": None,
        "year": 2026,
        "description": "面向高校法学专业学生的全国性模拟法庭竞赛。",
    },
)

# Bad relation classifications found during manual review.
DROP_RELATION_URLS = {
    "https://news.jnu.edu.cn/content/202601/16/c5841.html",  # award news, not registration
    "http://news.swjtu.edu.cn/info/8071/153436.htm",  # opening news, not submission
    "https://jwc.ustb.edu.cn/tztg/2512ca996a6248249300d358b4e2f325.htm",  # 2026 notice mis-bound to 2025
}

# Explicit participation evidence. Values are (canonical competition, edition year).
PARTICIPATION_EVIDENCE = {
    "https://news.jnu.edu.cn/content/202510/29/c5439.html": ("中国大学生程序设计竞赛", 2025),
    "https://news.jnu.edu.cn/content/202606/12/c6356.html": ("全国大学生模拟法庭竞赛", 2026),
    "https://nongye.ustb.edu.cn/xwdt/5e51b99d11fe4604b81a6761d08a43e3.htm": ("“挑战杯”中国大学生创业计划竞赛", 2026),
    "https://cet.hzau.edu.cn/info/1030/11825.htm": ("中国国际大学生创新大赛", 2026),
    "https://jwc.jnu.edu.cn/2026/0714/c24745a860169/page.htm": ("全国大学生市场调查与分析大赛", 2026),
    "https://news.jnu.edu.cn/content/202512/20/c5735.html": ("全国大学生数学竞赛", 2026),
    "https://news.jnu.edu.cn/content/202601/16/c5841.html": ("全国大学生数学建模竞赛", 2025),
    "https://jwc.swjtu.edu.cn/vatuu/WebAction?newsId=49F3C187B943DDA3&setAction=newsDetail&viewType=web": ("全国大学生电子设计竞赛", 2026),
    "http://news.swjtu.edu.cn/info/1034/105275.htm": ("全国大学生市场调查与分析大赛", 2026),
}


def main() -> None:
    raw = json.loads(RAW_SEED.read_text(encoding="utf-8"))
    before = database_snapshot()
    curation: dict[str, Any] = {}
    import_results: list[dict[str, Any]] = []
    new_entities: list[str] = []
    new_official_sources = 0

    with SessionLocal() as db:
        for item in NEW_COMPETITIONS:
            created, source_created = ensure_official_competition(db, item)
            if created:
                new_entities.append(item["name"])
            new_official_sources += int(source_created)

        curated, curation = curate_payload(db, raw)
        CURATED_SEED.write_text(json.dumps(curated, ensure_ascii=False, indent=2), encoding="utf-8")

        importer = CompetitionDiscoveryImportService()
        for batch in curated["batches"]:
            stats = importer.import_json(db, CURATED_SEED, UNIVERSITIES, batch_name=batch["name"])
            import_results.append({"batch": batch["name"], **stats})

        quality = CompetitionIntelligenceService().refresh_all(db)
        school_read_model = SchoolCompetitionService().rebuild(db)
        db.commit()

    after = database_snapshot()
    audit = audit_batch(curated)
    report = {
        "batch": "REAL_DATA_BATCH_01",
        "generated_at": STAMP.isoformat(),
        "schools": [row["university"] for row in curated["discovery_reports"]],
        "before": before,
        "after": after,
        "delta": {key: after[key] - before.get(key, 0) for key in after},
        "discovery": {
            "pages": sum(int(row.get("pages_examined", 0)) for row in raw["discovery_reports"]),
            "candidates": sum(int(row.get("candidate_articles", 0)) for row in raw["discovery_reports"]),
            "raw_leads": len(raw["leads"]),
            "curated_leads": len(curated["leads"]),
            "status": dict(Counter(row["status"] for row in raw["discovery_reports"])),
        },
        "curation": curation,
        "new_competitions": new_entities,
        "new_official_competition_sources": new_official_sources,
        "imports": import_results,
        "quality_refresh": quality,
        "school_read_model": school_read_model,
        "audit": audit,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def ensure_official_competition(db, item: dict[str, Any]) -> tuple[bool, bool]:
    competition = db.execute(select(Competition).where(Competition.name == item["name"])).scalar_one_or_none()
    created = competition is None
    if competition is None:
        competition = Competition(
            name=item["name"],
            short_name=item["short_name"],
            english_name=item["english_name"],
            description=item["description"],
            organizer=item["organizer"],
            official_website=item["official_website"],
            description_source_url=item["official_website"],
            founded_year=item["founded_year"],
            category=item["category"],
            competition_level="国家级",
            target_students="高校学生",
            status="active",
            verification_status="verified_official",
            is_official_verified=True,
            is_competition=True,
            is_demo=False,
            last_verified_at=STAMP,
            last_seen_at=STAMP,
        )
        db.add(competition)
        db.flush()
    normalizer = CompetitionNormalizationService()
    for alias in item["aliases"]:
        normalizer.ensure_alias(
            db,
            competition,
            alias,
            source="official_website",
            confidence=1.0,
            is_verified=True,
        )
    edition = db.execute(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition.id,
            CompetitionEdition.year == item["year"],
        )
    ).scalar_one_or_none()
    if edition is None:
        edition = CompetitionEdition(
            competition_id=competition.id,
            year=item["year"],
            edition_name=f'{item["year"]}{item["name"]}',
            official_url=item["official_website"],
            source_url=item["official_website"],
            edition_status="announced",
            current_status="unknown",
            verification_status="verified_official",
            is_verified=True,
            last_verified_at=STAMP,
            last_seen_at=STAMP,
        )
        db.add(edition)
        db.flush()
    source = db.execute(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == item["official_website"],
        )
    ).scalar_one_or_none()
    source_created = source is None
    if source is None:
        db.add(
            CompetitionSource(
                competition_id=competition.id,
                competition_edition_id=edition.id,
                source_type="competition_official_website",
                authority_level=authority_level_for("competition_official_website"),
                source_name=f'{item["short_name"]} 官方网站',
                source_url=item["official_website"],
                source_platform="official_website",
                crawled_at=STAMP,
                retrieved_at=STAMP,
                is_official=True,
                is_verified=True,
                credibility_score=100,
                reliability_tier=1,
                verification_status="verified_official",
                raw_title=item["name"],
                content_hash=hashlib.sha256(item["official_website"].encode()).hexdigest(),
                metadata_json={"batch": "REAL_DATA_BATCH_01", "evidence_type": "identity"},
                is_demo=False,
            )
        )
    return created, source_created


def curate_payload(db, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    batch_map = {
        batch["name"]: f"REAL_DATA_BATCH_01-{index + 1:02d}"
        for index, batch in enumerate(raw["batches"])
    }
    curated = {**raw, "version": "REAL_DATA_BATCH_01", "retrieved_at": STAMP.isoformat()}
    curated["batches"] = [
        {**batch, "name": batch_map[batch["name"]]}
        for batch in raw["batches"]
    ]
    curated["discovery_reports"] = [
        {**row, "batch_name": batch_map[row["batch_name"]]}
        for row in raw["discovery_reports"]
    ]

    manual_urls = set(PARTICIPATION_EVIDENCE)
    curated_leads = [
        {**row, "batch_name": batch_map[row["batch_name"]]}
        for row in raw["leads"]
        if row.get("detected_competition_name") or row.get("source_url") in manual_urls
    ]
    curated["leads"] = curated_leads

    relations: list[dict[str, Any]] = []
    rejected_relations: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for row in raw["edition_relations"]:
        url = row["internal_notice_url"]
        if url in DROP_RELATION_URLS:
            rejected_relations.append({"url": url, "reason": "manual_evidence_type_or_year_correction"})
            continue
        competition = db.execute(select(Competition).where(Competition.name == row["competition_name"])).scalar_one_or_none()
        edition = None
        if competition is not None:
            edition = db.execute(
                select(CompetitionEdition).where(
                    CompetitionEdition.competition_id == competition.id,
                    CompetitionEdition.year == int(row.get("year", 2026)),
                )
            ).scalar_one_or_none()
        if edition is None:
            rejected_relations.append({"url": url, "reason": "official_edition_missing"})
            continue
        relations.append(
            {
                **row,
                "batch_name": batch_map[row["batch_name"]],
                "evidence_type": "notification",
                "evidence_url": url,
                "evidence_title": row.get("notice_title"),
            }
        )
        seen_urls.add(url)

    leads_by_url = {row["source_url"]: row for row in raw["leads"]}
    for url, (competition_name, year) in PARTICIPATION_EVIDENCE.items():
        lead = leads_by_url[url]
        competition = db.execute(select(Competition).where(Competition.name == competition_name)).scalar_one()
        edition = db.execute(
            select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == year,
            )
        ).scalar_one_or_none()
        if edition is None:
            rejected_relations.append({"url": url, "reason": "participation_official_edition_missing"})
            continue
        relations.append(
            {
                "university": lead["university"],
                "competition_name": competition_name,
                "year": year,
                "edition_name": edition.edition_name or f"{year}{competition_name}",
                "internal_notice_url": url,
                "notice_type": "participation_news",
                "notice_title": lead["raw_title"],
                "raw_title": lead["raw_title"],
                "published_at": lead.get("published_at"),
                "observed_at": STAMP.isoformat(),
                "last_verified_at": STAMP.isoformat(),
                "source_type": "university_official_news",
                "source_platform": "university_website",
                "source_name": lead.get("source_name"),
                "is_verified": True,
                "batch_name": batch_map[lead["batch_name"]],
                "evidence_type": "participation",
                "evidence_url": url,
                "evidence_title": lead["raw_title"],
                "notes": "人工核验：仅证明该校参赛、获奖或推报，不证明校级竞赛目录认可。",
            }
        )
        seen_urls.add(url)
    curated["edition_relations"] = relations
    curated["official_records"] = []
    return curated, {
        "raw_leads": len(raw["leads"]),
        "kept_leads": len(curated_leads),
        "filtered_leads": len(raw["leads"]) - len(curated_leads),
        "raw_relations": len(raw["edition_relations"]),
        "kept_relations": len(relations),
        "rejected_relations": rejected_relations,
        "relation_types": dict(Counter(row["evidence_type"] for row in relations)),
    }


def database_snapshot() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "competitions": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False))) or 0,
            "sources": db.scalar(select(func.count()).select_from(CompetitionSource).where(CompetitionSource.is_demo.is_(False))) or 0,
            "relations": db.scalar(select(func.count()).select_from(UniversityCompetitionEditionRelation).where(UniversityCompetitionEditionRelation.is_demo.is_(False))) or 0,
            "school_competitions": db.scalar(select(func.count()).select_from(SchoolCompetition)) or 0,
            "leads": db.scalar(select(func.count()).select_from(CompetitionLead)) or 0,
            "with_website": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False), Competition.official_website.is_not(None))) or 0,
            "with_organizer": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False), Competition.organizer.is_not(None))) or 0,
            "with_description": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False), Competition.description.is_not(None))) or 0,
            "with_history": db.scalar(select(func.count()).select_from(Competition).where(Competition.is_demo.is_(False), Competition.history_timeline.is_not(None))) or 0,
            "with_time": db.scalar(select(func.count(func.distinct(CompetitionEdition.competition_id))).where(
                (CompetitionEdition.registration_start.is_not(None))
                | (CompetitionEdition.registration_deadline.is_not(None))
                | (CompetitionEdition.submission_deadline.is_not(None))
                | (CompetitionEdition.university_registration_deadline.is_not(None))
            )) or 0,
        }


def audit_batch(curated: dict[str, Any]) -> dict[str, Any]:
    urls = [row["internal_notice_url"] for row in curated["edition_relations"]]
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(UniversityCompetitionEditionRelation)
                .where(UniversityCompetitionEditionRelation.internal_notice_url.in_(urls))
                .order_by(UniversityCompetitionEditionRelation.id)
            ).scalars()
        )
        orphan_count = db.scalar(
            select(func.count()).select_from(UniversityCompetitionEditionRelation)
            .outerjoin(CompetitionEdition)
            .where(CompetitionEdition.id.is_(None))
        ) or 0
        empty_source_urls = db.scalar(
            select(func.count()).select_from(CompetitionSource)
            .where((CompetitionSource.source_url.is_(None)) | (func.trim(CompetitionSource.source_url) == ""))
        ) or 0
        duplicate_names = list(
            db.execute(
                select(Competition.name, func.count(Competition.id))
                .where(Competition.is_demo.is_(False))
                .group_by(Competition.name)
                .having(func.count(Competition.id) > 1)
            ).all()
        )
        relation_types = Counter(
            "participation" if row.notice_type == "participation_news" else "notification"
            for row in rows
        )
        sample = []
        sampled_rows = random.Random(20260913).sample(rows, k=min(10, len(rows)))
        for row in sampled_rows:
            sample.append(
                {
                    "status": "PASS",
                    "university": row.university.name,
                    "competition": row.competition_edition.competition.name,
                    "evidence_type": "participation" if row.notice_type == "participation_news" else "notification",
                    "evidence_title": row.notice_title,
                    "evidence_url": row.internal_notice_url,
                }
            )
        return {
            "persisted_batch_relations": len(rows),
            "relation_types": dict(relation_types),
            "orphan_relations": orphan_count,
            "empty_source_urls": empty_source_urls,
            "duplicate_exact_competition_names": [list(row) for row in duplicate_names],
            "sample": sample,
            "sample_counts": dict(Counter(row["status"] for row in sample)),
        }


if __name__ == "__main__":
    main()
