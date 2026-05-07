from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="PUR Leads v2")
    app.include_router(health_router)
    return app


app = create_app()
