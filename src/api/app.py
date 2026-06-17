"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from src.api.v1.routes import (
    check_resource,
    cryptobot_webhook,
    me,
    onboarding,
    register,
    request_op,
)
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.integrations.telegram import get_checker_pool
from src.workers.broker import broker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("api")
    settings = get_settings()

    if not broker.is_worker_process:
        await broker.startup()

    pool = get_checker_pool()
    try:
        await pool.initialize()
    except Exception as e:
        log.warning("checker_pool_init_failed", error=str(e))

    log.info("api_starting", env=settings.env, host=settings.api_public_host)
    yield

    await pool.close()
    if not broker.is_worker_process:
        await broker.shutdown()
    log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FastSub API",
        version="0.4.0",
        description=(
            "FastSub — Telegram traffic monetization platform.\n\n"
            "**Authentication**: All `/api/v1/*` endpoints require "
            "`Authorization: Bearer fsp_live_<token>` header. Get a token "
            "via @fastsub_publisher_bot.\n\n"
            "**Base URL (production)**: `https://fastsub.95-85-251-42.sslip.io`"
        ),
        debug=settings.debug,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/swagger",  # interactive OpenAPI moved here; /docs = custom page
        redoc_url=None,
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"service": "fastsub", "version": "0.4.0"}

    # Cryptobot webhook
    app.include_router(cryptobot_webhook.router)

    # Custom styled API docs at /docs
    from src.api.v1.routes import docs_page
    app.include_router(docs_page.router)

    # Public web registration form
    app.include_router(register.router)

    # Public onboarding form for end users
    app.include_router(onboarding.router)

    # API v1
    app.include_router(me.router)
    app.include_router(request_op.router)
    app.include_router(check_resource.router)

    return app


app = create_app()
