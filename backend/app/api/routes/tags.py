from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.repositories.tag_repository import TagRepository
from app.schemas.tag import TagRead

router = APIRouter(tags=["tags"])
repository = TagRepository()


@router.get("/tags", response_model=ApiResponse[list[TagRead]])
def list_tags(db: Session = Depends(get_db)) -> dict:
    tags = repository.list_tags(db)
    return success_response([TagRead.model_validate(tag) for tag in tags])

