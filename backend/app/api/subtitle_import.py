"""綁定影片的本機字幕匯入／移除 API；不接收遠端檔案 URL。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.transcript import imported_subtitles as imported

router = APIRouter(prefix="/subtitles/imported", tags=["subtitles"])


class ImportRequest(BaseModel):
    video_url: str = Field(min_length=12, max_length=2048)
    filename: str = Field(min_length=5, max_length=255)
    content: str = Field(min_length=1, max_length=1024 * 1024)


class TargetRequest(BaseModel):
    video_url: str = Field(min_length=12, max_length=2048)


@router.post("")
def import_subtitles(req: ImportRequest) -> dict:
    try:
        platform, video_id, page = imported.target_from_url(req.video_url)
        stored = imported.save(platform, video_id, page, req.filename, req.content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "platform": platform, "video_id": video_id, "page": page,
        "format": stored["format"], "cue_count": len(stored["cues"]),
        "source": "imported",
    }


@router.post("/remove")
def remove_subtitles(req: TargetRequest) -> dict:
    try:
        platform, video_id, page = imported.target_from_url(req.video_url)
        removed = imported.delete(platform, video_id, page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"removed": removed, "platform": platform, "video_id": video_id, "page": page}



@router.post("/status")
def imported_subtitles_status(req: TargetRequest) -> dict:
    try:
        platform, video_id, page = imported.target_from_url(req.video_url)
        stored = imported.load(platform, video_id, page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "exists": bool(stored), "platform": platform, "video_id": video_id, "page": page,
        "format": stored["format"] if stored else None,
        "cue_count": len(stored["cues"]) if stored else 0,
    }
