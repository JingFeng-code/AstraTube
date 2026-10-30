"""低 TPM Groq 模型的分段、輸出限制、速率標頭與錯誤分類：皆不連外。"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import ask as ask_api, summarize as summary_api
from app.llm import openai_compat
from app.llm import router as llm_router
from app.llm.base import TruncatedOutputError
from app.llm.budget import GroqPacer, _seconds, summary_budget, estimate_tokens, groq_pacer
from app.llm.util import is_transient, public_reason
from app.models.schemas import AskRequest, DeepDiveRequest, SummarizeRequest
from app.transcript import subtitle_translation
from app.prompts.summarize import (budget_summarize_prompt, budget_summarize_system,
                                   summarize_prompt)


def test_only_groq_uses_lower_budget():
    qwen = summary_budget("groq:qwen/qwen3.8-27b")
    assert qwen is not None and qwen.chunk_chars < 12_000
    assert 0 < qwen.max_completion_tokens < qwen.tokens_per_minute
    assert qwen.workers == 1
    with patch.object(groq_pacer, "limit_for", return_value=4000):
        reduced = summary_budget("groq:qwen/qwen3.8-27b")
        assert reduced.chunk_chars == 900 and reduced.max_completion_tokens == 700
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
            openai_compat.GROQ, "qwen/qwen3.8-27b", [{"role": "user", "content": "hello"}],
            max_completion_tokens=1400,
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


def _groq_post(responses=None):
    """回傳 (patch 組, 實際送出的 request 清單)。"""
    sent = []
    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return responses or httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    return sent, (patch.object(openai_compat.httpx, "post", side_effect=post),
                  patch.object(openai_compat.groq_pacer, "before"),
                  patch.object(openai_compat.groq_pacer, "observe"),
                  patch.object(openai_compat, "_headers", return_value={"Authorization": "Bearer test"}))


def test_summary_cap_does_not_apply_to_other_calls():
    sent, (a, b, c, d) = _groq_post()
    with a, b, c, d:
        llm_router.generate("groq:qwen/qwen3.8-27b", "寫一份實作文件", "sys")
    # 沒指定上限：用完這一分鐘剩下的額度，不是摘要的 1400
    assert sent[0]["max_completion_tokens"] > 7000


def test_summary_segment_passes_its_own_cap():
    source = {"type": "youtube", "video_id": "dQw4w9WgXcQ", "text": "[0] x", "has_timestamps": True}
    sent, (a, b, c, d) = _groq_post(httpx.Response(200, json={"choices": [{"message": {
        "content": '{"title":"t","cards":[{"heading":"h","summary":"s"}]}'}}]}))
    with a, b, c, d:
        summary_api._run_segment(SummarizeRequest(url="u", provider="groq:qwen/qwen3.8-27b"),
                                 source, "[0] x", 0, False)
    assert sent[0]["max_completion_tokens"] == 1400


def _ask(transcript, provider="groq:qwen/qwen3.8-27b", response=None):
    sent, (a, b, c, d) = _groq_post(response)
    with a, b, c, d, patch.object(ask_api, "_load_transcript", return_value=transcript):
        result = ask_api.ask(AskRequest(question="q", video_id="dQw4w9WgXcQ", provider=provider))
    return result, sent


def test_ask_trims_long_transcript_instead_of_failing():
    transcript = "\n".join(f"[{i}] this is a transcript line about setup steps" for i in range(1300))
    assert len(transcript) > 60_000
    result, sent = _ask(transcript)
    assert sent, "長逐字稿不可以還沒送出就失敗"
    assert estimate_tokens(sent[0]["messages"]) + 1400 <= 8000
    assert "[0] this is" in sent[0]["messages"][0]["content"]
    assert "[1299]" not in sent[0]["messages"][0]["content"]
    assert "影片前段" in result["answer"], "只參考前段時要告知使用者"


def test_ask_short_transcript_is_untouched():
    result, sent = _ask("[0] short transcript")
    assert "[0] short transcript" in sent[0]["messages"][0]["content"]
    assert "影片前段" not in result["answer"]


def test_ask_other_providers_are_not_trimmed():
    transcript = "\n".join(f"[{i}] line" for i in range(5000))
    sent, (a, b, c, d) = _groq_post()
    with a, b, c, d, patch.object(ask_api, "_load_transcript", return_value=transcript):
        ask_api.ask(AskRequest(question="q", video_id="dQw4w9WgXcQ", provider="openai:gpt-x"))
    assert "[4999]" in sent[0]["messages"][0]["content"]
    assert "max_completion_tokens" not in sent[0]


TRUNCATED = {"choices": [{"message": {"content": "只寫到一半"}, "finish_reason": "length"}]}


def test_truncated_reply_raises_without_retry():
    sent, (a, b, c, d) = _groq_post(httpx.Response(200, json=TRUNCATED))
    with a, b, c, d:
        try:
            llm_router.generate("openai:gpt-x", "x", "y")
            assert False, "截斷不可以當成完整內容"
        except TruncatedOutputError as err:
            assert err.partial == "只寫到一半" and err.public_message
    assert len(sent) == 1, "重試同一份請求沒有意義"


def test_ask_and_deepdive_show_partial_with_notice():
    result, _ = _ask("[0] x", provider="openai:gpt-x", response=httpx.Response(200, json=TRUNCATED))
    assert result["answer"].startswith("只寫到一半") and "截斷" in result["answer"]
    _, (a, b, c, d) = _groq_post(httpx.Response(200, json=TRUNCATED))
    with a, b, c, d:
        deep = summary_api.deepdive(DeepDiveRequest(provider="openai:gpt-x", source_title="t",
                                                    card={"heading": "h", "summary": "s"}))
    assert deep["content"].startswith("只寫到一半") and "截斷" in deep["content"]


def test_truncated_summary_keeps_cards_and_warns():
    partial = '{"title":"t","cards":[{"heading":"h","summary":"s"},{"heading":"第二張'
    source = {"type": "article", "text": "內容"}
    _, (a, b, c, d) = _groq_post(httpx.Response(200, json={"choices": [
        {"message": {"content": partial}, "finish_reason": "length"}]}))
    with a, b, c, d, patch.object(summary_api, "route_content", return_value=source):
        events = asyncio.run(_events(summary_api.summarize_stream(SummarizeRequest(
            url="https://example.com", provider="groq:qwen/qwen3.8-27b"))))
    cards = next(e for e in events if e["type"] == "cards")
    assert cards["truncated"] is True and cards["cards"][0]["heading"] == "h"


def _coverage_generate(second):
    """第一次回傳只到開頭的卡片，觸發覆蓋率補做；第二次由 second 決定結果。"""
    first = json.dumps({"title": "t", "cards": [
        {"heading": "開頭", "summary": "s", "timestamp_seconds": 0}]}, ensure_ascii=False)
    return [(first, "m"), second]


def _audit_chunk():
    return "\n".join(f"[{t}] {'逐字稿內容' * 10}" for t in range(0, 1000, 60))


def test_truncated_coverage_reply_keeps_cards_and_warns():
    partial = '{"title":"t","cards":[{"heading":"補做","summary":"s","timestamp_seconds":600},{"heading":"第二張'
    side_effect = _coverage_generate(TruncatedOutputError("x", partial, "m"))
    with patch.object(summary_api.llm_router, "generate", side_effect=side_effect):
        data, _ = summary_api._run_segment(SummarizeRequest(url="https://example.com", provider="auto"),
                                           {"type": "youtube", "has_timestamps": True},
                                           _audit_chunk(), 0, False)
    assert [c["heading"] for c in data["cards"]][:2] == ["開頭", "補做"]
    assert data["truncated"] is True


def test_unrepairable_coverage_reply_still_warns():
    side_effect = _coverage_generate(TruncatedOutputError("x", "", "m"))
    with patch.object(summary_api.llm_router, "generate", side_effect=side_effect):
        data, _ = summary_api._run_segment(SummarizeRequest(url="https://example.com", provider="auto"),
                                           {"type": "youtube", "has_timestamps": True},
                                           _audit_chunk(), 0, False)
    assert [c["heading"] for c in data["cards"]] == ["開頭"]
    assert data["truncated"] is True


def test_complete_coverage_reply_is_not_marked_truncated():
    more = json.dumps({"cards": [{"heading": "補做", "summary": "s", "timestamp_seconds": 600}]}, ensure_ascii=False)
    side_effect = _coverage_generate((more, "m"))
    with patch.object(summary_api.llm_router, "generate", side_effect=side_effect):
        data, _ = summary_api._run_segment(SummarizeRequest(url="https://example.com", provider="auto"),
                                           {"type": "youtube", "has_timestamps": True},
                                           _audit_chunk(), 0, False)
    assert [c["heading"] for c in data["cards"]] == ["開頭", "補做"]
    assert "truncated" not in data


def test_truncated_translation_is_not_cached():
    response = '{"translations":[{"id":0,"text":"譯文"}]}'
    _, (a, b, c, d) = _groq_post(httpx.Response(200, json={"choices": [
        {"message": {"content": response}, "finish_reason": "length"}]}))
    with a, b, c, d, patch.object(subtitle_translation.translation_cache, "get", return_value=None), \
         patch.object(subtitle_translation.translation_cache, "put") as put:
        try:
            subtitle_translation.translate_batch([{"id": 0, "text": "hello"}], provider="openai:gpt-x")
            assert False, "截斷的翻譯不可以成功"
        except TruncatedOutputError:
            pass
    put.assert_not_called()


if __name__ == "__main__":
    test_summary_cap_does_not_apply_to_other_calls()
    test_summary_segment_passes_its_own_cap()
    test_ask_trims_long_transcript_instead_of_failing()
    test_ask_short_transcript_is_untouched()
    test_ask_other_providers_are_not_trimmed()
    test_truncated_reply_raises_without_retry()
    test_ask_and_deepdive_show_partial_with_notice()
    test_truncated_summary_keeps_cards_and_warns()
    test_truncated_coverage_reply_keeps_cards_and_warns()
    test_unrepairable_coverage_reply_still_warns()
    test_complete_coverage_reply_is_not_marked_truncated()
    test_truncated_translation_is_not_cached()
    test_only_groq_uses_lower_budget()
    test_budget_prompt_is_shorter_and_still_has_card_schema()
    test_groq_completion_cap_and_pacer_only_for_groq()
    test_request_too_large_is_permanent_and_has_safe_error()
    test_headers_and_reset_seconds()
    test_stream_splits_groq_and_uses_single_worker_without_affecting_others()
    print("Groq token budget and pacing tests passed.")
