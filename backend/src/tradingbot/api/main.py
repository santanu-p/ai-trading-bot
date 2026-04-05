from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingbot.api.routers import auth, health, settings, trading
from tradingbot.config import get_settings
from tradingbot.db import Base, engine


def create_app() -> FastAPI:
    settings_config = get_settings()
    app = FastAPI(title=settings_config.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings_config.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        if settings_config.auto_create_tables:
            Base.metadata.create_all(bind=engine)

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(trading.router)
    return app


app = create_app()

