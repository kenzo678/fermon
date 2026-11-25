from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fermon.fermentation.infrastructure.http.errors import register_error_handlers
from fermon.fermentation.infrastructure.http.ingestion_router import (
    router as ingestion_router,
)
from fermon.fermentation.infrastructure.http.lab_router import router as lab_router
from fermon.fermentation.infrastructure.http.quality_router import router as quality_router
from fermon.fermentation.infrastructure.http.router import router as fermentation_router
from fermon.fermentation.infrastructure.http.websocket import router as websocket_router
from fermon.fermentation.infrastructure.realtime import RealtimeBroadcaster, listen_dsn
from fermon.fermentation.infrastructure.wiring import alert_rules
from fermon.identity.application import LoginThrottle
from fermon.identity.infrastructure.http.csrf import require_csrf_header
from fermon.identity.infrastructure.http.dependencies import get_current_user
from fermon.identity.infrastructure.http.device_key import (
    require_device_key,
    warn_if_device_keys_missing,
)
from fermon.identity.infrastructure.http.errors import register_identity_error_handlers
from fermon.identity.infrastructure.http.router import router as identity_router
from fermon.identity.infrastructure.http.session_cookie import (
    SessionSettings,
    warn_if_cookie_not_secure,
)
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings()
        engine = create_engine(resolved)
        app.state.engine = engine
        warn_if_cookie_not_secure(app.state.session_settings)
        warn_if_device_keys_missing(app.state.device_api_keys)
        app.state.session_factory = create_session_factory(engine)
        app.state.alert_rules = alert_rules(resolved)
        # Starts without waiting for the database, so the API (and /health) comes up regardless.
        broadcaster = RealtimeBroadcaster(listen_dsn(resolved.database_url))
        app.state.reading_feed = broadcaster
        app.state.alert_feed = broadcaster
        await broadcaster.start()
        try:
            yield
        finally:
            await broadcaster.stop()
            await engine.dispose()

    app = FastAPI(title="Fermon", lifespan=lifespan)
    resolved_settings = settings or Settings()
    cors_origins = resolved_settings.cors_origins
    app.state.session_settings = SessionSettings(
        ttl_seconds=resolved_settings.session_ttl_seconds,
        cookie_secure=resolved_settings.session_cookie_secure,
    )
    app.state.login_throttle = LoginThrottle(
        lambda: datetime.now(UTC),
        window=timedelta(seconds=resolved_settings.login_throttle_window_seconds),
        max_account_failures=resolved_settings.login_max_failures_per_account,
        max_ip_failures=resolved_settings.login_max_failures_per_ip,
    )
    app.state.device_api_keys = resolved_settings.device_api_keys
    app.state.cors_origins = cors_origins  # also enforced on WebSocket handshakes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With", "X-Device-Key"],
        allow_credentials=True,
    )
    register_error_handlers(app)
    register_identity_error_handlers(app)
    # Sessions are required by default: a router added here without `session_routes` would be
    # caught by tests/test_authorization.py. Each identity route picks its own session rule.
    csrf = [Depends(require_csrf_header)]
    session_routes = [*csrf, Depends(get_current_user)]
    app.include_router(identity_router, dependencies=csrf)
    app.include_router(fermentation_router, dependencies=session_routes)
    app.include_router(quality_router, dependencies=session_routes)
    app.include_router(lab_router, dependencies=session_routes)
    # Devices authenticate with an API key instead of a session cookie, so there is no CSRF risk.
    app.include_router(ingestion_router, dependencies=[Depends(require_device_key)])
    app.include_router(websocket_router)  # authenticates the handshake itself (close code 4401)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
