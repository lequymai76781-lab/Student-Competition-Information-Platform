from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_setup import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.resolved_log_dir)
    public_docs = settings.environment in {"development", "test"}
    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="API for student competition discovery, policy intelligence, and rule-based recommendations.",
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
