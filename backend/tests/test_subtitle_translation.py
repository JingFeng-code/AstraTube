"""逐句翻譯測試：Mock LLM，不連線任何 AI API，也不需要密鑰。"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import subtitles
from app.transcript import subtitle_translation, translation_cache
from app.llm import opencode


def test_translation_validates_exact_ids():
    raw = json.dumps({"translations": [
        {"id": 2, "text": "您好"},
        {"id": 4, "text": "世界"},
    ]}, ensure_ascii=False)
    assert subtitle_translation._validated_json(raw, {2, 4}) == {2: "您好", 4: "世界"}
    for payload in (
        {"translations": [{"id": 2, "text": "您好"}]},
        {"translations": [{"id": 2, "text": "您好"}, {"id": 2, "text": "重複"}]},
        {"translations": [{"id": "2", "text": "錯誤"}]},
        {"translations": [{"id": 2, "text": "  "}, {"id": 4, "text": "OK"}]},
    ):
        try:
            subtitle_translation._validated_json(json.dumps(payload), {2, 4})
            assert False, "Should reject missing, duplicate, invalid or empty translations"
        except ValueError:
            pass


def test_reuses_translation_cache_without_model_call():
    cues = [{"id": 0, "text": "Hello"}, {"id": 1, "text": "World"}]
    with patch.object(translation_cache, "get", return_value="已快取"), \
         patch.object(opencode, "generate") as generate:
        translated, model = subtitle_translation.translate_batch(cues)
    generate.assert_not_called()
    assert translated == [
        {"id": 0, "translation": "已快取"}, {"id": 1, "translation": "已快取"}
    ]
    assert model == opencode.DEFAULT_FREE_MODEL


def test_calls_only_free_model_and_preserves_ids():
    cues = [{"id": 5, "text": "Create an API"}, {"id": 6, "text": "Press Start"}]
    response = '{"translations":[{"id":6,"text":"按下開始"}]}'
    with patch.object(translation_cache, "get", side_effect=lambda text, model:
                      "建立 API" if text == "Create an API" else None), \
         patch.object(translation_cache, "put") as put, \
         patch.object(opencode, "generate", return_value=(response, "free")) as generate:
        translated, _ = subtitle_translation.translate_batch(cues)
    args, kwargs = generate.call_args
    assert kwargs["model"] == opencode.DEFAULT_FREE_MODEL
    assert "Press Start" in args[0]
    assert "Create an API" not in args[0]
    assert translated[1]["translation"] == "按下開始"
    put.assert_called_once_with("Press Start", opencode.DEFAULT_FREE_MODEL, "按下開始")


def test_cache_persists_and_separates_models():
    with TemporaryDirectory() as folder:
        with patch.object(translation_cache, "CACHE_DIR", Path(folder)):
            translation_cache.put("hello", "free-model-a", "你好")
            assert translation_cache.get("hello", "free-model-a") == "你好"
            assert translation_cache.get("hello", "different-model") is None
            assert translation_cache.get("different sentence", "free-model-a") is None


def test_endpoint_binds_to_server_transcript_and_pages():
    sample = {
        "platform": "bilibili",
        "video_id": "BV1B7411m7LV",
        "page": 2,
        "cues": [{"text": "first"}, {"text": "second"}, {"text": "third"}],
    }
    with patch.object(subtitles, "get_subtitles", return_value=sample) as get_source, \
         patch.object(subtitles.subtitle_translation, "translate_batch", return_value=(
             [{"id": 1, "translation": "第二句"}, {"id": 2, "translation": "第三句"}], "free-model",
         )) as translate:
        result = subtitles.translate_subtitles(subtitles.TranslateRequest(
            platform="bilibili", video_id="BV1B7411m7LV", page=2,
            start_index=1, batch_size=2
        ))
    get_source.assert_called_once_with("bilibili", "BV1B7411m7LV", 2, "opencode")
    translate.assert_called_once_with([
        {"id": 1, "text": "second"}, {"id": 2, "text": "third"},
    ], provider="opencode")
    assert result["next_index"] == 3
    assert result["translations"][0]["id"] == 1


def test_invalid_batch_and_error_do_not_forge_success():
    for kwargs in ({"batch_size": 17}, {"start_index": -1}, {"page": 0},
                   {"platform": "unknown"}):
        try:
            subtitles.TranslateRequest(video_id="M7lc1UVf-VE", **kwargs)
            assert False, "Expected request validation failure"
        except ValidationError:
            pass
    with patch.object(subtitles, "get_subtitles", return_value={"cues": [{"text": "Hi"}]}), \
         patch.object(subtitles.subtitle_translation, "translate_batch",
                      side_effect=ValueError("翻譯輸出格式錯誤")):
        try:
            subtitles.translate_subtitles(subtitles.TranslateRequest(
                platform="youtube", video_id="M7lc1UVf-VE"
            ))
            assert False, "Expected HTTP error"
        except HTTPException as exc:
            assert exc.status_code == 502


def test_translation_error_shows_provider_reason_without_leaking_other_details():
    from app.llm.base import ProviderError
    cases = [
        (ProviderError("OpenCode HTTP 429：rate limited 免費額度或請求次數已達上限"), "HTTP 429", True),
        (RuntimeError("internal transcript: 秘密逐字稿內容"), "秘密逐字稿", False),
    ]
    for error, needle, visible in cases:
        with patch.object(subtitles, "get_subtitles", return_value={"cues": [{"text": "Hi"}]}), \
             patch.object(subtitles.subtitle_translation, "translate_batch", side_effect=error):
            try:
                subtitles.translate_subtitles(subtitles.TranslateRequest(platform="youtube", video_id="M7lc1UVf-VE"))
                assert False, "Expected HTTP error"
            except HTTPException as exc:
                assert exc.status_code == 502
                assert (needle in exc.detail) is visible, exc.detail


def test_bounded_batch():
    too_long = [{"id": 1, "text": "x" * 801}]
    try:
        subtitle_translation.translate_batch(too_long)
        assert False, "Should reject overlong cues"
    except ValueError:
        pass


def test_ollama_translation_uses_own_model_and_cache():
    """不同引擎不得共用快取，且 Ollama 失敗時不能落到雲端。"""
    from app.llm import ollama
    label = "ollama:qwen3:4b"
    assert subtitle_translation.resolve_provider(label) == ("ollama", "qwen3:4b", label)
    assert subtitle_translation.resolve_provider("opencode")[2] == opencode.DEFAULT_FREE_MODEL
    for invalid in ("", "openai:gpt-4.1", "gemini", "ollama:", "ollama:qwen3:4b-cloud"):
        try:
            subtitle_translation.resolve_provider(invalid)
            assert False, "Invalid translation provider should fail: " + invalid
        except ValueError:
            pass
    fake = '{"translations":[{"id":0,"text":"你好"}]}'
    with patch.object(translation_cache, "get", return_value=None) as cached, \
         patch.object(translation_cache, "put") as put, \
         patch.object(ollama, "generate", return_value=(fake, "Ollama/qwen3:4b")) as local, \
         patch.object(opencode, "generate") as cloud:
        result, name = subtitle_translation.translate_batch([{"id":0,"text":"Hello"}], provider=label)
    assert name == label
    assert result == [{"id":0,"translation":"你好"}]
    cached.assert_called_once_with("Hello", label)
    put.assert_called_once_with("Hello", label, "你好")
    local.assert_called_once()
    assert local.call_args.kwargs["model"] == "qwen3:4b"
    cloud.assert_not_called()


def test_get_cached_translation_is_provider_specific():
    with patch.object(subtitles.captions, "fetch_transcript", return_value=("[0] Hi", False)), \
         patch.object(translation_cache, "get", side_effect=lambda source, key:
                      "本地的譯文" if key == "ollama:qwen3:4b" else None):
        local = subtitles.get_subtitles("youtube", "M7lc1UVf-VE", 1, "ollama:qwen3:4b")
        free = subtitles.get_subtitles("youtube", "M7lc1UVf-VE", 1, "opencode")
    assert local["cues"][0]["translation"] == "本地的譯文"
    assert free["cues"][0]["translation"] is None
    assert local["translation_status"] == "complete"


def test_rejects_paid_provider_before_asking_model():
    with patch.object(subtitles, "get_subtitles") as load:
        try:
            subtitles.translate_subtitles(subtitles.TranslateRequest(
                platform="youtube", video_id="M7lc1UVf-VE", translation_provider="openai:gpt-4.1"
            ))
            assert False
        except HTTPException as exc:
            assert exc.status_code == 400
    load.assert_not_called()


if __name__ == "__main__":
    test_translation_validates_exact_ids()
    test_reuses_translation_cache_without_model_call()
    test_calls_only_free_model_and_preserves_ids()
    test_cache_persists_and_separates_models()
    test_endpoint_binds_to_server_transcript_and_pages()
    test_invalid_batch_and_error_do_not_forge_success()
    test_translation_error_shows_provider_reason_without_leaking_other_details()
    test_bounded_batch()
    test_ollama_translation_uses_own_model_and_cache()
    test_get_cached_translation_is_provider_specific()
    test_rejects_paid_provider_before_asking_model()
    print("subtitle translation tests passed")
