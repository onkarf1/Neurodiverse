from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import Settings, get_settings
from app.core.constants import API_V1_PREFIX, REQUEST_ID_HEADER
from app.core.errors import register_exception_handlers
from app.core.log_config import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory; run with `uvicorn --factory app.main:create_app`."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    is_production = settings.app_env == "production"
    app = FastAPI(
        title="GoalFit API",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = settings
    register_exception_handlers(app)

    # Starlette runs the most recently added middleware first, so this list is innermost first.
    # Request flow: SecurityHeaders -> CORS -> RequestContext -> BodySizeLimit -> routes.
    # CORS sits outside RequestContext so 413 and 500 responses stay readable by the frontend.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(SecurityHeadersMiddleware, strict=is_production)

    app.include_router(v1_router, prefix=API_V1_PREFIX)
    return app
