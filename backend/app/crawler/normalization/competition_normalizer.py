from sqlalchemy.orm import Session

from app.services.competition_normalization_service import CompetitionNormalizationResult, CompetitionNormalizationService


class CompetitionNormalizer:
    def __init__(self) -> None:
        self.service = CompetitionNormalizationService()

    def normalize(self, db: Session, raw_name: str) -> CompetitionNormalizationResult:
        return self.service.normalize(db, raw_name)

    def normalize_or_create(
        self,
        db: Session,
        raw_name: str,
        *,
        trusted_policy: bool,
        source_title: str,
        category: str | None = None,
        source_url: str | None = None,
    ) -> CompetitionNormalizationResult:
        return self.service.normalize_or_create(
            db,
            raw_name,
            trusted_policy=trusted_policy,
            source_title=source_title,
            category=category,
            source_url=source_url,
        )
