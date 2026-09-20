import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models import (
    Competition,
    CompetitionAlias,
    CompetitionEdition,
    CompetitionPolicyRecognition,
    CompetitionSource,
    CompetitionStatistics,
    PolicyDocument,
    Tag,
    University,
)

PROJECT_ROOT = BACKEND_DIR.parent
REPORT_PATH = PROJECT_ROOT / "data" / "reports" / "competition_product_acceptance_report.json"
BASELINE_COMPETITIONS = 97
GITHUB_REPOSITORY = "Tomzkl/college-competitions-skill"
GITHUB_COMMIT = "98da22d75b23c059c77d69d24a650b48553d7492"


def count(db, model, *conditions) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def main() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    in_30_days = now + timedelta(days=30)

    with SessionLocal() as db:
        competition_count = count(db, Competition, Competition.is_demo.is_(False))
        github_sources = list(
            db.execute(
                select(CompetitionSource, Competition)
                .join(Competition, Competition.id == CompetitionSource.competition_id)
                .where(
                    CompetitionSource.source_type == "github_seed",
                    CompetitionSource.is_demo.is_(False),
                )
                .order_by(Competition.id)
            ).all()
        )
        policy_documents = list(
            db.execute(
                select(PolicyDocument, University)
                .join(University, University.id == PolicyDocument.university_id)
                .where(PolicyDocument.is_demo.is_(False))
                .order_by(PolicyDocument.id)
            ).all()
        )
        tagged_competitions = int(
            db.scalar(
                select(func.count(func.distinct(Competition.id)))
                .select_from(Competition)
                .join(Competition.tags)
                .where(Competition.is_demo.is_(False))
            )
            or 0
        )
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
        current_editions = list(
            db.execute(
                select(CompetitionEdition, Competition, CompetitionStatistics)
                .join(Competition, Competition.id == CompetitionEdition.competition_id)
                .outerjoin(CompetitionStatistics, CompetitionStatistics.competition_id == Competition.id)
                .where(
                    CompetitionEdition.is_verified.is_(True),
                    CompetitionEdition.current_status.in_(("registration_open", "upcoming")),
                    CompetitionEdition.registration_deadline.is_not(None),
                    CompetitionEdition.registration_deadline >= now,
                )
                .order_by(CompetitionEdition.registration_deadline, Competition.id)
            ).all()
        )
        pending_competitions = list(
            db.execute(
                select(Competition)
                .where(
                    Competition.is_demo.is_(False),
                    ~Competition.editions.any(CompetitionEdition.is_verified.is_(True)),
                )
                .order_by(Competition.id)
            ).scalars()
        )
        top_priority = list(
            db.execute(
                select(Competition, CompetitionStatistics)
                .join(CompetitionStatistics, CompetitionStatistics.competition_id == Competition.id)
                .where(Competition.is_demo.is_(False))
                .order_by(CompetitionStatistics.priority_score.desc(), Competition.id)
                .limit(10)
            ).all()
        )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": {"competitions": BASELINE_COMPETITIONS},
            "acceptance": {
                "01_current_competitions": competition_count,
                "02_new_competitions": competition_count - BASELINE_COMPETITIONS,
                "03_github_seed_imported": len(github_sources),
                "04_competition_aliases": count(
                    db, CompetitionAlias, CompetitionAlias.is_demo.is_(False)
                ),
                "05_parent_child_competitions": {
                    "parents": count(
                        db,
                        Competition,
                        Competition.is_demo.is_(False),
                        Competition.competition_type == "series",
                    ),
                    "children": count(
                        db,
                        Competition,
                        Competition.is_demo.is_(False),
                        Competition.parent_competition_id.is_not(None),
                    ),
                },
                "06_tags": count(db, Tag),
                "07_classified_competition_ratio": {
                    "tagged": tagged_competitions,
                    "total": competition_count,
                    "percentage": round(tagged_competitions / competition_count * 100, 2)
                    if competition_count
                    else 0,
                },
                "08_policy_documents": len(policy_documents),
                "09_recognitions": count(
                    db,
                    CompetitionPolicyRecognition,
                    CompetitionPolicyRecognition.is_demo.is_(False),
                ),
                "10_985_policy_coverage": f"{policy_985_coverage}/39",
                "11_competition_editions": count(db, CompetitionEdition),
                "12_2026_editions": count(db, CompetitionEdition, CompetitionEdition.year == 2026),
                "13_registration_open": count(
                    db,
                    CompetitionEdition,
                    CompetitionEdition.is_verified.is_(True),
                    CompetitionEdition.current_status == "registration_open",
                    CompetitionEdition.registration_deadline >= now,
                ),
                "14_deadline_within_30_days": count(
                    db,
                    CompetitionEdition,
                    CompetitionEdition.is_verified.is_(True),
                    CompetitionEdition.registration_deadline >= now,
                    CompetitionEdition.registration_deadline <= in_30_days,
                ),
                "15_officially_verified_competitions": count(
                    db,
                    Competition,
                    Competition.is_demo.is_(False),
                    Competition.is_official_verified.is_(True),
                ),
                "16_home_actionable_competitions": [
                    {
                        "name": competition.name,
                        "status": edition.current_status,
                        "registration_deadline": edition.registration_deadline.isoformat(),
                        "priority_score": statistics.priority_score if statistics else 0,
                    }
                    for edition, competition, statistics in current_editions
                ],
                "17_pending_official_edition": {
                    "count": len(pending_competitions),
                    "competitions": [competition.name for competition in pending_competitions],
                },
                "18_github_sources": {
                    "repository": GITHUB_REPOSITORY,
                    "commit": GITHUB_COMMIT,
                    "license": "MIT",
                    "verified_as_official": False,
                    "records": [
                        {
                            "competition_id": competition.id,
                            "competition_name": competition.name,
                            "raw_title": source.raw_title,
                            "source_url": source.source_url,
                            "source_file": source.source_file,
                        }
                        for source, competition in github_sources
                    ],
                },
                "19_formal_university_or_college_sources": [
                    {
                        "title": document.title,
                        "university": university.name,
                        "scope_type": document.scope_type,
                        "year": document.year,
                        "source_url": document.source_url,
                        "is_verified": document.is_verified,
                        "recognitions": count(
                            db,
                            CompetitionPolicyRecognition,
                            CompetitionPolicyRecognition.policy_document_id == document.id,
                            CompetitionPolicyRecognition.is_demo.is_(False),
                        ),
                    }
                    for document, university in policy_documents
                ],
                "20_next_stage_recommendations": [
                    "优先补齐首页高优先级赛事的2026官方通知与报名截止时间。",
                    "继续推进39所985高校政策覆盖，但不阻塞竞赛发现主链路。",
                    "将学校、学院、专业和年级条件接入推荐评分与认可证据。",
                    "为待核验Seed建立人工审核队列，禁止由GitHub线索直接生成学校认可。",
                ],
            },
            "top_10_priority": [
                {
                    "competition_id": competition.id,
                    "name": competition.name,
                    "priority_score": statistics.priority_score,
                    "score_breakdown": statistics.score_breakdown,
                }
                for competition, statistics in top_priority
            ],
        }

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
