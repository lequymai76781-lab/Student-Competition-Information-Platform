from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CandidateCompetition,
    College,
    Competition,
    CompetitionPolicyRecognition,
    CrawlerJob,
    Major,
    PolicyDocument,
    ReviewQueue,
    University,
)


class PolicyRepository:
    def list_documents(
        self,
        db: Session,
        *,
        university_id: int | None = None,
        scope_type: str | None = None,
        policy_type: str | None = None,
        year: int | None = None,
        include_demo: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = (
            select(PolicyDocument, University.name, College.name, Major.name)
            .join(University, University.id == PolicyDocument.university_id)
            .outerjoin(College, College.id == PolicyDocument.college_id)
            .outerjoin(Major, Major.id == PolicyDocument.major_id)
        )
        if university_id is not None:
            stmt = stmt.where(PolicyDocument.university_id == university_id)
        if scope_type:
            stmt = stmt.where(PolicyDocument.scope_type == scope_type)
        if policy_type:
            stmt = stmt.where(PolicyDocument.policy_type == policy_type)
        if year is not None:
            stmt = stmt.where(PolicyDocument.year == year)
        if not include_demo:
            stmt = stmt.where(PolicyDocument.is_demo.is_(False))

        stmt = stmt.order_by(
            PolicyDocument.is_current.desc(),
            PolicyDocument.year.desc().nullslast(),
            PolicyDocument.updated_at.desc(),
        ).offset(offset).limit(limit)
        return [self._document_row(document, university_name, college_name, major_name) for document, university_name, college_name, major_name in db.execute(stmt).all()]

    def list_recognitions(
        self,
        db: Session,
        *,
        competition_id: int | None = None,
        university_id: int | None = None,
        recognition_status: str | None = None,
        include_demo: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = (
            select(
                CompetitionPolicyRecognition,
                Competition.name,
                PolicyDocument.title,
                University.name,
                College.name,
                Major.name,
            )
            .join(Competition, Competition.id == CompetitionPolicyRecognition.competition_id)
            .join(PolicyDocument, PolicyDocument.id == CompetitionPolicyRecognition.policy_document_id)
            .join(University, University.id == CompetitionPolicyRecognition.university_id)
            .outerjoin(College, College.id == CompetitionPolicyRecognition.college_id)
            .outerjoin(Major, Major.id == CompetitionPolicyRecognition.major_id)
        )
        if competition_id is not None:
            stmt = stmt.where(CompetitionPolicyRecognition.competition_id == competition_id)
        if university_id is not None:
            stmt = stmt.where(CompetitionPolicyRecognition.university_id == university_id)
        if recognition_status:
            stmt = stmt.where(CompetitionPolicyRecognition.recognition_status == recognition_status)
        if not include_demo:
            stmt = stmt.where(CompetitionPolicyRecognition.is_demo.is_(False))

        stmt = stmt.order_by(
            CompetitionPolicyRecognition.year.desc().nullslast(),
            CompetitionPolicyRecognition.confidence.desc(),
            Competition.name.asc(),
        ).offset(offset).limit(limit)

        rows = db.execute(stmt).all()
        return [
            self._recognition_row(recognition, competition_name, policy_title, university_name, college_name, major_name)
            for recognition, competition_name, policy_title, university_name, college_name, major_name in rows
        ]

    def list_jobs(
        self,
        db: Session,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrawlerJob]:
        stmt = select(CrawlerJob)
        if status:
            stmt = stmt.where(CrawlerJob.status == status)
        stmt = stmt.order_by(CrawlerJob.created_at.desc()).offset(offset).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def list_review_queue(
        self,
        db: Session,
        *,
        status: str = "pending",
        university_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = select(ReviewQueue, University.name).outerjoin(University, University.id == ReviewQueue.university_id)
        if status:
            stmt = stmt.where(ReviewQueue.status == status)
        if university_id is not None:
            stmt = stmt.where(ReviewQueue.university_id == university_id)
        stmt = stmt.order_by(ReviewQueue.created_at.desc()).offset(offset).limit(limit)
        return [self._review_row(item, university_name) for item, university_name in db.execute(stmt).all()]

    def get_985_progress(self, db: Session) -> list[dict]:
        universities = list(
            db.execute(select(University).where(University.is_985.is_(True)).order_by(University.name.asc()))
            .scalars()
            .all()
        )
        progress: list[dict] = []
        for university in universities:
            policy_count = self._count(
                db,
                select(func.count()).select_from(PolicyDocument).where(
                    PolicyDocument.university_id == university.id,
                    PolicyDocument.is_demo.is_(False),
                ),
            )
            verified_count = self._count(
                db,
                select(func.count()).select_from(PolicyDocument).where(
                    PolicyDocument.university_id == university.id,
                    PolicyDocument.is_demo.is_(False),
                    PolicyDocument.is_verified.is_(True),
                ),
            )
            recognition_count = self._count(
                db,
                select(func.count()).select_from(CompetitionPolicyRecognition).where(
                    CompetitionPolicyRecognition.university_id == university.id,
                    CompetitionPolicyRecognition.is_demo.is_(False),
                ),
            )
            parsed_count = self._count(
                db,
                select(func.count()).select_from(PolicyDocument).where(
                    PolicyDocument.university_id == university.id,
                    PolicyDocument.is_demo.is_(False),
                    PolicyDocument.parser_type.is_not(None),
                ),
            )
            competition_count = self._count(
                db,
                select(func.count(func.distinct(CandidateCompetition.normalized_competition_id))).where(
                    CandidateCompetition.university_id == university.id,
                    CandidateCompetition.is_demo.is_(False),
                    CandidateCompetition.normalized_competition_id.is_not(None),
                ),
            )
            review_pending_count = self._count(
                db,
                select(func.count()).select_from(ReviewQueue).where(
                    ReviewQueue.university_id == university.id,
                    ReviewQueue.status == "pending",
                    ReviewQueue.is_demo.is_(False),
                ),
            )
            college_count = self._count(
                db,
                select(func.count()).select_from(College).where(College.university_id == university.id),
            )
            latest_year = db.scalar(
                select(func.max(PolicyDocument.year)).where(
                    PolicyDocument.university_id == university.id,
                    PolicyDocument.is_demo.is_(False),
                )
            )
            progress.append(
                {
                    "university_id": university.id,
                    "university_name": university.name,
                    "short_name": university.short_name,
                    "province": university.province,
                    "city": university.city,
                    "official_domain": university.official_domain,
                    "seeded": True,
                    "college_count": college_count,
                    "policy_documents_count": policy_count,
                    "verified_policy_documents_count": verified_count,
                    "parsed_policy_documents_count": parsed_count,
                    "competition_count": competition_count,
                    "recognition_count": recognition_count,
                    "review_pending_count": review_pending_count,
                    "latest_policy_year": latest_year,
                    "last_policy_crawl_at": self._as_utc(university.last_policy_crawl_at),
                    "crawl_status": university.policy_crawl_status,
                    "crawl_error": university.policy_crawl_error,
                }
            )
        return progress

    def coverage_summary(self, db: Session) -> dict:
        progress = self.get_985_progress(db)
        real_policy_documents = self._count(
            db,
            select(func.count()).select_from(PolicyDocument).where(PolicyDocument.is_demo.is_(False)),
        )
        verified_policy_documents = self._count(
            db,
            select(func.count()).select_from(PolicyDocument).where(
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.is_verified.is_(True),
            ),
        )
        college_policy_documents = self._count(
            db,
            select(func.count()).select_from(PolicyDocument).where(
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.scope_type == "college",
            ),
        )
        parsed_college_policy_documents = self._count(
            db,
            select(func.count()).select_from(PolicyDocument).where(
                PolicyDocument.is_demo.is_(False),
                PolicyDocument.scope_type == "college",
                PolicyDocument.parser_type.is_not(None),
            ),
        )
        candidate_competitions = self._count(
            db,
            select(func.count()).select_from(CandidateCompetition).where(CandidateCompetition.is_demo.is_(False)),
        )
        competitions = self._count(
            db,
            select(func.count(func.distinct(CandidateCompetition.normalized_competition_id))).where(
                CandidateCompetition.is_demo.is_(False),
                CandidateCompetition.normalized_competition_id.is_not(None),
            ),
        )
        recognitions = self._count(
            db,
            select(func.count()).select_from(CompetitionPolicyRecognition).where(
                CompetitionPolicyRecognition.is_demo.is_(False)
            ),
        )
        review_queue_pending = self._count(
            db,
            select(func.count()).select_from(ReviewQueue).where(
                ReviewQueue.status == "pending",
                ReviewQueue.is_demo.is_(False),
            ),
        )
        return {
            "universities_985_total": 39,
            "universities_985_seeded": len(progress),
            "universities_with_real_policy": sum(
                1 for item in progress if item["verified_policy_documents_count"] > 0
            ),
            "real_policy_documents": real_policy_documents,
            "verified_policy_documents": verified_policy_documents,
            "college_policy_documents": college_policy_documents,
            "parsed_college_policy_documents": parsed_college_policy_documents,
            "candidate_competitions": candidate_competitions,
            "competitions": competitions,
            "recognitions": recognitions,
            "review_queue_pending": review_queue_pending,
            "progress": progress,
        }

    def _document_row(self, document: PolicyDocument, university_name: str, college_name: str | None, major_name: str | None) -> dict:
        text = document.content_text or ""
        return {
            "id": document.id,
            "university_id": document.university_id,
            "university_name": university_name,
            "college_id": document.college_id,
            "college_name": college_name,
            "major_id": document.major_id,
            "major_name": major_name,
            "scope_type": document.scope_type,
            "title": document.title,
            "policy_type": document.policy_type,
            "year": document.year,
            "latest_available_year": document.latest_available_year,
            "publisher": document.publisher,
            "source_url": document.source_url,
            "attachment_url": document.attachment_url,
            "original_filename": document.original_filename,
            "official_domain": document.official_domain,
            "authority_level": document.authority_level,
            "published_at": document.published_at,
            "effective_from": document.effective_from,
            "effective_until": document.effective_until,
            "content_excerpt": text[:320] if text else None,
            "document_hash": document.document_hash,
            "is_current": document.is_current,
            "is_verified": document.is_verified,
            "verification_status": document.verification_status,
            "crawler_job_id": document.crawler_job_id,
            "parser_type": document.parser_type,
            "source_type": document.source_type,
            "is_demo": document.is_demo,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    def _recognition_row(
        self,
        recognition: CompetitionPolicyRecognition,
        competition_name: str,
        policy_title: str,
        university_name: str,
        college_name: str | None,
        major_name: str | None,
    ) -> dict:
        return {
            "id": recognition.id,
            "competition_id": recognition.competition_id,
            "competition_name": competition_name,
            "policy_document_id": recognition.policy_document_id,
            "policy_title": policy_title,
            "university_id": recognition.university_id,
            "university_name": university_name,
            "college_id": recognition.college_id,
            "college_name": college_name,
            "major_id": recognition.major_id,
            "major_name": major_name,
            "year": recognition.year,
            "recognition_status": recognition.recognition_status,
            "recognition_level": recognition.recognition_level,
            "award_requirement": recognition.award_requirement,
            "usage_type": recognition.usage_type,
            "score_text": recognition.score_text,
            "score_numeric": recognition.score_numeric,
            "rank_requirement": recognition.rank_requirement,
            "evidence_text": recognition.evidence_text,
            "evidence_page": recognition.evidence_page,
            "evidence_section": recognition.evidence_section,
            "confidence": recognition.confidence,
            "needs_manual_review": recognition.needs_manual_review,
            "is_demo": recognition.is_demo,
            "created_at": recognition.created_at,
            "updated_at": recognition.updated_at,
        }

    def _review_row(self, item: ReviewQueue, university_name: str | None) -> dict:
        return {
            "id": item.id,
            "item_type": item.item_type,
            "item_id": item.item_id,
            "university_id": item.university_id,
            "university_name": university_name,
            "college_id": item.college_id,
            "major_id": item.major_id,
            "policy_document_id": item.policy_document_id,
            "competition_id": item.competition_id,
            "status": item.status,
            "reason": item.reason,
            "raw_value": item.raw_value,
            "suggested_value": item.suggested_value,
            "evidence_text": item.evidence_text,
            "source_url": item.source_url,
            "confidence": item.confidence,
            "assigned_to": item.assigned_to,
            "reviewed_at": item.reviewed_at,
            "reviewer_notes": item.reviewer_notes,
            "is_demo": item.is_demo,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _count(self, db: Session, stmt) -> int:
        return int(db.scalar(stmt) or 0)

    def _as_utc(self, value):
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)
