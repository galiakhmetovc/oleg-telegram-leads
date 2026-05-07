from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analytics import router as analytics_router
from app.api.enrichments import router as enrichments_router
from app.api.health import router as health_router
from app.api.settings import router as settings_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PUR Leads v2")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(enrichments_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    return app


app = create_app()
