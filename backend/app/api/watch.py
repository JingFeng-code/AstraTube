"""陪看模式 API：擷取只能在這台電腦上發生，所以和本地影片一樣拒絕遠端環境。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.local_video import on_this_computer
from app.core import messages
from app.transcript import local_speech, watch_along

router = APIRouter(prefix="/watch", tags=["watch"])


class Region(BaseModel):
    x: float = Field(ge=0, le=20000)
    y: float = Field(ge=0, le=20000)
    width: float = Field(gt=0, le=20000)
    height: float = Field(gt=0, le=20000)
    dpr: float = Field(default=1, gt=0, le=8)


class StartRequest(BaseModel):
    platform: Literal["youtube", "bilibili"]
    video_id: str = Field(min_length=1, max_length=20)
    page: int = Field(default=1, ge=1, le=1000)
    region: Region
    offset: float = Field(default=0, ge=0, le=360000)


class HeartbeatRequest(BaseModel):
    position: float = Field(ge=0, le=360000)


def _require_this_computer(request: Request) -> None:
    client = request.client.host if request.client else None
    if not on_this_computer(client, request.headers.get("origin")):
        raise HTTPException(403, messages.t("speech.local_only"))


@router.get("/status")
def watch_status(request: Request) -> dict:
    client = request.client.host if request.client else None
    return {
        "available": on_this_computer(client, request.headers.get("origin")) and watch_along.capture_supported(),
        "speech_ready": local_speech.engine_available() and local_speech.model_ready(),
        "session": watch_along.status(),
    }


@router.get("/vision-models")
def watch_vision_models(request: Request) -> dict:
    _require_this_computer(request)
    return {"models": watch_along.vision_models()}


@router.post("/start")
def watch_start(req: StartRequest, request: Request) -> dict:
    _require_this_computer(request)
    if not watch_along.capture_supported():
        raise HTTPException(409, messages.t("watch.desktop_only"))
    if not (local_speech.engine_available() and local_speech.model_ready()):
        raise HTTPException(409, messages.t("speech.model_missing"))
    try:
        return watch_along.start(req.platform, req.video_id, req.page, req.region.model_dump(), req.offset)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/heartbeat")
def watch_heartbeat(req: HeartbeatRequest, request: Request) -> dict:
    _require_this_computer(request)
    watch_along.heartbeat(req.position)
    return {"ok": True}


@router.post("/region")
def watch_region(req: Region, request: Request) -> dict:
    _require_this_computer(request)
    watch_along.set_region(req.model_dump())
    return {"ok": True}


@router.post("/finish")
def watch_finish(request: Request) -> dict:
    _require_this_computer(request)
    try:
        return watch_along.finish()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/cancel")
def watch_cancel(request: Request) -> dict:
    _require_this_computer(request)
    return watch_along.cancel()
