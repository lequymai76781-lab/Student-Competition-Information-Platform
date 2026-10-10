from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, University
from app.repositories.policy_repository import PolicyRepository
from app.schemas.policy import (
    CrawlerJobRead,
    PolicyCoverageSummary,
    PolicyDocumentRead,
    PolicyRecognitionRead,
    PolicyResolutionRead,
    ReviewQueueRead,
)
from app.services.policy_resolution_service import PolicyResolutionService


class PolicyDataService:
    def __init__(self) -> None:
        self.repository = PolicyRepository()
        self.resolution_service = PolicyResolutionService()

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
    ) -> list[PolicyDocumentRead]:
        rows = self.repository.list_documents(
            db,
            university_id=university_id,
            scope_type=scope_type,
            policy_type=policy_type,
            year=year,
            include_demo=include_demo,
            limit=limit,
            offset=offset,
        )
        return [PolicyDocumentRead(**row) for row in rows]

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
    ) -> list[PolicyRecognitionRead]:
        rows = self.repository.list_recognitions(
            db,
            competition_id=competition_id,
            university_id=university_id,
            recognition_status=recognition_status,
            include_demo=include_demo,
            limit=limit,
            offset=offset,
        )
        return [PolicyRecognitionRead(**row) for row in rows]

    def list_jobs(self, db: Session, *, status: str | None = None, limit: int = 50, offset: int = 0) -> list[CrawlerJobRead]:
        jobs = self.repository.list_jobs(db, status=status, limit=limit, offset=offset)
        return [CrawlerJobRead.model_validate(job) for job in jobs]

    def list_review_queue(
        self,
        db: Session,
        *,
        status: str = "pending",
        university_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewQueueRead]:
        rows = self.repository.list_review_queue(db, status=status, university_id=university_id, limit=limit, offset=offset)
        return [ReviewQueueRead(**row) for row in rows]

    def coverage_summary(self, db: Session) -> PolicyCoverageSummary:
        return PolicyCoverageSummary(**self.repository.coverage_summary(db))

    def resolve(
        self,
        db: Session,
        *,
        competition_id: int,
        university_id: int,
        college_id: int | None = None,
        major_id: int | None = None,
        year: int | None = None,
    ) -> PolicyResolutionRead:
        if db.scalar(select(Competition.id).where(Competition.id == competition_id)) is None:
            raise HTTPException(status_code=404, detail="Competition not found")
        if db.scalar(select(University.id).where(University.id == university_id)) is None:
            raise HTTPException(status_code=404, detail="University not found")
        result = self.resolution_service.resolve(
            db,
            competition_id=competition_id,
            university_id=university_id,
            college_id=college_id,
            major_id=major_id,
            year=year,
            verified_only=True,
        )
        return PolicyResolutionRead(**asdict(result))
