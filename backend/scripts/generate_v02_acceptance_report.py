import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    CandidateCompetition,
    Competition,
    CompetitionPolicyRecognition,
    CompetitionStatistics,
    PolicyAttachment,
    PolicyDocument,
    University,
)

ROOT_DIR = BACKEND_DIR.parent
REPORT_PATH = ROOT_DIR / "data" / "reports" / "v02_acceptance_report.json"
FIRST_BATCH = ["清华大学", "北京大学", "浙江大学", "武汉大学", "华中科技大学"]


def count(db, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def university_chain(db, name: str) -> dict:
    university = db.execute(select(University).where(University.name == name)).scalar_one()
    policy_ids = select(PolicyDocument.id).where(
        PolicyDocument.university_id == university.id,
        PolicyDocument.is_demo.is_(False),
        PolicyDocument.is_verified.is_(True),
    )
    return {
        "university": university.name,
        "is_985": university.is_985,
        "crawl_status": university.policy_crawl_status,
        "policy_documents": count(
            db,
            PolicyDocument,
            PolicyDocument.university_id == university.id,
            PolicyDocument.is_demo.is_(False),
        ),
        "candidates": count(
            db,
            CandidateCompetition,
            CandidateCompetition.university_id == university.id,
            CandidateCompetition.is_demo.is_(False),
        ),
        "competitions": int(
            db.scalar(
                select(func.count(func.distinct(CandidateCompetition.normalized_competition_id))).where(
                    CandidateCompetition.university_id == university.id,
                    CandidateCompetition.is_demo.is_(False),
                    CandidateCompetition.normalized_competition_id.is_not(None),
                )
            )
            or 0
        ),
        "recognitions": count(
            db,
            CompetitionPolicyRecognition,
            CompetitionPolicyRecognition.university_id == university.id,
            CompetitionPolicyRecognition.is_demo.is_(False),
        ),
        "source_urls": list(
            db.execute(select(PolicyDocument.source_url).where(PolicyDocument.id.in_(policy_ids))).scalars()
        ),
    }


def main() -> None:
    db = SessionLocal()
    try:
        real_conditions = lambda model: model.is_demo.is_(False)
        policy_985_coverage = int(
            db.scalar(
                select(func.count(func.distinct(PolicyDocument.university_id)))
                .join(University, University.id == PolicyDocument.university_id)
                .where(
                    University.is_985.is_(True),
                    PolicyDocument.is_demo.is_(False),
                    PolicyDocument.is_verified.is_(True),
                )
            )
            or 0
        )
        top_rows = db.execute(
            select(Competition, CompetitionStatistics)
            .join(CompetitionStatistics, CompetitionStatistics.competition_id == Competition.id)
            .where(Competition.is_demo.is_(False))
            .order_by(CompetitionStatistics.priority_score.desc(), Competition.id.asc())
            .limit(10)
        ).all()
        top_competitions = [
            {
                "competition_id": competition.id,
                "name": competition.name,
                "priority_score": statistics.priority_score,
                "985_university_recognitions": statistics.university_985_recognition_count,
                "985_college_recognitions": statistics.college_985_recognition_count,
                "policy_references": statistics.policy_reference_count,
                "latest_policy_year": statistics.latest_policy_year,
                "official_sources": statistics.official_source_count,
            }
            for competition, statistics in top_rows
        ]
        first_batch_rows = list(
            db.execute(select(University).where(University.name.in_(FIRST_BATCH))).scalars()
        )
        first_batch_rows.sort(key=lambda university: FIRST_BATCH.index(university.name))
        first_batch = [
            {
                "university": university.name,
                "status": university.policy_crawl_status,
                "last_crawl_at": university.last_policy_crawl_at.isoformat() if university.last_policy_crawl_at else None,
                "reason": university.policy_crawl_error,
            }
            for university in first_batch_rows
        ]
        documents = list(
            db.execute(select(PolicyDocument).where(PolicyDocument.is_demo.is_(False)).order_by(PolicyDocument.id)).scalars()
        )
        policy_sources = []
        for document in documents:
            attachment = db.execute(
                select(PolicyAttachment).where(PolicyAttachment.policy_document_id == document.id)
            ).scalar_one_or_none()
            policy_sources.append(
                {
                    "policy_document_id": document.id,
                    "title": document.title,
                    "university": document.university.name,
                    "college": document.college.name if document.college else None,
                    "scope_type": document.scope_type,
                    "source_url": document.source_url,
                    "attachment_url": document.attachment_url,
                    "document_hash": document.document_hash,
                    "parser_type": document.parser_type,
                    "verification_status": document.verification_status,
                    "attachment_parse_status": attachment.parse_status if attachment else None,
                }
            )

        whu_chain = university_chain(db, "武汉大学")
        whsu_chain = university_chain(db, "武汉体育学院")
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "985_directory": count(
                    db,
                    University,
                    University.is_985.is_(True),
                    University.is_demo.is_(False),
                ),
                "985_policy_coverage": policy_985_coverage,
                "universities": count(db, University, real_conditions(University)),
                "policy_documents": count(db, PolicyDocument, real_conditions(PolicyDocument)),
                "verified_policy_documents": count(
                    db,
                    PolicyDocument,
                    real_conditions(PolicyDocument),
                    PolicyDocument.is_verified.is_(True),
                ),
                "candidate_competitions": count(
                    db,
                    CandidateCompetition,
                    real_conditions(CandidateCompetition),
                ),
                "competitions": count(db, Competition, real_conditions(Competition)),
                "recognitions": count(
                    db,
                    CompetitionPolicyRecognition,
                    real_conditions(CompetitionPolicyRecognition),
                ),
            },
            "acceptance": {
                "one_real_985_policy_chain": all(
                    whu_chain[key] > 0 for key in ("policy_documents", "candidates", "competitions", "recognitions")
                ),
                "wuhan_university_chain": whu_chain,
                "non_985_hierarchy_sample": whsu_chain,
            },
            "top_10_competitions": top_competitions,
            "first_batch": first_batch,
            "failures_or_partial": [row for row in first_batch if row["status"] != "completed"],
            "policy_sources": policy_sources,
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
