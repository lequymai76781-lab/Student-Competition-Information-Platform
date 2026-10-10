from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.university_repository import UniversityRepository
from app.schemas.university import (
    UniversityCompetitionPolicyRead,
    UniversityDetail,
    UniversityPolicyRead,
    UniversityRead,
)


class UniversityService:
    def __init__(self) -> None:
        self.repository = UniversityRepository()

    def list_universities(
        self,
        db: Session,
        *,
        keyword: str | None = None,
        province: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UniversityRead]:
        universities = self.repository.list_universities(
            db,
            keyword=keyword,
            province=province,
            limit=limit,
            offset=offset,
        )
        return [UniversityRead.model_validate(university) for university in universities]

    def get_university(self, db: Session, university_id: int) -> UniversityDetail:
        university = self.repository.get_by_id(db, university_id)
        if university is None:
            raise HTTPException(status_code=404, detail="University not found")
        detail = UniversityDetail.model_validate(university)
        detail.colleges = [college for college in detail.colleges if college.is_verified and not college.is_demo]
        return detail

    def list_policies(
        self,
        db: Session,
        university_id: int,
        *,
        year: int | None = None,
        policy_type: str | None = None,
    ) -> list[UniversityPolicyRead]:
        if self.repository.get_by_id(db, university_id) is None:
            raise HTTPException(status_code=404, detail="University not found")
        policies = self.repository.list_policies(db, university_id, year=year, policy_type=policy_type)
        return [UniversityPolicyRead.model_validate(policy) for policy in policies]

    def list_competition_policies(
        self,
        db: Session,
        university_id: int,
        *,
        year: int | None = None,
        usage_type: str | None = None,
    ) -> list[UniversityCompetitionPolicyRead]:
        if self.repository.get_by_id(db, university_id) is None:
            raise HTTPException(status_code=404, detail="University not found")
        rows = self.repository.list_competition_policies(db, university_id, year=year, usage_type=usage_type)
        return [UniversityCompetitionPolicyRead(**row) for row in rows]
