import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.responses import error_response


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and exc.detail.get("transaction") == "atomic":
        allowed = {key: exc.detail[key] for key in ("message", "failed_candidate_id", "succeeded", "failed", "pending_ids", "transaction") if key in exc.detail}
        return JSONResponse(status_code=exc.status_code, content=error_response(str(allowed.get("message", "批量审核失败")), allowed))
    return JSONResponse(status_code=exc.status_code, content=error_response(str(exc.detail)))


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content=jsonable_encoder(error_response("Request validation failed", exc.errors())))


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    error_id = uuid4().hex
    logging.getLogger(__name__).error("Unhandled error %s", error_id, exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(status_code=500, content=error_response("Internal server error", {"error_id": error_id}))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
