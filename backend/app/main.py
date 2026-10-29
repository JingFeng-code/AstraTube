"""FastAPI 組裝：CORS、掛上各組路由、健康檢查。"""
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import config  # noqa: F401  確保 .env 在最早期被載入
from app.core import access
from app.api.ask import router as ask_router
from app.api.implement import router as implement_router
from app.api.models import router as models_router
from app.api.notes import router as notes_router
from app.api.settings import router as settings_router
from app.api.subtitles import router as subtitles_router
from app.api.subtitle_import import router as subtitle_import_router
from app.api.summarize import router as summarize_router

app = FastAPI(title="AstraTube")


class LocalOnlyCORSMiddleware(CORSMiddleware):
    """只對 AstraTube 自己的介面回應 CORS，不再使用 "*"（任何網站都能讀寫本機 API）。"""

    def is_allowed_origin(self, origin: str) -> bool:
        return access.origin_allowed(origin)


app.add_middleware(LocalOnlyCORSMiddleware, allow_origins=[],
                   allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["Content-Type", "X-Astra-Desktop-Token"])


@app.middleware("http")
async def local_access_gate(request: Request, call_next):
    # 先擋其他網站與 DNS rebinding，再檢查桌面版每次啟動產生的工作階段 Token。
    reason = access.rejection_reason(request.headers.get("host", ""),
                                     request.headers.get("origin"),
                                     request.headers.get("sec-fetch-site"))
    if reason:
        return JSONResponse({"detail": "Request origin is not allowed.", "reason": reason},
                            status_code=403)
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
