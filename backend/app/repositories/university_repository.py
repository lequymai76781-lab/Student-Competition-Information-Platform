from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Competition, PolicyDocument, University, UniversityCompetitionPolicy, UniversityPolicy


class UniversityRepository:
    def list_universities(
        self,
        db: Session,
        *,
        keyword: str | None = None,
        province: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[University]:
        stmt = select(University).options(selectinload(University.colleges))
        if keyword:
            stmt = stmt.where(University.name.ilike(f"%{keyword}%"))
        if province:
            stmt = stmt.where(University.province == province)
        stmt = stmt.order_by(University.name.asc()).offset(offset).limit(limit)
        return list(db.execute(stmt).scalars().unique().all())

    def get_by_id(self, db: Session, university_id: int) -> University | None:
        stmt = select(University).options(selectinload(University.colleges)).where(University.id == university_id)
        return db.execute(stmt).scalars().unique().one_or_none()

    def list_policies(
        self,
        db: Session,
        university_id: int,
        *,
        year: int | None = None,
        policy_type: str | None = None,
    ) -> list[dict]:
        stmt = select(PolicyDocument).where(
            PolicyDocument.university_id == university_id,
            PolicyDocument.is_demo.is_(False),
        )
        if year is not None:
            stmt = stmt.where(PolicyDocument.year == year)
        if policy_type:
            stmt = stmt.where(PolicyDocument.policy_type == policy_type)
        stmt = stmt.order_by(
            PolicyDocument.is_current.desc(),
            PolicyDocument.year.desc().nullslast(),
            PolicyDocument.updated_at.desc(),
        )
        return [self._policy_document_compat_row(document) for document in db.execute(stmt).scalars().all()]

    @staticmethod
    def _policy_document_compat_row(document: PolicyDocument) -> dict:
        return {
            "id": document.id,
            "university_id": document.university_id,
            "policy_name": document.title,
            "policy_type": document.policy_type,
            "year": document.year,
            "source_url": document.source_url,
            "official_file_url": document.attachment_url,
            "published_at": document.published_at,
            "effective_date": document.effective_from,
            "content": document.content_text or document.content_markdown,
            "is_verified": document.is_verified,
            "is_demo": document.is_demo,
        }

    def list_competition_policies(
        self,
        db: Session,
        university_id: int,
        *,
        year: int | None = None,
        usage_type: str | None = None,
    ) -> list[dict]:
        stmt = (
            select(UniversityCompetitionPolicy, Competition.name, UniversityPolicy.policy_name)
            .join(Competition, Competition.id == UniversityCompetitionPolicy.competition_id)
            .outerjoin(UniversityPolicy, UniversityPolicy.id == UniversityCompetitionPolicy.policy_id)
            .where(UniversityCompetitionPolicy.university_id == university_id)
            .order_by(UniversityCompetitionPolicy.year.desc(), Competition.name.asc())
        )
        if year is not None:
            stmt = stmt.where(UniversityCompetitionPolicy.year == year)
        if usage_type:
            stmt = stmt.where(UniversityCompetitionPolicy.usage_type == usage_type)

        return [
            {
                "id": item.id,
                "competition_id": item.competition_id,
                "competition_name": competition_name,
                "policy_id": item.policy_id,
                "policy_name": policy_name,
                "year": item.year,
                "recognition_status": item.recognition_status,
                "recognized_level": item.recognized_level,
                "recognized_award": item.recognized_award,
                "score": item.score,
                "usage_type": item.usage_type,
                "notes": item.notes,
                "evidence_text": item.evidence_text,
                "is_demo": item.is_demo,
            }
            for item, competition_name, policy_name in db.execute(stmt).all()
        ]
