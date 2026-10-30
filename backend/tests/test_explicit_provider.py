"""未選擇 AI 時不可以走到自動接力或付費供應商（不呼叫真實 API）。"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.api import ask as ask_api, implement as implement_api, summarize as summarize_api  # noqa: E402
from app.llm import opencode, router  # noqa: E402
from app.llm.base import NotConfiguredError  # noqa: E402
from app.models.schemas import AskRequest, DeepDiveRequest, ImplementRequest, SummarizeRequest  # noqa: E402

NOT_SELECTED = (None, "", "   ", "smart", "no-such-provider", "no-such-provider:x")


def _no_upstream():
    """任何上游呼叫都算失敗。"""
    return (patch.object(opencode, "generate_free", side_effect=AssertionError("不可呼叫免費接力")),
            patch.object(router, "_call", side_effect=AssertionError("不可呼叫任何供應商")),
            patch.object(router, "configured_paid_chain",
                         return_value=[(router.DEEPSEEK, "deepseek-chat")]))


def _events(response):
    async def collect():
        rows = []
        async for chunk in response.body_iterator:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            rows.extend(json.loads(item) for item in text.splitlines() if item.strip())
        return rows
    return asyncio.run(collect())


def test_is_explicit_only_accepts_real_choices():
    for provider in NOT_SELECTED:
        assert not router.is_explicit(provider), provider
    for provider in ("auto", "free", "gemini", "gemini:x", "ollama:qwen3:4b", "groq:a/b", "openai:gpt-x"):
        assert router.is_explicit(provider), provider


def test_generate_refuses_when_no_ai_is_selected():
    free, call, chain = _no_upstream()
    with free, call, chain:
        for provider in NOT_SELECTED:
            try:
                router.generate(provider, "摘要")
                raise AssertionError(f"{provider!r} 應該被拒絕")
            except NotConfiguredError as exc:
                assert "AI" in str(exc)


def test_deepdive_without_provider_never_reaches_paid_chain():
    free, call, chain = _no_upstream()
    req = DeepDiveRequest(provider=None, source_title="t",
                          card={"heading": "h", "summary": "s", "timestamp_seconds": 0})
    with free, call, chain:
        try:
            summarize_api.deepdive(req)
            raise AssertionError("Expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 400


def test_ask_without_provider_is_rejected_before_loading_transcript():
    with patch.object(ask_api, "_load_transcript", side_effect=AssertionError("不可先取逐字稿")), \
         patch.object(ask_api.gemini, "generate_chat", side_effect=AssertionError("不可呼叫 Gemini")):
        try:
            ask_api.ask(AskRequest(question="q", video_id="dQw4w9WgXcQ", provider=None))
            raise AssertionError("Expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 400


def test_stream_without_provider_does_not_touch_the_video():
    # 沒選 AI 時也不能先把影片交給 Gemini 轉錄
    with patch.object(summarize_api, "route_content", side_effect=AssertionError("不可先擷取內容")):
        events = _events(summarize_api.summarize_stream(SummarizeRequest(url="https://example.com")))
    assert events[-1]["type"] == "fatal"
    assert "AI" in events[-1]["error"]


def test_non_stream_summarize_without_provider_is_rejected():
    with patch.object(summarize_api, "route_content", side_effect=AssertionError("不可先擷取內容")):
        try:
            summarize_api.summarize(SummarizeRequest(url="https://example.com"))
            raise AssertionError("Expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 400


def test_implement_teach_without_provider_uses_local_fallback():
    # 沒裝 CLI 又沒選 AI：給內建安裝說明，不呼叫任何供應商
    free, call, chain = _no_upstream()
    req = ImplementRequest(provider=None, video_title="t", cards=[{"heading": "h", "summary": "s"}])
    with free, call, chain, patch.object(implement_api.agent_cli, "detect", return_value=[]):
        events = _events(implement_api.implement(req))
    teach = next(e for e in events if e["type"] == "teach")
    assert teach["model"] == "" and teach["content"]


if __name__ == "__main__":
    test_is_explicit_only_accepts_real_choices()
    test_generate_refuses_when_no_ai_is_selected()
    test_deepdive_without_provider_never_reaches_paid_chain()
    test_ask_without_provider_is_rejected_before_loading_transcript()
    test_stream_without_provider_does_not_touch_the_video()
    test_non_stream_summarize_without_provider_is_rejected()
    test_implement_teach_without_provider_uses_local_fallback()
    print("Explicit provider tests passed.")
