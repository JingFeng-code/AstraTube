"""FastAPI 組裝：CORS、掛上各組路由、健康檢查。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import config  # noqa: F401  確保 .env 在最早期被載入
from app.api.ask import router as ask_router
from app.api.implement import router as implement_router
from app.api.models import router as models_router
from app.api.notes import router as notes_router
from app.api.settings import router as settings_router
from app.api.summarize import router as summarize_router

app = FastAPI(title="Youtube Card Reader")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(summarize_router)
app.include_router(implement_router)
app.include_router(ask_router)
app.include_router(models_router)
app.include_router(notes_router)
app.include_router(settings_router)


@app.get("/health")
def health() -> dict:
    """健康檢查。"""
    return {"status": "ok"}
