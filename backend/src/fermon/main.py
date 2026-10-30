from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fermon.fermentation.infrastructure.http.errors import register_error_handlers
from fermon.fermentation.infrastructure.http.router import router as fermentation_router
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings or Settings())
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Fermon", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(settings or Settings()).cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )
    register_error_handlers(app)
    app.include_router(fermentation_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
