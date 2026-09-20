"""Idempotent importer for verified P0 specialized-school facts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models import Competition, CompetitionEdition, CompetitionFactSource, University, UniversityCompetitionEditionRelation

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "seeds" / "specialized_institutions_p0_relations.json"


def dt(value: str | None):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def main() -> None:
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    stats = {"competition_created":0,"edition_created":0,"relation_created":0,"fact_created":0,"skipped":0}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for row in rows:
            school = db.scalar(select(University).where(University.name == row["school"]))
            if not school:
                raise RuntimeError(f"missing school {row['school']}")
            competition = db.scalar(select(Competition).where(Competition.name == row["competition"]))
            if not competition:
                competition = Competition(
                    name=row["competition"], category="专业赛事", competition_type="competition",
                    entity_type="competition", is_competition=True, is_cross_major_supported=False,
                    is_cross_university_supported=False, verification_status="school_confirmed",
                    description_source_url=row["source_url"], last_verified_at=now,
                )
                db.add(competition); db.flush(); stats["competition_created"] += 1
            edition = db.scalar(select(CompetitionEdition).where(
                CompetitionEdition.competition_id == competition.id,
                CompetitionEdition.year == row["year"],
            ))
            if not edition:
                edition = CompetitionEdition(
                    competition_id=competition.id, year=row["year"],
                    edition_name=f"{row['year']}年{row['competition']}", source_url=row["source_url"],
                    verification_status="school_confirmed", is_verified=True, last_verified_at=now,
                )
                db.add(edition); db.flush(); stats["edition_created"] += 1
            exists = db.scalar(select(UniversityCompetitionEditionRelation).where(
                UniversityCompetitionEditionRelation.university_id == school.id,
                UniversityCompetitionEditionRelation.competition_edition_id == edition.id,
                UniversityCompetitionEditionRelation.internal_notice_url == row["source_url"],
            ))
            if exists:
                stats["skipped"] += 1
            else:
                notice_type = "participation_news" if row["relation_type"] == "participation" else "campus_notice"
                db.add(UniversityCompetitionEditionRelation(
                    university_id=school.id, competition_edition_id=edition.id,
                    source_type="university_official_notice", source_platform="official_website",
                    source_name=row["source_name"], notice_type=notice_type, notice_title=row["title"],
                    internal_notice_url=row["source_url"], organizing_department=row["department"],
                    published_at=dt(row["published_at"]), observed_at=now, last_verified_at=now,
                    verification_status="school_confirmed", is_verified=True,
                    source_hash=hashlib.sha256((row["source_url"]+row["title"]).encode()).hexdigest(),
                    metadata_json={"task":"SPECIALIZED_INSTITUTIONS_COVERAGE_01","relation_type":row["relation_type"],"recognition_scope":row["scope"],"event_type":row["event_type"],"professional_reference":row["professional_reference"]},
                )); stats["relation_created"] += 1
            if row["professional_reference"]:
                fact = db.scalar(select(CompetitionFactSource).where(
                    CompetitionFactSource.competition_id == competition.id,
                    CompetitionFactSource.field_name == "professional_reference",
                    CompetitionFactSource.source_url == row["source_url"],
                ))
                if not fact:
                    db.add(CompetitionFactSource(
                        competition_id=competition.id, competition_edition_id=edition.id,
                        field_name="professional_reference", fact_value={"value":True,"institution":row["school"],"scope":row["scope"]},
                        source_type="professional_institution_official", source_name=row["source_name"],
                        source_url=row["source_url"], reliability_tier=2, source_level="B",
                        is_official=True, verification_status="school_confirmed", published_at=dt(row["published_at"]),
                        observed_at=now, last_verified_at=now, notes="专业院校官方制度/通知证据；不等同 national_reference。",
                    )); stats["fact_created"] += 1
        db.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
