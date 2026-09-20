"""Idempotently import verified second-round specialized-institution evidence."""
from __future__ import annotations

import hashlib
import json
import sys
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
    Major,
    PolicyDocument,
    University,
    UniversityCompetitionEditionRelation,
)

SEED = ROOT / "data" / "seeds" / "specialized_institutions_round2_relations.json"


def parse_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def source_hash(*parts: str | None) -> str:
    return hashlib.sha256("\u241f".join(part or "" for part in parts).encode("utf-8")).hexdigest()


def get_scope_entities(db, school: University, row: dict) -> tuple[College | None, Major | None]:
    college = None
    major = None
    if row["scope"] == "college":
        college = db.scalar(
            select(College).where(College.university_id == school.id, College.name == row["department"])
        )
        if college is None:
            domain = urlparse(row["source_url"]).netloc.lower().removeprefix("www.")
            college = College(
                university_id=school.id,
                name=row["department"],
                official_website=f"https://{domain}/",
                official_domain=domain,
                source_url=row["source_url"],
                source_hash=source_hash(row["school"], row["department"], row["source_url"]),
                is_verified=True,
            )
            db.add(college)
            db.flush()
    elif row["scope"] == "major":
        major = db.scalar(select(Major).where(Major.name == row["department"]))
        if major is None:
            major = Major(name=row["department"], discipline_category="体育学", major_category="体育教育")
            db.add(major)
            db.flush()
    return college, major


def ensure_competition(db, row: dict, now: datetime, stats: dict[str, int]) -> Competition:
    competition = db.scalar(select(Competition).where(Competition.name == row["competition"]))
    if competition is None:
        competition = Competition(
            name=row["competition"],
            organizer=row["organizer"],
            category="专业赛事",
            competition_type=row["event_type"],
            entity_type="competition",
            is_competition=True,
            is_cross_major_supported=False,
            is_cross_university_supported=False,
            verification_status="school_confirmed",
            description_source_url=row["source_url"],
            last_verified_at=now,
        )
        db.add(competition)
        db.flush()
        stats["competition_created"] += 1
    else:
        changed = False
        if not competition.organizer:
            competition.organizer = row["organizer"]
            changed = True
        if not competition.description_source_url:
            competition.description_source_url = row["source_url"]
            changed = True
        if changed:
            competition.last_verified_at = now
            stats["competition_updated"] += 1
    return competition


def ensure_source(db, competition: Competition, edition: CompetitionEdition | None, row: dict, now: datetime, stats: dict[str, int]) -> None:
    found = db.scalar(
        select(CompetitionSource).where(
            CompetitionSource.competition_id == competition.id,
            CompetitionSource.source_url == row["source_url"],
            CompetitionSource.source_type == "professional_institution_official",
        )
    )
    if found is None:
        db.add(
            CompetitionSource(
                competition_id=competition.id,
                competition_edition_id=edition.id if edition else None,
                source_type="professional_institution_official",
                authority_level="A2",
                source_name=row["source_name"],
                source_url=row["source_url"],
                source_platform="official_website",
                published_at=parse_date(row["published_at"]),
                retrieved_at=now,
                is_official=True,
                is_verified=True,
                credibility_score=90,
                reliability_tier=2,
                verification_status="verified_official",
                raw_title=row["title"],
                raw_content=row["evidence"],
                content_hash=source_hash(row["source_url"], row["evidence"]),
                metadata_json={"task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01", "round": 2},
            )
        )
        stats["source_created"] += 1


def ensure_fact(db, competition: Competition, edition: CompetitionEdition | None, row: dict, field: str, value, now: datetime, stats: dict[str, int]) -> None:
    fact = db.scalar(
        select(CompetitionFactSource).where(
            CompetitionFactSource.competition_id == competition.id,
            CompetitionFactSource.competition_edition_id == (edition.id if edition else None),
            CompetitionFactSource.field_name == field,
            CompetitionFactSource.source_url == row["source_url"],
        )
    )
    if fact is None:
        db.add(
            CompetitionFactSource(
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
                observed_at=now,
                last_verified_at=now,
                source_hash=source_hash(row["source_url"], field, json.dumps(value, ensure_ascii=False)),
                notes="专业院校官方来源；professional_reference 不等同 national_reference。",
            )
        )
        stats["fact_created"] += 1


def ensure_edition(db, competition: Competition, row: dict, now: datetime, stats: dict[str, int]) -> CompetitionEdition:
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
            edition_name=f"{row['year']}年{row['competition']}",
            source_url=row["source_url"],
            verification_status="school_confirmed",
            is_verified=True,
            last_verified_at=now,
        )
        db.add(edition)
        db.flush()
        stats["edition_created"] += 1
    return edition


def ensure_recognition(db, school: University, competition: Competition, college: College | None, major: Major | None, row: dict, now: datetime, stats: dict[str, int]) -> None:
    document_hash = source_hash(row["source_url"], row["title"])
    document = db.scalar(select(PolicyDocument).where(PolicyDocument.document_hash == document_hash))
    if document is None:
        attachment = row["source_url"] if row["source_url"].lower().split("?")[0].endswith(".pdf") else None
        document = PolicyDocument(
            university_id=school.id,
            college_id=college.id if college else None,
            major_id=major.id if major else None,
            scope_type=row["scope"],
            title=row["title"],
            policy_type="competition_recognition",
            year=row["year"],
            latest_available_year=row["year"],
            publisher=row["source_name"],
            source_url=row["source_url"],
            attachment_url=attachment,
            official_domain=urlparse(row["source_url"]).netloc.lower().removeprefix("www."),
            authority_level="A2",
            published_at=parse_date(row["published_at"]),
            content_text=row["evidence"],
            document_hash=document_hash,
            is_current=True,
            is_verified=True,
            verification_status="verified_official",
            parser_type="manual_official_evidence",
            source_type="university_official",
            metadata_json={
                "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
                "round": 2,
                "recognition_scope": row["scope"],
                "event_type": row["event_type"],
            },
        )
        db.add(document)
        db.flush()
        stats["policy_created"] += 1
    evidence_hash = source_hash(row["evidence"])
    recognition = db.scalar(
        select(CompetitionPolicyRecognition).where(
            CompetitionPolicyRecognition.policy_document_id == document.id,
            CompetitionPolicyRecognition.competition_id == competition.id,
            CompetitionPolicyRecognition.usage_type == "student_development",
            CompetitionPolicyRecognition.evidence_hash == evidence_hash,
        )
    )
    if recognition is None:
        db.add(
            CompetitionPolicyRecognition(
                competition_id=competition.id,
                policy_document_id=document.id,
                university_id=school.id,
                college_id=college.id if college else None,
                major_id=major.id if major else None,
                year=row["year"],
                recognition_status="recognized",
                recognition_level=row["scope"],
                usage_type="student_development",
                evidence_text=row["evidence"],
                evidence_hash=evidence_hash,
                evidence_section="竞赛/实践成果认定",
                confidence=1.0,
                needs_manual_review=False,
            )
        )
        stats["recognition_created"] += 1


def ensure_edition_relation(db, school: University, competition: Competition, college: College | None, row: dict, now: datetime, stats: dict[str, int]) -> CompetitionEdition:
    edition = ensure_edition(db, competition, row, now, stats)
    relation = db.scalar(
        select(UniversityCompetitionEditionRelation).where(
            UniversityCompetitionEditionRelation.university_id == school.id,
            UniversityCompetitionEditionRelation.competition_edition_id == edition.id,
            UniversityCompetitionEditionRelation.internal_notice_url == row["source_url"],
        )
    )
    if relation is None:
        db.add(
            UniversityCompetitionEditionRelation(
                university_id=school.id,
                college_id=college.id if college else None,
                competition_edition_id=edition.id,
                source_type="university_official_notice",
                source_platform="official_website",
                source_name=row["source_name"],
                notice_type="participation_news" if row["relation_type"] == "participation" else "campus_notice",
                notice_title=row["title"],
                internal_notice_url=row["source_url"],
                organizing_department=row["department"],
                published_at=parse_date(row["published_at"]),
                observed_at=now,
                last_verified_at=now,
                verification_status="school_confirmed",
                is_verified=True,
                source_hash=source_hash(row["source_url"], row["title"]),
                metadata_json={
                    "task": "SPECIALIZED_INSTITUTIONS_COVERAGE_01",
                    "round": 2,
                    "relation_type": row["relation_type"],
                    "recognition_scope": row["scope"],
                    "event_type": row["event_type"],
                    "professional_reference": row["professional_reference"],
                },
            )
        )
        stats["relation_created"] += 1
    return edition


def main() -> None:
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    stats = {
        "competition_created": 0,
        "competition_updated": 0,
        "edition_created": 0,
        "relation_created": 0,
        "recognition_created": 0,
        "policy_created": 0,
        "source_created": 0,
        "fact_created": 0,
    }
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for row in rows:
            school = db.scalar(select(University).where(University.name == row["school"]))
            if school is None:
                raise RuntimeError(f"missing school {row['school']}")
            college, major = get_scope_entities(db, school, row)
            competition = ensure_competition(db, row, now, stats)
            edition = None
            if row["relation_type"] == "recognition":
                ensure_recognition(db, school, competition, college, major, row, now, stats)
            else:
                edition = ensure_edition_relation(db, school, competition, college, row, now, stats)
            ensure_source(db, competition, edition, row, now, stats)
            ensure_fact(db, competition, edition, row, "organizer", {"value": row["organizer"]}, now, stats)
            ensure_fact(db, competition, edition, row, "event_type", {"value": row["event_type"]}, now, stats)
            if row["professional_reference"]:
                ensure_fact(
                    db,
                    competition,
                    edition,
                    row,
                    "professional_reference",
                    {"value": True, "institution": row["school"], "scope": row["scope"]},
                    now,
                    stats,
                )
        db.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
