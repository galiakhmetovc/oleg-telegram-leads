from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.enrichments import router as enrichments_router
from app.api.golden_examples import router as golden_examples_router
from app.api.health import router as health_router
from app.api.llm_verifications import router as llm_verifications_router
from app.api.llm_settings import router as llm_settings_router
from app.api.notifications import router as notifications_router
from app.api.project_docs import router as project_docs_router
from app.api.runtime import router as runtime_router
from app.api.settings import router as settings_router
from app.api.telegram_ingestion import router as telegram_ingestion_router
from app.core.auth import verify_session_token
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PUR Leads v2")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.auth_enabled:
        app.middleware("http")(_auth_middleware)
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(enrichments_router, prefix="/api/v1")
    app.include_router(golden_examples_router, prefix="/api/v1")
    app.include_router(llm_verifications_router, prefix="/api/v1")
    app.include_router(llm_settings_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(telegram_ingestion_router, prefix="/api/v1")
    app.include_router(runtime_router, prefix="/api/v1")
    app.include_router(project_docs_router, prefix="/api/v1")
    return app


async def _auth_middleware(request, call_next):  # type: ignore[no-untyped-def]
    path = request.url.path
    if not path.startswith("/api/v1") or path.startswith("/api/v1/auth"):
        return await call_next(request)

    settings = get_settings()
    session = verify_session_token(
        request.cookies.get(settings.auth_cookie_name),
        settings=settings,
    )
    if session is None:
        return JSONResponse(
            {"detail": "authentication required"},
            status_code=401,
        )
    request.state.auth_user = session.username
    return await call_next(request)


app = create_app()
