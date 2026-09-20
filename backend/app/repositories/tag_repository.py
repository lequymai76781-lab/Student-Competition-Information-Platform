from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag


class TagRepository:
    def list_tags(self, db: Session) -> list[Tag]:
        stmt = select(Tag).order_by(Tag.category.asc(), Tag.name.asc())
        return list(db.execute(stmt).scalars().all())

    def get_by_name(self, db: Session, name: str) -> Tag | None:
        return db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
