"""選了 Ollama／免費模型時，字幕失敗不得默默改用 Gemini 雲端轉錄（DeepSRT）。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import summarize as summarize_api
from app.transcript import router as transcript_router

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _route(provider):
    calls = []

    def deepsrt(*_a, **_k):
        calls.append("deepsrt")
        return "[0] 雲端", False

    def whisper(*_a, **_k):
        calls.append("whisper")
        return "[0] 本機", False

    with patch.object(transcript_router.captions, "fetch_transcript", side_effect=ValueError("none")), \
         patch.object(transcript_router.imported_subtitles, "load", return_value=None), \
         patch.object(transcript_router.gemini, "key_count", return_value=1), \
         patch.object(transcript_router.deepsrt, "transcribe", side_effect=deepsrt), \
         patch.object(transcript_router.whisper_local, "transcribe_url", side_effect=whisper):
        content = transcript_router.route_content(
            URL, allow_cloud_fallback=summarize_api._allows_cloud_transcription(provider))
    return calls, content["transcript_source"]


def test_strict_local_or_free_provider_never_uses_gemini_transcription():
    # 一般模式固定送出的免費模型，以及開發者選的 Ollama
    for provider in ("opencode:deepseek-v4-flash-free", "ollama:qwen3:8b", "deepseek:deepseek-chat"):
        calls, source = _route(provider)
        assert calls == ["whisper"], (provider, calls)
        assert source == "whisper"


def test_auto_and_gemini_keep_existing_waterfall():
    for provider in (None, "auto", "gemini"):
        calls, source = _route(provider)
        assert calls == ["deepsrt"], (provider, calls)
        assert source == "deepsrt"


def test_explicit_deep_visual_still_uses_gemini():
    with patch.object(transcript_router.captions, "fetch_transcript", side_effect=ValueError("none")), \
         patch.object(transcript_router.imported_subtitles, "load", return_value=None), \
         patch.object(transcript_router.gemini, "key_count", return_value=1), \
         patch.object(transcript_router.deepsrt, "transcribe", return_value=("[0] 畫面", False)):
        content = transcript_router.route_content(URL, deep_visual=True, allow_cloud_fallback=False)
    assert content["transcript_source"] == "deepsrt"


if __name__ == "__main__":
    test_strict_local_or_free_provider_never_uses_gemini_transcription()
    test_auto_and_gemini_keep_existing_waterfall()
    test_explicit_deep_visual_still_uses_gemini()
    print("Cloud transcription fallback tests passed")
