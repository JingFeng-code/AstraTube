"""免費模型接力測試：單一免費模型下架時要換下一個，且一般模式絕不改用付費供應商（不呼叫真實 API）。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.api import ask as ask_api  # noqa: E402
from app.llm import opencode, router  # noqa: E402
from app.llm.base import ProviderError  # noqa: E402
from app.models.schemas import AskRequest  # noqa: E402

UNAVAILABLE = '{"error":{"type":"server_error","message":"Upstream request failed: Model is unavailable."}}'


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _reset():
    opencode._unavailable.clear()
    opencode._models_cache = None


def _live(models):
    return patch.object(opencode, "list_free_models", return_value=(list(models), "live"))


def _fake_post(down: set[str], calls: list[str]):
    """down 內的模型回 HTTP 400「Model is unavailable」，其餘正常回答。"""
    def post(url, headers=None, json=None, timeout=None):
        model = json["model"]
        calls.append(model)
        if model in down:
            return FakeResponse(400, text=UNAVAILABLE)
        return FakeResponse(payload={"choices": [{"message": {"content": f"來自 {model}"}}]})
    return post


def test_only_model_unavailable_errors_skip_retries():
    assert opencode._says_model_unavailable(UNAVAILABLE)
    assert opencode._says_model_unavailable('{"error":"model not found"}')
    # 內容太長等請求錯誤不算模型下架，不該把模型排到最後
    assert not opencode._says_model_unavailable('{"error":"maximum context length for this model exceeded"}')


def test_chain_follows_live_list_and_keeps_preferred_order():
    _reset()
    # 預設模型已不在上架清單：接力從下一個偏好模型開始，其他上架的免費模型接在後面
    with _live(["big-pickle", "mimo-v2.5-free", "north-mini-code-free", "longcat-2.0-free", "new-model-free"]):
        assert opencode.free_chain() == ["longcat-2.0-free", "mimo-v2.5-free",
                                         "big-pickle", "new-model-free"]
    # 抓不到上架清單時用內建偏好順序
    with patch.object(opencode, "list_free_models", return_value=(["x"], "static")):
        assert opencode.free_chain() == list(opencode.AUTO_CHAIN)


def test_unavailable_model_is_skipped_and_moved_last():
    _reset()
    calls: list[str] = []
    chain = ["deepseek-v4-flash-free", "longcat-2.0-free"]
    with _live(chain), \
         patch.object(opencode.httpx, "post", side_effect=_fake_post({"deepseek-v4-flash-free"}, calls)):
        text, model = opencode.generate_free([{"role": "user", "content": "hi"}])
        assert (text, model) == ("來自 longcat-2.0-free", "longcat-2.0-free")
        assert calls == chain, "400 模型不可用不重試，直接換下一個"
        # 下一次請求先試可用的模型，不再每段都先撞已下架的模型
        assert opencode.free_chain() == ["longcat-2.0-free", "deepseek-v4-flash-free"]


def test_all_free_models_failing_lists_them_without_leaking_upstream_body():
    _reset()
    chain = ["deepseek-v4-flash-free", "longcat-2.0-free"]
    with _live(chain), patch.object(opencode.httpx, "post", side_effect=_fake_post(set(chain), [])):
        try:
            opencode.generate_free([{"role": "user", "content": "hi"}])
            raise AssertionError("Expected ProviderError")
        except ProviderError as exc:
            assert "deepseek-v4-flash-free" in str(exc) and "longcat-2.0-free" in str(exc)
            assert "HTTP 400" in str(exc)
            assert "HTTP 400" in exc.public_message
            assert "Upstream request failed" not in exc.public_message


def test_free_provider_never_uses_paid_fallback():
    _reset()
    assert router.parse("free")[0] == router.FREE
    paid_calls = []
    with _live(["deepseek-v4-flash-free"]), \
         patch.object(opencode.httpx, "post", side_effect=_fake_post({"deepseek-v4-flash-free"}, [])), \
         patch.object(router, "configured_paid_chain", return_value=[(router.DEEPSEEK, "deepseek-chat")]), \
         patch.object(router, "_call", side_effect=lambda *a, **k: paid_calls.append(a) or ("付費", "paid")):
        try:
            router.generate("free", "摘要")
            raise AssertionError("Expected ProviderError")
        except ProviderError:
            pass
        assert paid_calls == [], "一般模式不可改用開發者的付費金鑰"
        # 對照：auto（開發者模式）才會在免費模型全滅後備援到已設定金鑰的供應商
        assert router.generate("auto", "摘要") == ("付費", "paid")
        assert len(paid_calls) == 1


def test_ask_free_provider_relays_free_models_only():
    _reset()
    calls: list[str] = []
    with _live(["deepseek-v4-flash-free", "mimo-v2.5-free"]), \
         patch.object(ask_api, "_load_transcript", return_value="逐字稿"), \
         patch.object(ask_api.gemini, "key_count", return_value=1), \
         patch.object(ask_api.gemini, "generate_chat") as gemini_chat, \
         patch.object(ask_api.llm_router, "configured_paid_chain",
                      return_value=[(router.DEEPSEEK, "deepseek-chat")]), \
         patch.object(ask_api, "_answer_with") as paid, \
         patch.object(opencode.httpx, "post", side_effect=_fake_post({"deepseek-v4-flash-free"}, calls)):
        result = ask_api.ask(AskRequest(question="重點？", video_id="M7lc1UVf-VE", provider="free"))
    assert result["model_used"] == "mimo-v2.5-free"
    gemini_chat.assert_not_called()
    paid.assert_not_called()
    assert calls == ["deepseek-v4-flash-free", "mimo-v2.5-free"]


def test_ask_free_provider_reports_failure():
    _reset()
    with _live(["deepseek-v4-flash-free"]), \
         patch.object(ask_api, "_load_transcript", return_value="逐字稿"), \
         patch.object(opencode.httpx, "post", side_effect=_fake_post({"deepseek-v4-flash-free"}, [])):
        try:
            ask_api.ask(AskRequest(question="重點？", video_id="M7lc1UVf-VE", provider="free"))
            raise AssertionError("Expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 500
            assert "deepseek-v4-flash-free" in exc.detail


if __name__ == "__main__":
    test_only_model_unavailable_errors_skip_retries()
    test_chain_follows_live_list_and_keeps_preferred_order()
    test_unavailable_model_is_skipped_and_moved_last()
    test_all_free_models_failing_lists_them_without_leaking_upstream_body()
    test_free_provider_never_uses_paid_fallback()
    test_ask_free_provider_relays_free_models_only()
    test_ask_free_provider_reports_failure()
    print("Free-model relay tests passed.")
