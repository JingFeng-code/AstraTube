"""給瀏覽器看的錯誤訊息不可包含上游回應內容，也要說對是哪種服務（不呼叫真實 API）。"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic  # noqa: E402
import httpx  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from app.api import ask as ask_api, implement as implement_api  # noqa: E402
from app.api import subtitles as subtitles_api, summarize as summarize_api  # noqa: E402
from app.llm import anthropic_api, gemini, opencode, openai_compat, router  # noqa: E402
from app.llm.util import user_error  # noqa: E402
from app.models.schemas import AskRequest, DeepDiveRequest, ImplementRequest, SummarizeRequest  # noqa: E402
from app.transcript import subtitle_translation  # noqa: E402

SECRET = "UPSTREAM_ECHO sk-not-a-real-key 字幕原文"
BAD_RESPONSES = {
    "非 JSON": httpx.Response(200, text=SECRET),
    "200 內含 error": httpx.Response(200, json={"error": {"message": SECRET}}),
    "HTTP 400": httpx.Response(400, text=SECRET),
    "HTTP 401": httpx.Response(401, text=SECRET),
}


def _failing_openai(response):
    return (patch.object(openai_compat, "_headers", return_value={"Authorization": "Bearer x"}),
            patch.object(openai_compat.httpx, "post", return_value=response),
            patch("app.llm.util.time.sleep"))


def _events(response):
    async def collect():
        rows = []
        async for chunk in response.body_iterator:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            rows.extend(json.loads(item) for item in text.splitlines() if item.strip())
        return rows
    return asyncio.run(collect())


def test_stream_seg_error_never_contains_upstream_body():
    source = {"type": "article", "text": "內容"}
    for name, response in BAD_RESPONSES.items():
        a, b, c = _failing_openai(response)
        with a, b, c, patch.object(summarize_api, "route_content", return_value=source):
            events = _events(summarize_api.summarize_stream(
                SummarizeRequest(url="https://example.com", provider="openai:gpt-x")))
        errors = [e["error"] for e in events if e["type"] == "seg_error"]
        assert errors, name
        assert "UPSTREAM_ECHO" not in errors[0], (name, errors[0])
        assert errors[0].strip(), name


def test_ask_and_deepdive_never_contain_upstream_body():
    for name, response in BAD_RESPONSES.items():
        a, b, c = _failing_openai(response)
        with a, b, c, patch.object(ask_api, "_load_transcript", return_value="[0] x"):
            try:
                ask_api.ask(AskRequest(question="q", video_id="dQw4w9WgXcQ", provider="openai:gpt-x"))
                raise AssertionError(name)
            except HTTPException as exc:
                assert "UPSTREAM_ECHO" not in exc.detail, (name, exc.detail)
        a, b, c = _failing_openai(response)
        with a, b, c:
            try:
                summarize_api.deepdive(DeepDiveRequest(provider="openai:gpt-x", source_title="t",
                                                       card={"heading": "h", "summary": "s"}))
                raise AssertionError(name)
            except HTTPException as exc:
                assert "UPSTREAM_ECHO" not in exc.detail, (name, exc.detail)


def test_implement_never_contains_upstream_body():
    cards = [{"heading": "h", "summary": "s"}]
    with patch.object(router, "generate", side_effect=RuntimeError(SECRET)), \
         patch.object(implement_api.agent_cli, "detect", return_value=[]):
        events = _events(implement_api.implement(ImplementRequest(provider="openai:gpt-x", cards=cards)))
    assert "UPSTREAM_ECHO" not in json.dumps(events, ensure_ascii=False)
    with patch.object(router, "generate", side_effect=RuntimeError(SECRET)), \
         patch.object(implement_api.agent_cli, "detect", return_value=[]), \
         patch.object(implement_api, "workdir_for", return_value=Path(__file__).parent / "_tmp_never_used"):
        try:
            events = _events(implement_api.implement(ImplementRequest(
                provider="openai:gpt-x", cards=cards, cli="openai:gpt-x")))
        finally:
            import shutil
            shutil.rmtree(Path(__file__).parent / "_tmp_never_used", ignore_errors=True)
    assert "UPSTREAM_ECHO" not in json.dumps(events, ensure_ascii=False)


def test_opencode_bad_responses_are_public_safe():
    for name in ("非 JSON", "200 內含 error"):
        with patch.object(opencode.httpx, "post", return_value=BAD_RESPONSES[name]):
            try:
                opencode._post_chat("x-free", [{"role": "user", "content": "hi"}])
                raise AssertionError(name)
            except Exception as exc:  # noqa: BLE001
                assert "UPSTREAM_ECHO" not in user_error(exc), name


def test_anthropic_status_error_is_public_safe():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    upstream = anthropic.APIStatusError(SECRET, response=httpx.Response(429, request=request), body=None)
    client = patch.object(anthropic_api, "_client")
    with client as mocked:
        mocked.return_value.messages.create.side_effect = upstream
        try:
            anthropic_api._once("claude-x", [{"role": "user", "content": "hi"}], "")
            raise AssertionError("Expected error")
        except Exception as exc:  # noqa: BLE001
            shown = user_error(exc)
            assert "UPSTREAM_ECHO" not in shown and "HTTP 429" in shown, shown


def test_sdk_errors_only_show_status():
    class SdkError(Exception):
        code = 429

    with patch.object(gemini, "generate", side_effect=SdkError(SECRET)), \
         patch.object(router.gemini, "generate", side_effect=SdkError(SECRET)):
        try:
            router.generate("gemini:x", "hi")
            raise AssertionError("Expected error")
        except SdkError as exc:
            shown = user_error(exc)
            assert "UPSTREAM_ECHO" not in shown and "HTTP 429" in shown
    assert "UPSTREAM_ECHO" not in user_error(RuntimeError(SECRET))
    assert user_error(RuntimeError(SECRET)).strip()
    assert user_error(None).strip()


def test_our_own_messages_are_still_shown():
    assert user_error(ValueError("模型輸出不是卡片")) == "模型輸出不是卡片"
    assert user_error(router.NotConfiguredError("請先設定")) == "請先設定"
    from app.llm.base import ProviderError
    ollama_error = ProviderError("Ollama 超過 5 分鐘沒有任何輸出")
    assert user_error(ollama_error, "ollama:qwen3") == "Ollama 超過 5 分鐘沒有任何輸出"
    assert "Ollama 超過" not in user_error(ollama_error, "openai:gpt-x")


def _translate_error(provider, error):
    source = {"cues": [{"text": "hi"}]}
    with patch.object(subtitles_api, "get_subtitles", return_value=source), \
         patch.object(subtitle_translation, "resolve_provider", return_value=("x", "x", "x")), \
         patch.object(subtitle_translation, "translate_batch", side_effect=error):
        try:
            subtitles_api.translate_subtitles(subtitles_api.TranslateRequest(
                platform="youtube", video_id="dQw4w9WgXcQ", translation_provider=provider))
            raise AssertionError("Expected HTTPException")
        except HTTPException as exc:
            return exc.detail


def test_translation_error_names_the_right_service_and_is_complete():
    http = openai_compat.http_error("OpenAI", 401, SECRET)
    cloud = _translate_error("openai:gpt-x", http)
    assert "免費" not in cloud and "雲端 AI" in cloud and "HTTP 401" in cloud
    assert "UPSTREAM_ECHO" not in cloud
    assert "（" not in cloud, "不再包兩層括號"
    assert cloud.rstrip().endswith("。"), f"建議文字不可被截掉：{cloud}"
    assert "免費模型" in _translate_error("opencode", http)
    from app.llm.base import ProviderError
    local = _translate_error("ollama:qwen3", ProviderError("無法連線 Ollama"))
    assert "本機 Ollama" in local and "無法連線 Ollama" in local


def test_long_free_chain_message_keeps_status_and_advice():
    # 模型很多時，狀態碼與建議不可以被截掉
    live = [f"model-{i}-free" for i in range(9)]
    with patch.object(opencode, "list_free_models", return_value=(live, "live")), \
         patch.object(opencode.httpx, "post", return_value=httpx.Response(429, text=SECRET)), \
         patch("app.llm.util.time.sleep"):
        try:
            opencode.generate_free([{"role": "user", "content": "hi"}])
            raise AssertionError("Expected error")
        except Exception as exc:  # noqa: BLE001
            detail = _translate_error("opencode", exc)
    assert "HTTP 429" in detail and "請稍等幾分鐘" in detail and "UPSTREAM_ECHO" not in detail


def test_groq_final_429_does_not_say_still_waiting():
    response = httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": SECRET}})
    a, b, c = _failing_openai(response)
    with a, b, c, patch.object(openai_compat.groq_pacer, "before"):
        try:
            router.generate("groq:llama-x", "x", "y")
            raise AssertionError("Expected error")
        except Exception as exc:  # noqa: BLE001
            shown = user_error(exc)
    assert "正在" not in shown and "仍未成功" in shown and "UPSTREAM_ECHO" not in shown


if __name__ == "__main__":
    test_stream_seg_error_never_contains_upstream_body()
    test_ask_and_deepdive_never_contain_upstream_body()
    test_implement_never_contains_upstream_body()
    test_opencode_bad_responses_are_public_safe()
    test_anthropic_status_error_is_public_safe()
    test_sdk_errors_only_show_status()
    test_our_own_messages_are_still_shown()
    test_translation_error_names_the_right_service_and_is_complete()
    test_long_free_chain_message_keeps_status_and_advice()
    test_groq_final_429_does_not_say_still_waiting()
    print("Public error tests passed.")
