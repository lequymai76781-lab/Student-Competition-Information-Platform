"""Idempotently import SPECIALIZED_INSTITUTIONS_COVERAGE_02 verified data.

The batch reuses the existing competition, edition, university relation,
policy-recognition, source and fact tables.  Research-only terminal outcomes
are deliberately kept in the checkpoint archive rather than fabricated as
database relations.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.database.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    College,
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionPolicyRecognition,
    CompetitionSource,
    PolicyDocument,
    University,
    UniversityCompetitionEditionRelation,
)

TASK = "SPECIALIZED_INSTITUTIONS_COVERAGE_02"
MASTER = ROOT / "data/seeds/specialized_institutions_02.json"
SEED = ROOT / "data/seeds/specialized_institutions_02_relations.json"
REPORT = ROOT / "data/reports/specialized_institutions_coverage_02_import.json"
ALLOWED_EVENT_TYPES = {
    "competition", "festival", "showcase", "exhibition", "call_for_works",
    "award", "forum", "conference",
}
ALLOWED_RELATION_TYPES = {"recognition", "notification", "participation"}
ALLOWED_SCOPES = {"university", "college", "department", "major"}
NEW_CANONICAL = {
    "中国音乐金钟奖": {
        "official_website": "https://www.chnmusic.org.cn/jzj/",
        "founded_year": 2001,
        "frequency": "每两年一届",
        "aliases": ["中国音乐“金钟奖”", "中国音乐金钟奖声乐比赛", "中国音乐金钟奖流行音乐大赛"],
    },
    "Young·绒—中国创新创意设计大赛": {
        "official_website": "https://www.ad.tsinghua.edu.cn/info/1061/32725.htm",
        "aliases": ["Young·绒中国创新创意设计大赛"],
    },
    "比亚迪全球汽车设计大赛": {
        "official_website": "https://www.ad.tsinghua.edu.cn/info/1455/32288.htm",
        "aliases": ["BYD全球汽车设计大赛"],
    },
    "“到延安去·三秦学子圣地行”主题文创设计大赛": {
        "official_website": "https://sheji.xafa.edu.cn/dynamic/show/709.html",
        "aliases": ["到延安去·三秦学子圣地行主题文创设计大赛"],
    },
    "“学院杯”中国室内与环境设计大赛": {
        "official_website": "https://www.lumei.edu.cn/jzyssjxy/info/1004/1926.htm",
        "aliases": ["学院杯中国室内与环境设计大赛", "学院杯中国室内及环境设计大赛"],
    },
    "天津市大学生民族文创设计大赛": {
        "official_website": "https://www.tjarts.edu.cn/info/1155/18834.htm",
        "aliases": ["天津市大学生民族文化创意设计大赛"],
    },
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def digest(*parts: object) -> str:
    text = "\u241f".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalized_name(value: str) -> str:
    value = re.sub(r"[\s\u3000·•—\-_'\"“”‘’《》()（）]", "", value.lower())
    value = re.sub(r"^(?:20\d{2}年?)", "", value)
    value = re.sub(r"^第[一二三四五六七八九十百0-9]+届", "", value)
    return value


def load_inputs() -> tuple[list[dict], list[dict]]:
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    if len(master) != 20 or len({row["name"] for row in master}) != 20:
        raise ValueError("coverage-02 master must contain exactly 20 unique units")
    if Counter(row["category"][0] for row in master) != {"music": 11, "fine_arts": 9}:
        raise ValueError("coverage-02 master category split must be music=11, fine_arts=9")
    if len(rows) < 20:
        raise ValueError("verified relation seed must contain at least 20 QA-capable rows")
    for row in rows:
        if row["event_type"] not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"invalid event_type: {row['competition']}")
        if row["relation_type"] not in ALLOWED_RELATION_TYPES:
            raise ValueError(f"invalid relation_type: {row['competition']}")
        if row["scope"] not in ALLOWED_SCOPES:
            raise ValueError(f"invalid scope: {row['competition']}")
        if urlparse(row["source_url"]).scheme != "https":
            raise ValueError(f"non-https source: {row['source_url']}")
    return master, rows


def register_master(db, master: list[dict], stats: Counter) -> None:
    current = now_utc()
    for unit in master:
        school = db.scalar(select(University).where(University.name == unit["university_name"]))
        if school is None:
            school = University(
                name=unit["university_name"],
                province=unit["province"],
                city=unit["city"],
                university_type=unit["institution_type"],
                is_985=False,
                is_211=False,
                is_double_first_class=False,
                official_website=unit["official_url"],
                official_domain=domain(unit["official_url"]),
                policy_crawl_status="not_started",
                competition_discovery_status="completed",
                last_competition_discovery_at=current,
                is_demo=False,
            )
            db.add(school)
            db.flush()
            stats["university_created"] += 1
        if unit["entity_level"] == "college":
            college = db.scalar(
                select(College).where(
                    College.university_id == school.id,
                    College.name == unit["college_name"],
                )
            )
            if college is None:
                college = College(
                    university_id=school.id,
                    name=unit["college_name"],
                    official_website=unit["official_url"],
                    official_domain=domain(unit["official_url"]),
                    source_url=unit["official_url"],
                    source_hash=digest(TASK, unit["university_name"], unit["college_name"]),
                    is_verified=True,
                    is_demo=False,
                )
                db.add(college)
                db.flush()
                stats["college_created"] += 1


def resolve_college(db, school: University, row: dict, stats: Counter) -> College | None:
    if row["scope"] != "college":
        return None
    name = row.get("college") or row.get("department")
    if not name:
        raise ValueError(f"college scope missing name: {row['school']} / {row['competition']}")
    college = db.scalar(select(College).where(College.university_id == school.id, College.name == name))
    if college is None:
        college = College(
            university_id=school.id,
            name=name,
            official_website=f"https://{domain(row['source_url'])}/",
            official_domain=domain(row["source_url"]),
            source_url=row["source_url"],
            source_hash=digest(TASK, row["school"], name, row["source_url"]),
            is_verified=True,
            is_demo=False,
        )
        db.add(college)
        db.flush()
        stats["college_created"] += 1
    return college


def find_alias_match(db, canonical: str) -> Competition | None:
    target = normalized_name(canonical)
    for competition in db.scalars(select(Competition)).all():
        names = [competition.name]
        if competition.former_names:
            names.extend(competition.former_names)
        if target in {normalized_name(name) for name in names if name}:
            return competition
    return None


def ensure_competition(db, row: dict, stats: Counter) -> Competition:
    competition = db.scalar(select(Competition).where(Competition.name == row["competition"]))
    if competition is None:
        competition = find_alias_match(db, row["competition"])
    if competition is None:
        canonical = NEW_CANONICAL.get(row["competition"], {})
        competition = Competition(
            name=row["competition"],
            organizer=row["organizer"],
            official_website=canonical.get("official_website") or row["canonical_source_url"],
            category="音乐" if row["category"] == "music" else "美术与设计",
            status="active",
            is_cross_major_supported=False,
            is_cross_university_supported=False,
            is_demo=False,
            competition_type=row["event_type"],
            is_competition=row["event_type"] == "competition",
            entity_type=row["event_type"],
            verification_status="verified_official",
            is_official_verified=True,
            former_names=canonical.get("aliases", []),
            founded_year=canonical.get("founded_year"),
            frequency=canonical.get("frequency"),
            description_source_url=row["canonical_source_url"],
            last_verified_at=now_utc(),
        )
        db.add(competition)
        db.flush()
        stats["competition_created"] += 1
    else:
        # Preserve established canonical records. Fill only missing objective fields.
        changed = False
        if not competition.organizer:
            competition.organizer = row["organizer"]
            changed = True
        if not competition.description_source_url:
            competition.description_source_url = row["canonical_source_url"]
            changed = True
        canonical = NEW_CANONICAL.get(row["competition"], {})
        if not competition.official_website and canonical.get("official_website"):
            competition.official_website = canonical["official_website"]
            changed = True
        if changed:
            competition.last_verified_at = now_utc()
            stats["competition_filled"] += 1
    return competition


def ensure_edition(db, competition: Competition, row: dict, stats: Counter) -> CompetitionEdition:
    edition = db.scalar(
        select(CompetitionEdition).where(
            CompetitionEdition.competition_id == competition.id,
            CompetitionEdition.year == row["year"],
        )
    )
    if edition is None:
        edition = CompetitionEdition(
            competition_id=competition.id,
            year=row["year"],
            edition_name=row["edition_name"],
            source_url=row["source_url"],
            official_notice_url=row["source_url"],
            current_status="finished",
            edition_status="finished",
            verification_status="school_confirmed",
            is_verified=True,
            last_verified_at=now_utc(),
        )
        db.add(edition)
        db.flush()
        stats["edition_created"] += 1
    return edition


def ensure_source(db, competition: Competition, edition: CompetitionEdition | None, row: dict, stats: Counter) -> None:
    source = db.scalar(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == row["source_url"],
            CompetitionSource.source_type == "professional_institution_official",
        )
    )
    if source is None:
        db.add(CompetitionSource(
            competition_id=competition.id,
            competition_edition_id=edition.id if edition else None,
            source_type="professional_institution_official",
            authority_level="A2",
            source_name=row["source_name"],
            source_url=row["source_url"],
            source_platform="official_website",
            published_at=parse_date(row["published_at"]),
            retrieved_at=now_utc(),
            is_official=True,
            is_verified=True,
            is_demo=False,
            credibility_score=90,
            reliability_tier=2,
            verification_status="verified_official",
            raw_title=row["title"],
            raw_content=row["evidence"],
            content_hash=digest(row["source_url"], row["evidence"]),
            metadata_json={"task": TASK, "category": row["category"], "relation_type": row["relation_type"]},
        ))
        stats["source_created"] += 1


def ensure_fact(db, competition: Competition, edition: CompetitionEdition | None, row: dict, field: str, value, stats: Counter) -> None:
    fact = db.scalar(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == competition.id,
            CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
            CompetitionFactSource.field_name == field,
            CompetitionFactSource.source_url == row["source_url"],
        )
    )
    if fact is None:
        db.add(CompetitionFactSource(
            competition_id=competition.id,
            competition_edition_id=edition.id if edition else None,
            field_name=field,
            fact_value=value,
            source_type="professional_institution_official",
            source_name=row["source_name"],
            source_url=row["source_url"],
            reliability_tier=2,
            source_level="B",
            is_official=True,
            verification_status="school_confirmed",
            published_at=parse_date(row["published_at"]),
            observed_at=now_utc(),
            last_verified_at=now_utc(),
            source_hash=digest(row["source_url"], field, json.dumps(value, ensure_ascii=False)),
            notes=f"{TASK} 官方证据；professional_reference 不等同主观含金量评级。",
        ))
        stats["fact_created"] += 1


def ensure_recognition(db, school: University, college: College | None, competition: Competition, row: dict, stats: Counter) -> None:
    document_hash = digest(TASK, row["source_url"], row["title"])
    document = db.scalar(select(PolicyDocument).where(PolicyDocument.document_hash == document_hash))
    if document is None:
        document = PolicyDocument(
            university_id=school.id,
            college_id=college.id if college else None,
            scope_type=row["scope"],
            title=row["title"],
            policy_type="competition_recognition",
            year=row["year"],
            latest_available_year=row["year"],
            publisher=row["source_name"],
            source_url=row["source_url"],
            attachment_url=row["source_url"] if row["source_url"].lower().endswith(".pdf") else None,
            official_domain=domain(row["source_url"]),
            authority_level="A2",
            published_at=parse_date(row["published_at"]),
            content_text=row["evidence"],
            document_hash=document_hash,
            is_current=True,
            is_verified=True,
            is_demo=False,
            verification_status="verified_official",
            parser_type="manual_official_evidence",
            source_type="university_official",
            metadata_json={"task": TASK, "category": row["category"], "recognition_scope": row["scope"]},
        )
        db.add(document)
        db.flush()
        stats["policy_created"] += 1
    evidence_hash = digest(row["evidence"])
    recognition = db.scalar(
        select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.policy_document_id == document.id,
            CompetitionPolicyRecognition.competition_id == competition.id,
            CompetitionPolicyRecognition.evidence_hash == evidence_hash,
        )
    )
    if recognition is None:
        db.add(CompetitionPolicyRecognition(
            competition_id=competition.id,
            policy_document_id=document.id,
            university_id=school.id,
            college_id=college.id if college else None,
            year=row["year"],
            recognition_status="recognized",
            recognition_level=row["scope"],
            usage_type="admission",
            evidence_text=row["evidence"],
            evidence_hash=evidence_hash,
            evidence_section="竞赛成果认定",
            confidence=1.0,
            needs_manual_review=False,
            is_demo=False,
        ))
        stats["recognition_created"] += 1


def ensure_relation(db, school: University, college: College | None, competition: Competition, row: dict, stats: Counter) -> CompetitionEdition:
    edition = ensure_edition(db, competition, row, stats)
    relation = db.scalar(
        select(UniversityCompetitionEditionRelation).where(
            UniversityCompetitionEditionRelation.university_id == school.id,
            UniversityCompetitionEditionRelation.competition_edition_id == edition.id,
            UniversityCompetitionEditionRelation.internal_notice_url == row["source_url"],
        )
    )
    if relation is None:
        db.add(UniversityCompetitionEditionRelation(
            university_id=school.id,
            college_id=college.id if college else None,
            competition_edition_id=edition.id,
            source_type="university_official_notice" if domain(row["source_url"]).endswith("edu.cn") else "organizer_official_notice",
            source_platform="official_website",
            source_name=row["source_name"],
            notice_type="award_news" if row["relation_type"] == "participation" else "campus_notice",
            notice_title=row["title"],
            internal_notice_url=row["source_url"],
            organizing_department=row.get("department"),
            published_at=parse_date(row["published_at"]),
            observed_at=now_utc(),
            last_verified_at=now_utc(),
            verification_status="school_confirmed",
            is_verified=True,
            is_demo=False,
            source_hash=digest(row["source_url"], row["title"]),
            metadata_json={
                "task": TASK,
                "category": row["category"],
                "relation_type": row["relation_type"],
                "recognition_scope": row["scope"],
                "professional_reference": row["professional_reference"],
                "event_type": row["event_type"],
            },
        ))
        stats["relation_created"] += 1
    return edition


def run_import() -> dict:
    master, rows = load_inputs()
    stats: Counter = Counter()
    with SessionLocal() as db:
        register_master(db, master, stats)
        for row in rows:
            school = db.scalar(select(University).where(University.name == row["school"]))
            if school is None:
                raise RuntimeError(f"missing school after master import: {row['school']}")
            college = resolve_college(db, school, row, stats)
            competition = ensure_competition(db, row, stats)
            if competition.name != row["competition"]:
                stats["canonical_alias_reused"] += 1
            edition = None
            if row["relation_type"] == "recognition":
                ensure_recognition(db, school, college, competition, row, stats)
            else:
                edition = ensure_relation(db, school, college, competition, row, stats)
            ensure_source(db, competition, edition, row, stats)
            ensure_fact(db, competition, edition, row, "organizer", {"value": row["organizer"]}, stats)
            ensure_fact(db, competition, edition, row, "event_type", {"value": row["event_type"]}, stats)
            if row["professional_reference"]:
                ensure_fact(db, competition, edition, row, "professional_reference", {
                    "value": True,
                    "institution": row["school"],
                    "scope": row["scope"],
                }, stats)
        db.commit()
    result = {
        "task": TASK,
        "generated_at": now_utc().isoformat(),
        "input": {"master_units": len(master), "verified_rows": len(rows)},
        "stats": dict(sorted(stats.items())),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run_import(), ensure_ascii=False, indent=2))
