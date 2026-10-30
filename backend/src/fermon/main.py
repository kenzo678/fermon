from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fermon.fermentation.infrastructure.http.errors import register_error_handlers
from fermon.fermentation.infrastructure.http.router import router as fermentation_router
from fermon.fermentation.infrastructure.http.websocket import router as websocket_router
from fermon.fermentation.infrastructure.realtime import ReadingBroadcaster, listen_dsn
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings()
        engine = create_engine(resolved)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        # Starts without waiting for the database, so the API (and /health) comes up regardless.
        broadcaster = ReadingBroadcaster(listen_dsn(resolved.database_url))
        app.state.reading_feed = broadcaster
        await broadcaster.start()
        try:
            yield
        finally:
            await broadcaster.stop()
            await engine.dispose()

    app = FastAPI(title="Fermon", lifespan=lifespan)
    cors_origins = (settings or Settings()).cors_origins
    app.state.cors_origins = cors_origins  # also enforced on WebSocket handshakes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )
    register_error_handlers(app)
    app.include_router(fermentation_router)
    app.include_router(websocket_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
