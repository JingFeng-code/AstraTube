"""內容擷取的總入口：YouTube 走三層轉錄瀑布，其餘先當文章、再退回影音轉寫。

轉錄瀑布（任一層失敗自動落到下一層）：
  預設        1. captions（免費秒回）→ 2. deepsrt（需 GEMINI_API_KEY）→ 3. whisper 本機轉寫
  深視覺模式  1. deepsrt（連畫面/簡報一起讀）→ 2. captions → 3. whisper

深視覺模式下若字幕也拿得到，會把字幕當成口說逐字稿的**時間軸基準**交給 DeepSRT：
Gemini 的畫面時間戳準、口說時間戳會單調漂移（實測片尾差到 +98 秒），
所以「口說用字幕、畫面用 Gemini」兩邊各取所長，比只信任一邊都準。
"""
from typing import Optional, TypedDict

from app.llm import gemini
from app.services.article_fetcher import fetch_article
from app.transcript import captions, deepsrt, whisper_local


class Content(TypedDict):
    """摘要流程共用的內容結構。"""
    type: str                        # youtube / article / video
    video_id: Optional[str]
    title: Optional[str]
    text: str
    is_chinese: bool
    has_timestamps: bool
    transcript_source: Optional[str]  # deepsrt / deepsrt+captions / captions / whisper；文章為 None


def _fetch_captions(video_id: str) -> Optional[tuple[str, bool]]:
    """抓字幕，抓不到回 None。結果有跨重啟快取，重複呼叫不會重打網路。"""
    try:
        return captions.fetch_transcript(video_id)
    except Exception as e:  # noqa: BLE001
        print(f"[transcript] 字幕取得失敗：{e}", flush=True)
        return None


def _try_deepsrt(url: str, video_id: str) -> Optional[Content]:
    """DeepSRT 層：沒 Gemini 金鑰或失敗回 None，由呼叫端落到下一層。"""
    if gemini.key_count() == 0:
        return None
    hit = _fetch_captions(video_id)
    reference = hit[0] if hit else None
    try:
        text, is_chinese = deepsrt.transcribe(url, video_id, reference_transcript=reference)
        return _pack("youtube", video_id, text, is_chinese,
                     "deepsrt+captions" if reference else "deepsrt")
    except Exception as e:  # noqa: BLE001
        print(f"[transcript] DeepSRT 失敗：{e}", flush=True)
        # DeepSRT 掛了但字幕已經抓到手，直接用字幕，不必讓呼叫端再抓一次
        if hit:
            return _pack("youtube", video_id, hit[0], hit[1], "captions")
        return None


def _try_captions(video_id: str) -> Optional[Content]:
    """字幕層：抓不到回 None，由呼叫端落到下一層。"""
    hit = _fetch_captions(video_id)
    return _pack("youtube", video_id, hit[0], hit[1], "captions") if hit else None


def _youtube(url: str, video_id: str, deep_visual: bool) -> Content:
    """YouTube 三層轉錄瀑布。預設字幕優先（省 Gemini 額度）；深視覺模式 DeepSRT 優先。"""
    order = (lambda: _try_deepsrt(url, video_id), lambda: _try_captions(video_id)) if deep_visual \
        else (lambda: _try_captions(video_id), lambda: _try_deepsrt(url, video_id))
    for layer in order:
        result = layer()
        if result is not None:
            return result

    text, is_chinese = whisper_local.transcribe_url(url, cache_key=video_id)
    return _pack("youtube", video_id, text, is_chinese, "whisper")


def _pack(kind: str, video_id: Optional[str], text: str, is_chinese: bool,
          source: Optional[str]) -> Content:
    return Content(type=kind, video_id=video_id, title=None, text=text,
                   is_chinese=is_chinese, has_timestamps=True, transcript_source=source)


def route_content(url: str, deep_visual: bool = False) -> Content:
    """依網址型態取得內容。取不到會拋出例外（ValueError 代表使用者輸入問題）。"""
    video_id = captions.extract_video_id(url)
    if video_id:
        return _youtube(url, video_id, deep_visual)

    try:
        title, text = fetch_article(url)
        return Content(type="article", video_id=None, title=title, text=text,
                       is_chinese=False, has_timestamps=False, transcript_source=None)
    except Exception:
        text, is_chinese = whisper_local.transcribe_url(url)
        return _pack("video", None, text, is_chinese, "whisper")
