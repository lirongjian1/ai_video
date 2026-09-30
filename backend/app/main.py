from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401
    AiCharacter,
    AiFile,
    AiModelConfig,
    AiProject,
    AiPrompt,
    AiScene,
    AiScript,
    AiStoryboard,
    AiTask,
    SysUser,
)
from app.services.bootstrap import ensure_default_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_default_admin(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)
settings.storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")


@app.get("/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}

