from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.imports import router as imports_router
from app.api.session import router as session_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.api_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(session_router)
app.include_router(imports_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neighborlink-backend",
        "environment": settings.environment,
        "version": settings.api_version,
    }
