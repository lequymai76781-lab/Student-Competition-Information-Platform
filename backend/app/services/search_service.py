from sqlalchemy.orm import Session

from app.repositories.competition_repository import CompetitionRepository
from app.schemas.competition import CompetitionListItem
from app.services.competition_service import CompetitionService


class SearchService:
    """Search abstraction. V0.1 uses PostgreSQL queries; Meilisearch can replace this later."""

    def __init__(self) -> None:
        self.repository = CompetitionRepository()
        self.competition_service = CompetitionService()

    def search_competitions(self, db: Session, keyword: str, limit: int = 20) -> list[CompetitionListItem]:
        competitions = self.repository.list_competitions(db, keyword=keyword, limit=limit)
        return [self.competition_service._to_list_item(competition) for competition in competitions]

