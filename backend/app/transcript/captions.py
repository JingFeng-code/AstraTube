"""YouTube 官方／自動字幕（youtube-transcript-api），預設瀑布的第一層。"""
import re
import time
from typing import Optional, Tuple

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (AgeRestricted, InvalidVideoId,
                                            NoTranscriptFound, PoTokenRequired, RequestBlocked,
                                            TranscriptsDisabled, VideoUnavailable, VideoUnplayable,
                                            YouTubeRequestFailed)

from app.core import messages
from app.transcript import cache


class CaptionError(ValueError):
    """字幕取得失敗，附帶可分類的原因。

    kind：
      missing      影片確實沒有（或停用了）字幕
      unavailable  影片私人、已移除、年齡或地區限制
      blocked      YouTube 拒絕請求（請求過多、IP 被暫時封鎖、需要驗證）
      network      連不到 YouTube（網路、Proxy、防火牆）
      service      YouTube 回應異常或格式變更（可能需要更新套件）
    只有 missing 代表「這支影片沒有字幕」；其他狀況影片本身可能有字幕。
    """

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        self.detail = detail
        super().__init__(messages.t(f"captions.{kind}"))


def classify_error(error: Exception) -> CaptionError:
    """把 youtube-transcript-api／requests 的例外對應到使用者看得懂的原因。"""
    if isinstance(error, CaptionError):
        return error
    detail = f"{type(error).__name__}: {' '.join(str(error).split())[:300]}"
    if isinstance(error, (NoTranscriptFound, TranscriptsDisabled, StopIteration)):
        return CaptionError("missing", detail)
    if isinstance(error, (VideoUnavailable, VideoUnplayable, AgeRestricted, InvalidVideoId)):
        return CaptionError("unavailable", detail)
    if isinstance(error, (RequestBlocked, PoTokenRequired)):  # IpBlocked 是 RequestBlocked 的子類別
        return CaptionError("blocked", detail)
    if isinstance(error, YouTubeRequestFailed) and "429" in str(error):
        return CaptionError("blocked", detail)
    if isinstance(error, requests.RequestException):
        return CaptionError("network", detail)
    # 其他 CouldNotRetrieveTranscript（無法解析、建立同意 Cookie 失敗）與未預期的例外
    return CaptionError("service", detail)

CACHE_PREFIX = "captions_v1:"

_ID_PATTERNS = (
    r"(?:v=|youtu\.be/|embed/|shorts/|live/)([A-Za-z0-9_-]{11})",
    r"^([A-Za-z0-9_-]{11})$",
)
_PREFERRED_LANGS = ("zh-TW", "zh-Hant", "zh", "zh-Hans", "en")


def extract_video_id(url: str) -> Optional[str]:
    """從各種 YouTube 網址形式取出 11 碼影片 id；不是 YouTube 回 None。"""
    for p in _ID_PATTERNS:
        m = re.search(p, url or "")
        if m:
            return m.group(1)
    return None


def _format(entries) -> str:
    """格式化成每行 `[秒數] 文字`。"""
    return "\n".join(f"[{int(e.start)}] {e.text.strip()}" for e in entries if (e.text or "").strip())


def fetch_transcript(video_id: str, use_cache: bool = True) -> Tuple[str, bool]:
    """抓字幕，回傳 (逐字稿, is_chinese)。取不到會拋 CaptionError（ValueError 子類別，附原因分類）。

    字幕是不會變的靜態資料，實測抓一次要 30 秒以上，因此跨重啟快取。
    """
    key = f"{CACHE_PREFIX}{video_id}"
    if use_cache:
        hit = cache.get(key)
        if hit is not None:
            print(f"[captions] 命中快取，直接回傳（{video_id}）", flush=True)
            return hit

    t0 = time.time()
    try:
        tl = YouTubeTranscriptApi().list(video_id)
        result = None
        for lang in _PREFERRED_LANGS:
            try:
                transcript = tl.find_transcript([lang])
            except NoTranscriptFound:
                continue
            # 找到了卻下載失敗（被擋、網路斷線）要往外拋，不能當成「沒有這個語言」
            result = (_format(transcript.fetch()), lang.startswith("zh"))
            break
        if result is None:
            result = (_format(next(iter(tl)).fetch()), False)
        if not result[0].strip():
            raise CaptionError("missing", "transcript has no text")
    except Exception as e:  # noqa: BLE001  一律分類，避免把被擋／斷線誤報成沒有字幕
        error = classify_error(e)
        print(f"[captions] 字幕取得失敗（{error.kind}）：{error.detail}", flush=True)
        raise error from e

    print(f"[captions] 取得字幕耗時 {time.time() - t0:.1f}s（{len(result[0])} 字元）", flush=True)
    if use_cache and result[0]:
        cache.put(key, result[0], result[1])
    return result
