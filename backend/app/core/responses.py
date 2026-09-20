from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    message: str = "ok"
    meta: dict[str, Any] | None = None


def success_response(data: Any = None, message: str = "ok", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "meta": meta,
    }


def error_response(message: str, details: Any = None) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "message": message,
        "meta": {"details": details} if details else None,
    }

