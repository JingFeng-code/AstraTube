"""Anthropic、Gemini、Ollama 回覆被截斷時的偵測與呼叫端處理：所有回應皆 mock，不連外。"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.cli as agent_cli  # noqa: E402
import app.api.implement as impl  # noqa: E402
from app.api import ask as ask_api, subtitles as subtitles_api, summarize as summary_api  # noqa: E402
from app.llm import anthropic_api, gemini, ollama, openai_compat  # noqa: E402
from app.llm import router as llm_router  # noqa: E402
from app.llm.base import EmptyResponseError, ProviderError, TruncatedOutputError  # noqa: E402
from app.llm.util import user_error  # noqa: E402
from app.models.schemas import AskRequest, Card, DeepDiveRequest, ImplementRequest, SummarizeRequest  # noqa: E402
from app.prompts.implement import FILE_BEGIN  # noqa: E402
from app.transcript import subtitle_translation, translation_cache  # noqa: E402

# 部分內容裡放一段記號：測到它出現在錯誤訊息裡，就代表上游內容外洩了
SECRET = "UPSTREAM_ECHO"
PARTIAL = f"只寫到一半{SECRET}"
PARTIAL_CARDS = ('{"title":"t","cards":[{"heading":"h","summary":"s"},'
                 f'{{"heading":"第二張{SECRET}')
ANTHROPIC = "anthropic:claude-x"
GEMINI = "gemini:gemini-x"
OLLAMA = "ollama:qwen3:4b"
PROVIDERS = (ANTHROPIC, GEMINI, OLLAMA)


class FakeStream:
    def __init__(self, lines):
        self.lines = lines
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self.lines


class FakeOllamaClient:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def stream(self, _method, _url, json):  # noqa: A002  名稱要和 httpx 的參數一致
        return FakeStream(self.lines)


def _ollama_lines(text: str, reason: str | None) -> list[str]:
    last = {"message": {"role": "assistant", "content": ""}, "done": True}
    if reason:
        last["done_reason"] = reason
    return [json.dumps({"message": {"role": "assistant", "content": text}, "done": False}),
            json.dumps(last)]


def _gemini_response(text: str, reason: str) -> types.GenerateContentResponse:
    """用 SDK 真正的型別解析 REST 回應，確認 finishReason 轉換後讀得到。"""
    parts = [{"text": text}] if text else []
    return types.GenerateContentResponse.model_validate(
        {"candidates": [{"finishReason": reason, "content": {"role": "model", "parts": parts}}]})


def _anthropic_response(text: str, reason: str) -> SimpleNamespace:
    content = [SimpleNamespace(type="text", text=text)] if text else []
    return SimpleNamespace(content=content, stop_reason=reason, stop_details=None)


class _Upstream:
    """讓三家供應商都回傳指定內容，並記錄實際發出幾次請求。"""

    def __init__(self, provider: str, text: str, truncated: bool = True, keys: int = 1):
        self.provider, self.text, self.truncated, self.keys = provider, text, truncated, keys
        self.client = MagicMock()
        self.patches = []

    def __enter__(self):
        if self.provider == ANTHROPIC:
            reason = "max_tokens" if self.truncated else "end_turn"
            self.client.messages.create.return_value = _anthropic_response(self.text, reason)
            self.patches = [patch.object(anthropic_api, "_client", return_value=self.client)]
        elif self.provider == GEMINI:
            reason = "MAX_TOKENS" if self.truncated else "STOP"
            self.client.models.generate_content.return_value = _gemini_response(self.text, reason)
            self.patches = [patch.object(gemini, "_client", return_value=self.client),
                            patch.object(gemini, "_keys",
                                         return_value=[f"k{i}" for i in range(self.keys)])]
        else:
            lines = _ollama_lines(self.text, "length" if self.truncated else "stop")
            self.patches = [patch.object(ollama.httpx, "Client",
                                         return_value=FakeOllamaClient(lines))]
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, *_args):
        for item in self.patches:
            item.stop()

    @property
    def calls(self) -> int:
        if self.provider == ANTHROPIC:
            return self.client.messages.create.call_count
        return self.client.models.generate_content.call_count


def _ask(provider: str) -> dict:
    with patch.object(ask_api, "_load_transcript", return_value="[0] 逐字稿"):
        return ask_api.ask(AskRequest(question="q", video_id="dQw4w9WgXcQ", provider=provider))


# ── 供應商層：截斷與正常完成 ─────────────────────────────────

def test_truncated_reply_raises_once_with_partial_and_public_message():
    for provider in PROVIDERS:
        with _Upstream(provider, PARTIAL) as upstream:
            try:
                llm_router.generate(provider, "x", "y")
                assert False, f"{provider}：截斷不可以當成完整內容"
            except TruncatedOutputError as err:
                assert err.partial == PARTIAL, provider
                assert err.label and err.public_message == str(err), provider
                assert SECRET not in user_error(err, provider), provider
            if provider != OLLAMA:
                assert upstream.calls == 1, f"{provider}：重試同一份請求沒有意義"


def test_complete_reply_is_returned_untouched():
    for provider in PROVIDERS:
        with _Upstream(provider, "完整回答", truncated=False):
            text, label = llm_router.generate(provider, "x", "y")
        assert text == "完整回答" and label, provider


def test_anthropic_context_window_stop_counts_as_truncated():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response(
        PARTIAL, "model_context_window_exceeded")
    with patch.object(anthropic_api, "_client", return_value=client):
        try:
            anthropic_api.generate("x", model="claude-x")
            assert False, "塞滿 context window 也是截斷"
        except TruncatedOutputError as err:
            assert err.partial == PARTIAL and err.label == "Claude/claude-x"


def test_empty_truncated_reply_is_not_a_blank_partial():
    """一個字都沒有時沒有內容可留，不該走部分內容的路徑，顯示一則空白回答。"""
    cases = ((ANTHROPIC, EmptyResponseError, "stop_reason=max_tokens"),
             (GEMINI, EmptyResponseError, "finishReason=MAX_TOKENS"),
             (OLLAMA, ProviderError, "上限"))
    for provider, expected, hint in cases:
        with _Upstream(provider, ""), patch("time.sleep"):
            try:
                llm_router.generate(provider, "x", "y")
                assert False, provider
            except TruncatedOutputError:
                assert False, f"{provider}：空內容不該當部分內容"
            except expected as err:
                assert hint in user_error(err, provider), provider


def test_gemini_does_not_rotate_keys_on_truncation():
    with _Upstream(GEMINI, PARTIAL, keys=3) as upstream:
        try:
            gemini.generate("x", model="gemini-x")
            assert False
        except TruncatedOutputError as err:
            assert err.label == "gemini-x"
    assert upstream.calls == 1, "換金鑰也一樣會被截斷，不該再花額度"


def test_gemini_chat_does_not_fall_back_to_plain_chat():
    with _Upstream(GEMINI, PARTIAL) as upstream:
        try:
            gemini.generate_chat([{"role": "user", "content": "q"}], model="gemini-x")
            assert False
        except TruncatedOutputError as err:
            assert err.label != "gemini-x" and err.label.startswith("gemini-x"), "要標示有用搜尋"
    assert upstream.calls == 1, "截斷不是搜尋工具的問題，不該退回純對話再打一次"


def test_gemini_video_still_returns_partial_for_deepsrt_resume():
    """DeepSRT 靠輸出內容判斷中斷並從斷點補跑，這條路不可以改成拋例外。"""
    with _Upstream(GEMINI, "###TRANSCRIPT###\n[0] 一半"):
        assert "一半" in gemini.generate_video("https://youtu.be/dQw4w9WgXcQ", "轉錄")


def test_auto_mode_does_not_move_to_another_paid_provider():
    with _Upstream(GEMINI, PARTIAL), \
         patch.object(llm_router.opencode, "generate_free", side_effect=ProviderError("免費模型都失敗")), \
         patch.object(anthropic_api, "is_configured", return_value=True), \
         patch.object(openai_compat, "is_configured", return_value=True), \
         patch.object(openai_compat, "generate") as other, \
         patch.object(anthropic_api, "generate") as claude:
        try:
            llm_router.generate("auto", "x", "y")
            assert False
        except TruncatedOutputError as err:
            assert err.partial == PARTIAL
    other.assert_not_called()
    claude.assert_not_called()


# ── 呼叫端：摘要、問答、深入解析、翻譯、實作 ─────────────────

def test_summary_keeps_cards_and_marks_truncated():
    for provider in PROVIDERS:
        with _Upstream(provider, PARTIAL_CARDS):
            data, label = summary_api._run_segment(
                SummarizeRequest(url="https://example.com", provider=provider),
                {"type": "article", "text": "內容"}, "內容", 0, False)
        assert data["truncated"] is True, provider
        assert data["cards"][0]["heading"] == "h" and label, provider


def test_summary_complete_reply_is_not_marked_truncated():
    complete = json.dumps({"title": "t", "cards": [{"heading": "h", "summary": "s"}]},
                          ensure_ascii=False)
    for provider in PROVIDERS:
        with _Upstream(provider, complete, truncated=False):
            data, _ = summary_api._run_segment(
                SummarizeRequest(url="https://example.com", provider=provider),
                {"type": "article", "text": "內容"}, "內容", 0, False)
        assert "truncated" not in data, provider


def test_ask_shows_partial_with_notice():
    for provider in PROVIDERS:
        with _Upstream(provider, "只寫到一半"):
            result = _ask(provider)
        assert result["answer"].startswith("只寫到一半"), provider
        assert "截斷" in result["answer"] and result["model_used"], provider


def test_ask_gemini_truncation_is_not_an_error_and_keeps_search_flag():
    with _Upstream(GEMINI, "只寫到一半"):
        result = _ask(GEMINI)
    assert result["searched"] is True


def test_ask_auto_gemini_truncation_does_not_move_to_other_providers():
    with _Upstream(GEMINI, "只寫到一半") as upstream, \
         patch.object(ask_api, "_answer_with") as other, \
         patch.object(ask_api.opencode, "generate_free") as free:
        result = _ask("auto")
    assert result["answer"].startswith("只寫到一半") and upstream.calls == 1
    other.assert_not_called()
    free.assert_not_called()


def test_ask_complete_reply_has_no_notice():
    for provider in PROVIDERS:
        with _Upstream(provider, "完整回答", truncated=False):
            result = _ask(provider)
        assert result["answer"] == "完整回答", provider


def test_deepdive_shows_partial_with_notice():
    for provider in PROVIDERS:
        with _Upstream(provider, "只寫到一半"):
            deep = summary_api.deepdive(DeepDiveRequest(
                provider=provider, source_title="t", card={"heading": "h", "summary": "s"}))
        assert deep["content"].startswith("只寫到一半") and "截斷" in deep["content"], provider


def test_translation_fails_without_caching_or_leaking_upstream_text():
    reply = '{"translations":[{"id":0,"text":"' + SECRET + '"}]}'
    source = {"cues": [{"text": "hello"}]}
    for provider in PROVIDERS:
        with _Upstream(provider, reply), \
             patch.object(subtitles_api, "get_subtitles", return_value=source), \
             patch.object(translation_cache, "get", return_value=None), \
             patch.object(translation_cache, "put") as put:
            try:
                subtitles_api.translate_subtitles(subtitles_api.TranslateRequest(
                    platform="youtube", video_id="dQw4w9WgXcQ", translation_provider=provider))
                assert False, f"{provider}：截斷的翻譯不可以成功"
            except HTTPException as err:
                assert err.status_code == 502, provider
                assert "上限" in err.detail and SECRET not in err.detail, provider
        put.assert_not_called()


def test_translation_complete_reply_is_cached():
    reply = '{"translations":[{"id":0,"text":"你好"}]}'
    for provider in PROVIDERS:
        with _Upstream(provider, reply, truncated=False), \
             patch.object(translation_cache, "get", return_value=None), \
             patch.object(translation_cache, "put") as put:
            rows, _ = subtitle_translation.translate_batch(
                [{"id": 0, "text": "hello"}], provider=provider)
        assert rows == [{"id": 0, "translation": "你好"}], provider
        put.assert_called_once()


async def _implement_events(response):
    items = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        items.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return items


def test_implement_fails_and_does_not_write_finished_files():
    partial = f"{FILE_BEGIN}a.html>>>\n<h1>{SECRET}"
    with _Upstream(GEMINI, partial), \
         patch.object(agent_cli, "detect", return_value=[]), \
         patch.object(impl.gemini, "key_count", return_value=1):
        events = asyncio.run(_implement_events(impl.implement(ImplementRequest(
            video_title="截斷偵測測試", cli="gemini",
            cards=[Card(heading="卡", summary="內容")]))))
    fatal = events[-1]
    assert fatal["type"] == "fatal" and "上限" in fatal["error"]
    assert SECRET not in fatal["error"]
    workdir = Path(fatal["workdir"])
    try:
        assert not (workdir / "a.html").exists(), "半份檔案不能當成成品落檔"
        assert (workdir / "api-raw.txt").read_text(encoding="utf-8") == partial
    finally:
        for item in workdir.iterdir():
            item.unlink()
        workdir.rmdir()


if __name__ == "__main__":
    test_truncated_reply_raises_once_with_partial_and_public_message()
    test_complete_reply_is_returned_untouched()
    test_anthropic_context_window_stop_counts_as_truncated()
    test_empty_truncated_reply_is_not_a_blank_partial()
    test_gemini_does_not_rotate_keys_on_truncation()
    test_gemini_chat_does_not_fall_back_to_plain_chat()
    test_gemini_video_still_returns_partial_for_deepsrt_resume()
    test_auto_mode_does_not_move_to_another_paid_provider()
    test_summary_keeps_cards_and_marks_truncated()
    test_summary_complete_reply_is_not_marked_truncated()
    test_ask_shows_partial_with_notice()
    test_ask_gemini_truncation_is_not_an_error_and_keeps_search_flag()
    test_ask_auto_gemini_truncation_does_not_move_to_other_providers()
    test_ask_complete_reply_has_no_notice()
    test_deepdive_shows_partial_with_notice()
    test_translation_fails_without_caching_or_leaking_upstream_text()
    test_translation_complete_reply_is_cached()
    test_implement_fails_and_does_not_write_finished_files()
    print("test_truncated_output: all passed")
