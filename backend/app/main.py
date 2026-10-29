"""FastAPI 組裝：CORS、掛上各組路由、健康檢查。"""
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import config  # noqa: F401  確保 .env 在最早期被載入
from app.api.ask import router as ask_router
from app.api.implement import router as implement_router
from app.api.models import router as models_router
from app.api.notes import router as notes_router
from app.api.settings import router as settings_router
from app.api.subtitles import router as subtitles_router
from app.api.subtitle_import import router as subtitle_import_router
from app.api.summarize import router as summarize_router

app = FastAPI(title="AstraTube")
_DESKTOP = bool(os.environ.get("ASTRA_DESKTOP_TOKEN"))
# Release Tauri uses http://tauri.localhost on Windows. The session token is
# independently required for requests, including /health and /settings.
allowed_origins = ["http://tauri.localhost", "tauri://localhost"] if _DESKTOP else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                   allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["Content-Type", "X-Astra-Desktop-Token"])


@app.middleware("http")
async def desktop_session_gate(request: Request, call_next):
    token = os.environ.get("ASTRA_DESKTOP_TOKEN", "")
    if token and request.method != "OPTIONS":
        provided = request.headers.get("X-Astra-Desktop-Token", "")
        if not secrets.compare_digest(provided, token):
            return JSONResponse({"detail": "Desktop session unavailable."}, status_code=403)
    return await call_next(request)

app.include_router(summarize_router)
app.include_router(implement_router)
app.include_router(ask_router)
app.include_router(models_router)
app.include_router(notes_router)
app.include_router(settings_router)
app.include_router(subtitles_router)
app.include_router(subtitle_import_router)


@app.get("/health")
def health() -> dict:
    """健康檢查。"""
    return {"status": "ok"}
