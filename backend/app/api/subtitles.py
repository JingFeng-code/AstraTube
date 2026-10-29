"""時間軸字幕 API：重用公開字幕／快取；GET 僅讀快取，POST 由使用者觸發翻譯。

只支援經驗證的影片 ID；不下載影音，不將 GET 字幕端點拿來呼叫 AI。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal

from app.transcript import bilibili, cache, captions, translation_cache, subtitle_translation, imported_subtitles
from app.llm import opencode
from app.llm.base import ProviderError

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
    translation_provider: str = "opencode",
) -> dict:
    """只接受影片識別碼；不接受任意外部 URL，以免變成網路代理。"""
    try:
        imported_subtitles.validate_identity(platform, video_id, page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    imported = imported_subtitles.load(platform, video_id, page)
    if imported:
        cues = [dict(cue) for cue in imported["cues"]]
        is_chinese = imported["is_chinese"]
        source = "imported"
        timing_precision = "milliseconds_original"
    elif platform == "youtube":
        if not _YOUTUBE_ID.fullmatch(video_id):
            raise HTTPException(400, "YouTube 影片 ID 格式不正確。")
        try:
            text, is_chinese = captions.fetch_transcript(video_id)
        except Exception as exc:  # noqa: BLE001
            # 字幕不可用時，若本機已有經授權的 Whisper 轉錄快取，仍可顯示。
            local = cache.get(video_id)
            if not local:
                error = captions.classify_error(exc)
                # 只有「確實沒有字幕／影片受限」回 404；被擋或斷線是暫時性的服務問題
                status = 404 if error.kind in ("missing", "unavailable") else 503
                raise HTTPException(status, str(error)) from exc
            text, is_chinese = local
    elif not imported:
        if not _BILIBILI_ID.fullmatch(video_id):
            raise HTTPException(400, "Bilibili BV 影片 ID 格式不正確。")
        try:
            text, is_chinese = bilibili.fetch_transcript(video_id, page)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    if not imported:
        cues = parse_timed_cues(text)
        source = "platform"
        timing_precision = "seconds_estimated"
    if not cues:
        raise HTTPException(404, "逐字稿沒有可顯示的時間戳字幕。")
    # 讀取本機已有的譯文，不觸發 AI API；切換影片或重新開啟時不需重複付費或運算。
    try:
        _, _, cache_key = subtitle_translation.resolve_provider(translation_provider)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    translated_count = 0
    for cue in cues:
        cue["translation"] = translation_cache.get(cue["text"], cache_key)
        if cue["translation"]:
            translated_count += 1
    return {
        "source": source,
        "translated_count": translated_count,
        "translation_provider": translation_provider,
        "platform": platform,
        "video_id": video_id,
        "page": page,
        "is_chinese": is_chinese,
        "cues": cues,
        "translation_status": ("complete" if translated_count == len(cues) else
                               "partial" if translated_count else "not_available"),
        "timing_precision": timing_precision,
    }



class TranslateRequest(BaseModel):
    platform: Literal["youtube", "bilibili"]
    video_id: str = Field(min_length=1, max_length=20)
    page: int = Field(default=1, ge=1, le=1000)
    start_index: int = Field(default=0, ge=0, le=5999)
    batch_size: int = Field(default=16, ge=1, le=16)
    translation_provider: str = Field(default="opencode", min_length=1, max_length=140)


@router.post("/translate")
def translate_subtitles(req: TranslateRequest) -> dict:
    """使用者按下翻譯後才執行。原文由伺服器取得，防止任意文字被拿來消耗模型。"""
    try:
        subtitle_translation.resolve_provider(req.translation_provider)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    source = get_subtitles(req.platform, req.video_id, req.page, req.translation_provider)
    cues = source["cues"]
    if req.start_index >= len(cues):
        raise HTTPException(400, "翻譯位置超出影片字幕範圍。")
    selected = cues[req.start_index:req.start_index + req.batch_size]
    indexed = [{"id": req.start_index + index, "text": cue["text"]}
               for index, cue in enumerate(selected)]
    try:
        translations, model = subtitle_translation.translate_batch(
            indexed, provider=req.translation_provider)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        # 供應商金鑰與原始逐字稿不得透過錯誤訊息洩漏給瀏覽器。ProviderError 的訊息由我們自己組成
        # （狀態碼、清理過的回應摘要與下一步建議），可以顯示，讓使用者知道是限流、斷線還是被拒。
        kind = "本機 Ollama" if req.translation_provider.startswith("ollama:") else "免費字幕"
        reason = f"（{str(exc)[:240]}）" if isinstance(exc, ProviderError) else ""
        raise HTTPException(502, f"{kind}翻譯服務暫時無法使用{reason}，請檢查連線或模型設定。") from exc
    return {
        "platform": req.platform,
        "video_id": req.video_id,
        "page": req.page,
        "translations": translations,
        "next_index": req.start_index + len(selected),
        "total": len(cues),
        "model": model,
    }
