from fastapi import APIRouter

from app.core.responses import ApiResponse, success_response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def health_check() -> dict:
    return success_response({"status": "ok", "service": "competition-intelligence-api"})

