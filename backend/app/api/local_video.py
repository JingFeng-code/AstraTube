"""本地影片的本機語音轉文字 API。

影片只能傳到同一台電腦上的後端：在 Codespaces 等遠端環境，這等於把影片上傳到別台機器，
所以一律拒絕，不能只靠畫面上的說明。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from starlette.requests import ClientDisconnect

from app.core import access, messages
from app.transcript import local_speech

router = APIRouter(prefix="/local-video", tags=["local-video"])

_VIDEO_ID = re.compile(r"^[0-9a-f]{16}$")
_MAX_VIDEO_BYTES = 200 * 1024 ** 3


def on_this_computer(client_host: str | None, origin: str | None) -> bool:
    """請求必須來自這台電腦上的 AstraTube 介面。"""
    if os.environ.get("CODESPACE_NAME"):
        return False
    if client_host not in access.LOOPBACK_HOSTS:
        return False
    if origin is None:
        return True
    if origin in access.TAURI_ORIGINS:
        return True
    try:
        return (urlsplit(origin).hostname or "").lower() in access.LOOPBACK_HOSTS
    except ValueError:
        return False


def _require_this_computer(request: Request) -> None:
    client = request.client.host if request.client else None
    if not on_this_computer(client, request.headers.get("origin")):
        raise HTTPException(403, messages.t("speech.local_only"))


def _require_id(video_id: str) -> None:
    if not _VIDEO_ID.fullmatch(video_id):
        raise HTTPException(400, messages.t("speech.invalid_id"))


@router.get("/speech")
def speech_status(request: Request) -> dict:
    client = request.client.host if request.client else None
    return {
        "available_here": on_this_computer(client, request.headers.get("origin")),
        "engine": local_speech.engine_available(),
        "model_ready": local_speech.model_ready(),
        "model_name": local_speech.MODEL_NAME,
        "download": local_speech.download_status(),
    }


@router.post("/speech/model")
def download_model(request: Request) -> dict:
    """使用者按下才會下載；網址和內容雜湊都寫死在程式裡。"""
    _require_this_computer(request)
    return local_speech.start_model_download()


@router.post("/speech/model/cancel")
def cancel_model(request: Request) -> dict:
    _require_this_computer(request)
    return local_speech.cancel_model_download()


@router.get("/{video_id}/transcribe")
def transcribe_status(video_id: str) -> dict:
    _require_id(video_id)
    return local_speech.job_status(video_id)


@router.post("/{video_id}/transcribe/cancel")
def cancel_transcribe(video_id: str, request: Request) -> dict:
    _require_this_computer(request)
    _require_id(video_id)
    return local_speech.cancel_job(video_id)


@router.post("/{video_id}/transcribe")
async def upload_and_transcribe(video_id: str, request: Request) -> dict:
    """本文是影片檔本身；暫存到這台電腦，轉完就刪除。"""
    _require_this_computer(request)
    _require_id(video_id)
    if not local_speech.engine_available():
        raise HTTPException(409, messages.t("speech.engine_missing"))
    if not local_speech.model_ready():
        raise HTTPException(409, messages.t("speech.model_missing"))
    try:
        size = int(request.headers.get("content-length", ""))
    except ValueError:
        raise HTTPException(411, messages.t("speech.upload_failed")) from None
    if size <= 0 or size > _MAX_VIDEO_BYTES:
        raise HTTPException(413, messages.t("speech.too_large"))
    if not local_speech.has_room_for(size):
        raise HTTPException(507, messages.t("speech.no_disk"))
    try:
        path: Path = local_speech.begin_upload(video_id)
    except local_speech.SpeechError as exc:
        raise HTTPException(409, str(exc)) from exc
    received = 0
    try:
        with open(path, "wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
                received += len(chunk)
    except (ClientDisconnect, OSError) as exc:
        local_speech.abort_upload(video_id, path)
        raise HTTPException(400, messages.t("speech.upload_failed")) from exc
    if received != size:
        local_speech.abort_upload(video_id, path)
        raise HTTPException(400, messages.t("speech.upload_failed"))
    local_speech.start_job(video_id, path)
    return local_speech.job_status(video_id)
