"""低 TPM Groq 模型的分段、輸出限制、速率標頭與錯誤分類：皆不連外。"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import summarize as summary_api
from app.llm import openai_compat
from app.llm.budget import GroqPacer, _seconds, summary_budget, estimate_tokens
from app.llm.util import is_transient, public_reason
from app.models.schemas import SummarizeRequest
from app.prompts.summarize import (budget_summarize_prompt, budget_summarize_system,
                                   summarize_prompt)


def test_only_groq_uses_lower_budget():
    qwen = summary_budget("groq:qwen/qwen3.8-27b")
    assert qwen is not None and qwen.chunk_chars < 12_000
    assert 0 < qwen.max_completion_tokens < qwen.tokens_per_minute
    assert qwen.workers == 1
    assert summary_budget("openai:gpt-4o") is None
    assert summary_budget("ollama:qwen3:4b") is None


def test_budget_prompt_is_shorter_and_still_has_card_schema():
    content = {"type": "youtube", "has_timestamps": True,
               "text": "[0] Hello world.\n[15] Here is a specific setup step."}
    compressed = budget_summarize_prompt(content)
    original = summarize_prompt(content)
    assert len(compressed) < len(original) * .6
    assert all(name in compressed for name in (
        "content_type", "transcript_highlight", "timestamp_seconds", "summary"))
    assert "JSON" in budget_summarize_system("zh-Hant")


def test_groq_completion_cap_and_pacer_only_for_groq():
    fake = httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    with patch.object(openai_compat.httpx, "post", return_value=fake) as post, \
         patch.object(openai_compat.groq_pacer, "before") as before, \
         patch.object(openai_compat.groq_pacer, "observe") as observe, \
         patch.object(openai_compat, "_headers", return_value={"Authorization": "Bearer test"}):
        assert openai_compat._post_chat(
            openai_compat.GROQ, "qwen/qwen3.8-27b", [{"role": "user", "content": "hello"}]
        ) == "ok"
        data = post.call_args.kwargs["json"]
        assert data["max_completion_tokens"] == 1400
        assert data["reasoning_effort"] == "none"
        assert data["model"] == "qwen/qwen3.8-27b"
        assert before.call_count == 1 and observe.call_count == 1
        assert before.call_args.args[1] >= 1400
        before.reset_mock()
        post.reset_mock()
        openai_compat._post_chat(
            openai_compat.OPENAI, "gpt-4o", [{"role": "user", "content": "hello"}])
        assert "max_completion_tokens" not in post.call_args.kwargs["json"]
        before.assert_not_called()


def test_request_too_large_is_permanent_and_has_safe_error():
    response = httpx.Response(429, json={
        "error": {"message": "Request too large for model in organization org_private"}
    })
    with patch.object(openai_compat.httpx, "post", return_value=response), \
         patch.object(openai_compat.groq_pacer, "before"), \
         patch.object(openai_compat.groq_pacer, "observe"), \
         patch.object(openai_compat, "_headers", return_value={"Authorization": "Bearer test"}):
        try:
            openai_compat._post_chat(
                openai_compat.GROQ, "qwen/qwen3.8-27b",
                [{"role": "user", "content": "hello"}])
            assert False
        except Exception as err:
            assert is_transient(err) is False
            assert "org_private" not in public_reason(err)


def test_headers_and_reset_seconds():
    assert _seconds("2m59.56s") == 179.56
    assert _seconds("500ms") == .5
    assert _seconds("not-a-time") is None
    with patch("app.llm.budget.time.monotonic", return_value=10.0):
        pacer = GroqPacer()
        pacer.observe("sample", {
            "x-ratelimit-limit-tokens": "4000",
            "x-ratelimit-remaining-tokens": "100",
            "x-ratelimit-reset-tokens": "25s",
        })
        assert pacer._states["sample"]["tpm"] == 4000
        assert pacer._states["sample"]["remaining"] == 100
        assert pacer._states["sample"]["reset_at"] == 35.0
        assert pacer.retry_delay("sample", {"retry-after": "8"}) == 9.0
    assert estimate_tokens([{"content": "中文ABCDE"}]) >= 2


async def _events(response):
    rows = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        rows.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return rows


def test_stream_splits_groq_and_uses_single_worker_without_affecting_others():
    transcript = "\n".join(f"[{i*15}] 這是第{i}句字幕，包含實際可操作的步驟及知識內容。" for i in range(190))
    source = {"type": "youtube", "video_id": "dQw4w9WgXcQ", "text": transcript,
              "has_timestamps": True, "transcript_source": "captions"}
    captures = []
    def fake_run(_req, _source, chunk, index, multi, on_status=None):
        captures.append(chunk)
        return ({"title": "test", "cards": [{"heading": f"片段{index}", "summary": "ok"}]},
                "Groq/qwen/qwen3.8-27b")
    with patch.object(summary_api, "route_content", return_value=source), \
         patch.object(summary_api, "_run_segment", side_effect=fake_run):
        resp = summary_api.summarize_stream(SummarizeRequest(
            url="https://youtube.com/watch?v=dQw4w9WgXcQ", provider="groq:qwen/qwen3.8-27b"))
        events = asyncio.run(_events(resp))
    assert len(captures) > 2
    assert events[1]["workers"] == 1
    assert all(len(chunk) < 2400 for chunk in captures)
    assert events[-1]["failed_segments"] == 0
    assert events[-1]["segments"] == len(captures)


if __name__ == "__main__":
    test_only_groq_uses_lower_budget()
    test_budget_prompt_is_shorter_and_still_has_card_schema()
    test_groq_completion_cap_and_pacer_only_for_groq()
    test_request_too_large_is_permanent_and_has_safe_error()
    test_headers_and_reset_seconds()
    test_stream_splits_groq_and_uses_single_worker_without_affecting_others()
    print("Groq token budget and pacing tests passed.")
