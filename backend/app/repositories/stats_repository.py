from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CandidateCompetition,
    Competition,
    CompetitionEdition,
    CompetitionFactSource,
    CompetitionLead,
    CompetitionPolicyRecognition,
    CompetitionSource,
    CompetitionTag,
    PolicyRawItem,
    PolicyDocument,
    ReviewQueue,
    Tag,
    University,
    UniversityCompetitionDiscoveryReport,
    UniversityCompetitionEditionRelation,
)


class StatsRepository:
    def get_platform_stats(self, db: Session) -> dict[str, int | bool]:
        competitions = db.scalar(
            select(func.count()).select_from(Competition).where(
                Competition.is_demo.is_(False), Competition.is_competition.is_(True)
            )
        ) or 0
        universities = db.scalar(
            select(func.count()).select_from(University).where(University.is_demo.is_(False))
        ) or 0
        policies = db.scalar(
            select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))
        ) or 0
        recognitions = db.scalar(
            select(func.count()).select_from(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.is_demo.is_(False)
            )
        ) or 0
        candidate_competitions = db.scalar(
            select(func.count()).select_from(CandidateCompetition).where(CandidateCompetition.is_demo.is_(False))
        ) or 0
        tags = db.scalar(select(func.count()).select_from(Tag)) or 0
        editions = db.scalar(select(func.count()).select_from(CompetitionEdition)) or 0
        verified_editions = db.scalar(
            select(func.count()).select_from(CompetitionEdition).where(CompetitionEdition.is_verified.is_(True))
        ) or 0
        registration_open = db.scalar(
            select(func.count()).select_from(CompetitionEdition).where(
                CompetitionEdition.is_verified.is_(True),
                CompetitionEdition.current_status == "registration_open",
                CompetitionEdition.registration_deadline >= datetime.now(timezone.utc),
            )
        ) or 0
        submission_open = db.scalar(
            select(func.count()).select_from(CompetitionEdition).where(
                CompetitionEdition.is_verified.is_(True),
                CompetitionEdition.current_status == "submission_open",
                CompetitionEdition.submission_deadline >= datetime.now(timezone.utc),
            )
        ) or 0
        tagged_competitions = db.scalar(
            select(func.count(func.distinct(CompetitionTag.competition_id)))
            .select_from(CompetitionTag)
            .join(Competition, Competition.id == CompetitionTag.competition_id)
            .where(Competition.is_competition.is_(True), Competition.is_demo.is_(False))
        ) or 0
        github_seed_sources = db.scalar(
            select(func.count()).select_from(CompetitionSource).where(CompetitionSource.source_type == "github_seed")
        ) or 0
        leads = list(db.execute(select(CompetitionLead)).scalars())
        source_distribution = {
            "university_official": sum(lead.source_type == "university_official" for lead in leads),
            "third_party_platform": sum(lead.source_type == "third_party_platform" for lead in leads),
            "source_repository_discovery": sum(lead.source_type == "source_repository_discovery" for lead in leads),
            "social": sum(lead.source_type == "social" for lead in leads),
            "wechat": sum("wechat" in (lead.source_platform or "").lower() for lead in leads),
        }
        university_names = {
            (lead.metadata_json or {}).get("university")
            for lead in leads
            if lead.source_type == "university_official" and (lead.metadata_json or {}).get("university")
        }
        discovery_reports = list(
            db.execute(
                select(UniversityCompetitionDiscoveryReport)
                .join(University, University.id == UniversityCompetitionDiscoveryReport.university_id)
                .where(University.is_985.is_(True), University.is_demo.is_(False))
            ).scalars()
        )
        latest_discovery_reports: dict[int, UniversityCompetitionDiscoveryReport] = {}
        for report in sorted(
            discovery_reports,
            key=lambda item: item.last_crawled_at or item.updated_at,
            reverse=True,
        ):
            latest_discovery_reports.setdefault(report.university_id, report)
        current_discovery_reports = list(latest_discovery_reports.values())
        scanned_reports = [
            report
            for report in current_discovery_reports
            if report.status in {"completed", "partial", "failed", "blocked"}
        ]
        relation_rows = list(
            db.execute(
                select(UniversityCompetitionEditionRelation, CompetitionEdition)
                .join(CompetitionEdition, CompetitionEdition.id == UniversityCompetitionEditionRelation.competition_edition_id)
                .where(UniversityCompetitionEditionRelation.is_demo.is_(False))
            ).all()
        )
        universities_985_seeded = db.scalar(
            select(func.count()).select_from(University).where(University.is_985.is_(True), University.is_demo.is_(False))
        ) or 0
        real_policy_documents = db.scalar(
            select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False))
        ) or 0
        verified_policy_documents = db.scalar(
            select(func.count()).select_from(PolicyDocument).where(
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.is_verified.is_(True),
            )
        ) or 0
        college_policy_documents = db.scalar(
            select(func.count()).select_from(PolicyDocument).where(
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.scope_type == "college",
            )
        ) or 0
        review_queue_pending = db.scalar(
            select(func.count()).select_from(ReviewQueue).where(
                ReviewQueue.is_demo.is_(False),
                ReviewQueue.status == "pending",
            )
        ) or 0
        universities_with_real_policy = db.scalar(
            select(func.count(func.distinct(PolicyDocument.university_id)))
            .select_from(PolicyDocument)
            .join(University, University.id == PolicyDocument.university_id)
            .where(
                University.is_985.is_(True),
                University.is_demo.is_(False),
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.is_verified.is_(True),
            )
        ) or 0
        return {
            "competitions": competitions,
            "universities": universities,
            "policies": policies,
            "recognitions": recognitions,
            "tags": tags,
            "universities_985_total": 39,
            "universities_985_seeded": universities_985_seeded,
            "real_policy_documents": real_policy_documents,
            "verified_policy_documents": verified_policy_documents,
            "college_policy_documents": college_policy_documents,
            "review_queue_pending": review_queue_pending,
            "universities_with_real_policy": universities_with_real_policy,
            "candidate_competitions": candidate_competitions,
            "editions": editions,
            "verified_editions": verified_editions,
            "registration_open": registration_open,
            "submission_open": submission_open,
            "tagged_competitions": tagged_competitions,
            "github_seed_sources": github_seed_sources,
            "competition_leads": len(leads),
            "github_discovery_leads": sum(
                (lead.metadata_json or {}).get("repository") == "Nemoyuzx/contest-ddl" for lead in leads
            ),
            "university_official_leads": source_distribution["university_official"],
            "third_party_platform_leads": source_distribution["third_party_platform"],
            "wechat_leads": source_distribution["wechat"],
            "social_leads": source_distribution["social"],
            "universities_crawled": len({report.university_id for report in scanned_reports}) or len(university_names),
            "competition_discovery_scanned_985": len({report.university_id for report in scanned_reports}),
            "competition_discovery_completed_985": len(
                {report.university_id for report in current_discovery_reports if report.status == "completed"}
            ),
            "competition_discovery_partial_985": len(
                {report.university_id for report in current_discovery_reports if report.status == "partial"}
            ),
            "competition_discovery_failed_985": len(
                {report.university_id for report in current_discovery_reports if report.status == "failed"}
            ),
            "competition_discovery_blocked_985": len(
                {report.university_id for report in current_discovery_reports if report.status == "blocked"}
            ),
            "universities_with_competition_leads": len(
                {report.university_id for report in current_discovery_reports if report.competition_leads > 0}
            ) or len(university_names),
            "universities_with_competitions": len(
                {report.university_id for report in current_discovery_reports if report.matched_competitions > 0}
            ),
            "universities_with_2026_editions": len(
                {
                    relation.university_id
                    for relation, edition in relation_rows
                    if edition.year == 2026
                }
            ),
            "university_competition_notices": sum(
                1 for relation, _ in relation_rows if relation.college_id is None
            ),
            "college_competition_notices": sum(
                1 for relation, _ in relation_rows if relation.college_id is not None
            ),
            "internal_deadline_count": sum(
                1 for relation, _ in relation_rows if relation.internal_registration_deadline is not None
            ),
            "official_registration_deadline_count": db.scalar(
                select(func.count()).select_from(CompetitionEdition).where(
                    CompetitionEdition.official_registration_deadline.is_not(None)
                )
            ) or 0,
            "registration_notice_count": sum(
                1 for relation, _ in relation_rows if relation.notice_type == "registration_notice"
            ),
            "internal_selection_count": sum(
                1 for relation, _ in relation_rows if relation.notice_type == "internal_selection"
            ),
            "submission_notice_count": sum(
                1 for relation, _ in relation_rows if relation.notice_type == "submission_notice"
            ),
            "non_action_notice_count": sum(
                1
                for relation, _ in relation_rows
                if relation.notice_type not in {"registration_notice", "internal_selection", "submission_notice"}
            ),
            "competitions_with_description": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True), Competition.description.is_not(None)
                )
            ) or 0,
            "competitions_with_organizer": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True), Competition.organizer.is_not(None)
                )
            ) or 0,
            "competitions_with_official_website": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True), Competition.official_website.is_not(None)
                )
            ) or 0,
            "competitions_with_founded_year": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True), Competition.founded_year.is_not(None)
                )
            ) or 0,
            "field_fact_sources": db.scalar(select(func.count()).select_from(CompetitionFactSource)) or 0,
            "detail_ready_competitions": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True), Competition.detail_ready.is_(True)
                )
            ) or 0,
            "competitions_with_history_timeline": db.scalar(
                select(func.count()).select_from(Competition).where(Competition.history_timeline.is_not(None))
            ) or 0,
            "competitions_with_participation_requirements": db.scalar(
                select(func.count()).select_from(Competition).where(Competition.participation_requirements.is_not(None))
            ) or 0,
            "competitions_with_competition_process": db.scalar(
                select(func.count()).select_from(Competition).where(Competition.competition_process.is_not(None))
            ) or 0,
            "competitions_with_submission_requirements": db.scalar(
                select(func.count()).select_from(Competition).where(Competition.submission_requirements.is_not(None))
            ) or 0,
            "competitions_with_award_settings": db.scalar(
                select(func.count()).select_from(Competition).where(Competition.award_settings.is_not(None))
            ) or 0,
            "editions_with_fee_information": db.scalar(
                select(func.count()).select_from(CompetitionEdition).where(
                    (CompetitionEdition.registration_fee.is_not(None)) | (CompetitionEdition.fee_notes.is_not(None))
                )
            ) or 0,
            "policy_raw_items": db.scalar(select(func.count()).select_from(PolicyRawItem)) or 0,
            "verified_official_competitions": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True),
                    Competition.verification_status == "verified_official",
                )
            ) or 0,
            "verified_multi_source_competitions": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True),
                    Competition.verification_status == "verified_multi_source",
                )
            ) or 0,
            "secondary_source_only_competitions": db.scalar(
                select(func.count()).select_from(Competition).where(
                    Competition.is_competition.is_(True),
                    Competition.verification_status == "secondary_source_only",
                )
            ) or 0,
            "source_distribution": source_distribution,
            "demo_data": policies == 0 or competitions == 0 or recognitions == 0,
        }
