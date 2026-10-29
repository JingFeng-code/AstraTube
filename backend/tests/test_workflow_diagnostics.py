"""字幕 → AI 摘要 → 知識卡 → 問答 工作流程的錯誤診斷回歸測試（全部使用 Mock，不連外部服務）。

涵蓋 Windows 實測（Issue #19）的「第 1 段生成失敗，已跳過」：
- 供應商錯誤處理不得因變數遮蔽 app.core.messages 而再拋 AttributeError
- HTTP 401／403／404／429／5xx、逾時、連線失敗、非 JSON、空回應、格式錯誤都要顯示真正原因與下一步
- 模型回應不是卡片 JSON 時要明確說明，不能讓前端只看到看不懂的錯誤
- 匯入 SRT 後能完整走完摘要與問答
"""
import ast
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import summarize as summarize_api  # noqa: E402
from app.llm import gemini, openai_compat, opencode  # noqa: E402
from app.llm.base import EmptyResponseError, ProviderError  # noqa: E402
from app.llm.util import is_transient  # noqa: E402
from app.main import app  # noqa: E402
from app.transcript import cache, imported_subtitles  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[1] / "app"
VIDEO_URL = "https://www.youtube.com/watch?v=Y5UobXTOZEY"
SRT = "\n\n".join(
    f"{i}\n00:00:{i * 4:02d},000 --> 00:00:{i * 4 + 3:02d},500\n第 {i} 句：介紹 Python 的 list comprehension。"
    for i in range(1, 13))
GOOD_CARDS = {"title": "Python 列表推導式", "content_type": "tutorial", "cards": [
    {"heading": "語法", "summary": "用一行建立清單", "timestamp_seconds": 4},
    {"heading": "條件", "summary": "可加 if 過濾", "timestamp_seconds": 24}]}


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text if text else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def chat_payload(content):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


def client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8420")


# ── 1. 變數遮蔽 ─────────────────────────────────────────────

def test_no_function_shadows_the_messages_module():
    """凡是使用 messages.t(...) 的函式，都不得有名為 messages 的參數或區域變數。"""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = any(isinstance(node, ast.ImportFrom) and any(a.name == "messages" for a in node.names)
                      for node in ast.walk(tree))
        if not imports:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
            names |= {t.id for n in ast.walk(fn) if isinstance(n, ast.Assign)
                      for t in n.targets if isinstance(t, ast.Name)}
            uses_t = any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                         and n.value.id == "messages" and n.attr == "t" for n in ast.walk(fn))
            if "messages" in names and uses_t:
                offenders.append(f"{path.relative_to(APP_DIR)}:{fn.lineno} {fn.name}")
    assert not offenders, offenders


# ── 2. OpenAI 相容供應商（OpenCode／DeepSeek／OpenAI）的錯誤矩陣 ─────────

def _error_from(call, response=None, side_effect=None):
    kwargs = {"side_effect": side_effect} if side_effect is not None else {"return_value": response}
    with patch.object(httpx, "post", **kwargs):
        try:
            call()
        except (ProviderError, EmptyResponseError) as exc:
            return exc
    raise AssertionError("expected a provider error")


def _callers():
    yield "OpenCode", lambda: opencode._post_chat("deepseek-v4-flash-free", [{"role": "user", "content": "hi"}])
    vendor = openai_compat.DEEPSEEK

    def deepseek():
        # 不設定真實金鑰、不連線：只測錯誤處理
        with patch.object(openai_compat, "_headers", return_value={"Authorization": "Bearer test"}):
            return openai_compat._post_chat(vendor, "deepseek-chat", [{"role": "user", "content": "hi"}])
    yield vendor.label, deepseek


def test_http_status_matrix_shows_cause_and_next_step():
    cases = {
        401: ("HTTP 401", "API Key", False),
        403: ("HTTP 403", "API Key", False),
        404: ("HTTP 404", "下架", False),
        429: ("HTTP 429", "上限", True),
        500: ("HTTP 500", "暫時故障", True),
        503: ("HTTP 503", "暫時故障", True),
    }
    for vendor, call in _callers():
        for status, (code_text, hint, transient) in cases.items():
            exc = _error_from(call, FakeResponse(status, text='{"error":"denied"}'))
            message = str(exc)
            assert vendor in message and code_text in message and hint in message, message
            assert "has no attribute" not in message
            assert is_transient(exc) is transient, (status, message)


def test_html_error_pages_are_cleaned():
    page = "<html><head><title>Attention Required! | Cloudflare</title></head><body>blocked</body></html>"
    for _, call in _callers():
        message = str(_error_from(call, FakeResponse(403, text=page)))
        assert "<html" not in message and "Cloudflare" in message, message


def test_timeout_and_network_failures():
    for _, call in _callers():
        timeout = _error_from(call, side_effect=httpx.ReadTimeout("read timed out"))
        assert "逾時" in str(timeout) and "read timed out" in str(timeout)
        down = _error_from(call, side_effect=httpx.ConnectError("Name or service not known"))
        assert "網路" in str(down) and "Name or service not known" in str(down)


def test_invalid_json_empty_and_malformed_responses():
    for _, call in _callers():
        assert "JSON" in str(_error_from(call, FakeResponse(200, payload=ValueError("bad"), text="<oops>")))
        assert isinstance(_error_from(call, FakeResponse(200, payload=chat_payload(""))), EmptyResponseError)
        assert isinstance(_error_from(call, FakeResponse(200, payload={"choices": []})), EmptyResponseError)
        assert "overloaded" in str(_error_from(call, FakeResponse(200, payload={"error": {"message": "overloaded"}})))


def test_anthropic_errors_no_longer_masked():
    import anthropic
    from app.llm import anthropic_api

    class FakeClient:
        class messages:  # noqa: N801  模擬 SDK 介面
            @staticmethod
            def create(**_kw):
                raise anthropic.APIConnectionError(request=None)

    with patch.object(anthropic_api, "_client", return_value=FakeClient()):
        try:
            anthropic_api._once("claude-test", [{"role": "user", "content": "hi"}], "")
        except ProviderError as exc:
            assert "has no attribute" not in str(exc)
        else:
            raise AssertionError("expected ProviderError")


def test_gemini_search_answer_keeps_label_and_single_call():
    calls = []

    def fake_over_keys(run, **_kw):
        calls.append(1)
        return "答案"

    with patch.object(gemini, "_over_keys", side_effect=fake_over_keys), \
         patch.object(gemini, "_search_down_until", 0):
        text, label = gemini.generate_chat([{"role": "user", "content": "q"}], "sys")
    assert text == "答案" and label != gemini.LABEL
    assert len(calls) == 1, "搜尋成功時不得因標籤組字失敗而再呼叫一次純對話"


# ── 3. 模型輸出解析 ──────────────────────────────────────────

def test_parse_cards_accepts_common_wrappers_and_rejects_non_cards():
    good = json.dumps(GOOD_CARDS, ensure_ascii=False)
    for raw in (good, f"```json\n{good}\n```", f"以下是卡片：\n```json\n{good}\n```",
                f"<think>先讀素材</think>\n{good}", json.dumps(GOOD_CARDS["cards"], ensure_ascii=False)):
        assert len(summarize_api._parse_cards(raw, "zh-Hant")["cards"]) == 2, raw[:40]
    for raw in ("", "我需要先分析素材，然後輸出 JSON。", '{"title": "只有標題"}', '"字串"'):
        try:
            summarize_api._parse_cards(raw, "zh-Hant")
        except ValueError as exc:
            assert "知識卡格式" in str(exc)
        else:
            raise AssertionError(f"should reject: {raw!r}")


# ── 4. 匯入 SRT → 摘要 → 知識卡 → 問答（端到端，Mock 供應商） ───────────

def _with_isolated_storage():
    imported_dir = Path(tempfile.mkdtemp())
    cache_dir = Path(tempfile.mkdtemp())
    return patch.object(imported_subtitles, "CACHE_DIR", imported_dir), patch.object(cache, "CACHE_DIR", cache_dir)


def _stream(c, provider="opencode:deepseek-v4-flash-free"):
    response = c.post("/summarize_stream", json={"url": VIDEO_URL, "provider": provider})
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_imported_srt_to_cards_and_answer():
    p1, p2 = _with_isolated_storage()
    with p1, p2, patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": ""}):
        c = client()
        r = c.post("/subtitles/imported", json={"video_url": VIDEO_URL, "filename": "t.srt", "content": SRT})
        assert r.status_code == 200 and r.json()["cue_count"] == 12

        prompts = []

        def fake_post(url, json=None, **_kw):
            prompts.append(json["messages"][-1]["content"])
            if len(prompts) == 1:
                return FakeResponse(200, payload=chat_payload(globals()["json"].dumps(GOOD_CARDS, ensure_ascii=False)))
            return FakeResponse(200, payload=chat_payload("這支影片在講 list comprehension。"))

        with patch.object(httpx, "post", side_effect=fake_post):
            events = _stream(c)
            cards = [e for e in events if e["type"] == "cards"]
            assert cards and len(cards[0]["cards"]) == 2, events
            assert not [e for e in events if e["type"] in ("seg_error", "fatal")], events
            meta = next(e for e in events if e["type"] == "meta")
            assert meta["transcript_source"] == "imported_subtitles" and meta["youtube_video_id"] == "Y5UobXTOZEY"
            assert "list comprehension" in prompts[0], "摘要必須使用匯入的字幕內容"

            answer = c.post("/ask", json={"question": "重點是什麼？", "video_id": "Y5UobXTOZEY",
                                          "provider": "opencode:deepseek-v4-flash-free"})
            assert answer.status_code == 200, answer.text
            assert "list comprehension" in answer.json()["answer"]
            assert "第 1 句" in prompts[1] or "第 1 句" in "".join(prompts), "問答必須以匯入字幕為背景"


def test_provider_failure_reaches_the_user_with_reason():
    p1, p2 = _with_isolated_storage()
    with p1, p2, patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": ""}), patch("app.llm.util.time.sleep"):
        c = client()
        c.post("/subtitles/imported", json={"video_url": VIDEO_URL, "filename": "t.srt", "content": SRT})
        with patch.object(httpx, "post", return_value=FakeResponse(429, text='{"error":"rate limited"}')):
            events = _stream(c)
            errors = [e["error"] for e in events if e["type"] == "seg_error"]
            assert errors and "HTTP 429" in errors[0] and "上限" in errors[0], events
            answer = c.post("/ask", json={"question": "q", "video_id": "Y5UobXTOZEY",
                                          "provider": "opencode:deepseek-v4-flash-free"})
            assert answer.status_code == 500 and "HTTP 429" in answer.json()["detail"], answer.text
        with patch.object(httpx, "post", return_value=FakeResponse(200, payload=chat_payload("我先想一想……"))):
            errors = [e["error"] for e in _stream(c) if e["type"] == "seg_error"]
            assert errors and "知識卡格式" in errors[0], errors


def test_ask_without_transcript_returns_clear_400():
    p1, p2 = _with_isolated_storage()
    with p1, p2, patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": ""}), \
         patch("app.api.ask.captions.fetch_transcript", side_effect=ValueError("none")):
        response = client().post("/ask", json={"question": "q", "video_id": "AAAAAAAAAAA",
                                               "provider": "opencode:deepseek-v4-flash-free"})
    assert response.status_code == 400, response.text
    assert "逐字稿" in response.json()["detail"]


if __name__ == "__main__":
    test_no_function_shadows_the_messages_module()
    test_http_status_matrix_shows_cause_and_next_step()
    test_html_error_pages_are_cleaned()
    test_timeout_and_network_failures()
    test_invalid_json_empty_and_malformed_responses()
    test_anthropic_errors_no_longer_masked()
    test_gemini_search_answer_keeps_label_and_single_call()
    test_parse_cards_accepts_common_wrappers_and_rejects_non_cards()
    test_imported_srt_to_cards_and_answer()
    test_provider_failure_reaches_the_user_with_reason()
    test_ask_without_transcript_returns_clear_400()
    print("Workflow diagnostics tests passed")
