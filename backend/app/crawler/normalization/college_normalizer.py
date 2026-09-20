from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import College


class CollegeNormalizer:
    def get_or_create_from_official_source(
        self,
        db: Session,
        *,
        university_id: int,
        name: str,
        official_website: str,
        official_domain: str,
        source_url: str | None,
        source_hash: str,
        confidence: float,
    ) -> College:
        existing = db.execute(
            select(College).where(
                College.university_id == university_id,
                College.name == name,
            )
        ).scalar_one_or_none()
        if existing:
            if confidence >= 0.7:
                existing.official_website = existing.official_website or official_website
                existing.official_domain = existing.official_domain or official_domain
                existing.source_url = existing.source_url or source_url
                existing.source_hash = existing.source_hash or source_hash
                existing.is_verified = existing.is_verified or confidence >= 0.8
            return existing

        college = College(
            university_id=university_id,
            name=name,
            official_website=official_website,
            official_domain=official_domain,
            source_url=source_url,
            source_hash=source_hash,
            is_verified=confidence >= 0.8,
            is_demo=False,
        )
        db.add(college)
        db.flush()
        return college
