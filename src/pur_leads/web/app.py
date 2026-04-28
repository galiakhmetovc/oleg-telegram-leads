"""FastAPI application factory."""

from fastapi import FastAPI

from pur_leads.web.routes_health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="PUR Leads")
    app.include_router(health_router)
    return app
