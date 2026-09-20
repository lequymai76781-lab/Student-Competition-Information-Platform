from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import ApiResponse, success_response
from app.schemas.home import HomeDataRead
from app.services.home_data_service import HomeDataService


router = APIRouter(tags=["home"])
service = HomeDataService()


@router.get("/home", response_model=ApiResponse[HomeDataRead])
def get_home(db: Session = Depends(get_db)) -> dict:
    return success_response(service.build(db))
