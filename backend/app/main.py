from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.api_version)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neighborlink-backend",
        "environment": settings.environment,
        "version": settings.api_version,
    }
