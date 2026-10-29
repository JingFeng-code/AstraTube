"""YouTube 官方／自動字幕（youtube-transcript-api），預設瀑布的第一層。"""
import re
import time
from typing import Optional, Tuple

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from app.transcript import cache

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
    """抓字幕，回傳 (逐字稿, is_chinese)。取不到會拋 ValueError。

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
                entries = tl.find_transcript([lang]).fetch()
                result = (_format(entries), lang.startswith("zh"))
                break
            except Exception:
                continue
        if result is None:
            result = (_format(next(iter(tl)).fetch()), False)
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        raise ValueError(f"無法取得字幕：{e}")

    print(f"[captions] 取得字幕耗時 {time.time() - t0:.1f}s（{len(result[0])} 字元）", flush=True)
    if use_cache and result[0]:
        cache.put(key, result[0], result[1])
    return result
