from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import University


class UniversityNormalizer:
    def get_by_name_or_alias(self, db: Session, name: str) -> University | None:
        direct = db.execute(select(University).where(University.name == name)).scalar_one_or_none()
        if direct:
            return direct
        for university in db.execute(select(University)).scalars().all():
            if name in (university.aliases or []) or name == university.short_name:
                return university
        return None
