"""時間軸字幕 API：優先重用既有 YouTube / Bilibili 字幕快取。

這個 endpoint 不向 AI 傳送資料、不翻譯，也不下載影音。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal

from app.transcript import bilibili, cache, captions, translation_cache, subtitle_translation
from app.llm import opencode

router = APIRouter(prefix="/subtitles", tags=["subtitles"])
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BILIBILI_ID = re.compile(r"^BV[0-9A-Za-z]{10}$")
_LINE = re.compile(r"^\[(\d{1,7})\]\s*(.+)$")
_MAX_CUES = 6000


def parse_timed_cues(text: str) -> list[dict]:
    """從摘要流程既有的 [整數秒] 逐字稿生成有順序的字幕段落。

    上游逐字稿只有秒級起點，end 是估算顯示區間而非原始字幕的精確結束時間。
    相同秒數的文字合併，避免重疊造成選取不穩定。
    """
    grouped: dict[int, list[str]] = {}
    for raw in (text or "").splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        second = int(match.group(1))
        message = match.group(2).strip()
        if not message or second > 360000:
            continue
        grouped.setdefault(second, []).append(message[:800])
        if len(grouped) >= _MAX_CUES:
            break
    starts = sorted(grouped)
    result = []
    for idx, start in enumerate(starts):
        following = starts[idx + 1] if idx + 1 < len(starts) else start + 5
        result.append({
            "start": start,
            "end": min(max(start + 1, following), start + 12),
            "text": " ".join(grouped[start]),
            "translation": None,
        })
    return result


@router.get("")
def get_subtitles(
    platform: str = Query(..., pattern="^(youtube|bilibili)$"),
    video_id: str = Query(..., max_length=20),
    page: int = Query(1, ge=1, le=1000),
) -> dict:
    """只接受影片識別碼；不接受任意外部 URL，以免變成網路代理。"""
    if platform == "youtube":
        if not _YOUTUBE_ID.fullmatch(video_id):
            raise HTTPException(400, "YouTube 影片 ID 格式不正確。")
        try:
            text, is_chinese = captions.fetch_transcript(video_id)
        except Exception:
            # 字幕不可用時，若本機已有經授權的 Whisper 轉錄快取，仍可顯示。
            local = cache.get(video_id)
            if not local:
                raise HTTPException(404, "這支影片目前沒有可讀取的字幕。")
            text, is_chinese = local
    else:
        if not _BILIBILI_ID.fullmatch(video_id):
            raise HTTPException(400, "Bilibili BV 影片 ID 格式不正確。")
        try:
            text, is_chinese = bilibili.fetch_transcript(video_id, page)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    cues = parse_timed_cues(text)
    if not cues:
        raise HTTPException(404, "逐字稿沒有可顯示的時間戳字幕。")
    # 讀取本機已有的譯文，不觸發 AI API；切換影片或重新開啟時不需重複付費或運算。
    model = opencode.DEFAULT_FREE_MODEL
    translated_count = 0
    for cue in cues:
        cue["translation"] = translation_cache.get(cue["text"], model)
        if cue["translation"]:
            translated_count += 1
    return {
        "translated_count": translated_count,
        "platform": platform,
        "video_id": video_id,
        "page": page,
        "is_chinese": is_chinese,
        "cues": cues,
        "translation_status": ("complete" if translated_count == len(cues) else
                               "partial" if translated_count else "not_available"),
        "timing_precision": "seconds_estimated",
    }



class TranslateRequest(BaseModel):
    platform: Literal["youtube", "bilibili"]
    video_id: str = Field(min_length=1, max_length=20)
    page: int = Field(default=1, ge=1, le=1000)
    start_index: int = Field(default=0, ge=0, le=5999)
    batch_size: int = Field(default=16, ge=1, le=16)


@router.post("/translate")
def translate_subtitles(req: TranslateRequest) -> dict:
    """使用者按下翻譯後才執行。原文由伺服器取得，防止任意文字被拿來消耗模型。"""
    source = get_subtitles(req.platform, req.video_id, req.page)
    cues = source["cues"]
    if req.start_index >= len(cues):
        raise HTTPException(400, "翻譯位置超出影片字幕範圍。")
    selected = cues[req.start_index:req.start_index + req.batch_size]
    indexed = [{"id": req.start_index + index, "text": cue["text"]}
               for index, cue in enumerate(selected)]
    try:
        translations, model = subtitle_translation.translate_batch(indexed)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        # 供應商金鑰、HTTP 回應或原始逐字稿不得透過錯誤訊息洩漏給瀏覽器。
        raise HTTPException(502, "免費字幕翻譯服務暫時無法使用，請稍後重試。") from exc
    return {
        "platform": req.platform,
        "video_id": req.video_id,
        "page": req.page,
        "translations": translations,
        "next_index": req.start_index + len(selected),
        "total": len(cues),
        "model": model,
    }
