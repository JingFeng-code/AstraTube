"""AI 設定流程：不連外、不回傳金鑰、不假裝靜態清單已通過驗證。"""
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import provider_connection as pc
from app.llm import router as llm_router
from app.transcript import subtitle_translation


def test_provider_check_uses_supplied_key_without_persisting():
    with patch.object(pc, "_http_models", return_value=["gpt-test-chat"]) as fetch, \
         patch.object(pc.config, "get", return_value="old-secret") as get:
        result = pc.check_provider(pc.CheckProviderRequest(provider="openai", api_key="new-secret"))
    assert result == {"provider": "openai", "connected": True,
                      "models": ["gpt-test-chat"], "source": "live"}
    fetch.assert_called_once_with("openai", "new-secret")
    get.assert_not_called()


def test_existing_key_can_be_verified_without_exposing_it():
    with patch.object(pc, "_http_models", return_value=["deepseek-chat"]) as fetch, \
         patch.object(pc.config, "get", return_value="stored-secret"):
        result = pc.check_provider(pc.CheckProviderRequest(provider="deepseek"))
    fetch.assert_called_once_with("deepseek", "stored-secret")
    assert "secret" not in str(result)


def test_wrong_key_and_missing_key_do_not_return_static_models():
    with patch.object(pc.config, "get", return_value=""):
        try:
            pc.check_provider(pc.CheckProviderRequest(provider="openai"))
            assert False, "沒有金鑰必須回報失敗"
        except HTTPException as exc:
            assert exc.status_code == 400
    response = httpx.Response(401, json={"error": "sensitive vendor error"})
    with patch.object(pc.httpx, "Client") as client:
        client.return_value.__enter__.return_value.get.return_value = response
        try:
            pc.check_provider(pc.CheckProviderRequest(provider="openai", api_key="invalid"))
            assert False, "錯誤金鑰不得成功"
        except HTTPException as exc:
            assert exc.status_code == 401
            assert "sensitive" not in str(exc.detail)


def test_ollama_only_returns_installed_models():
    with patch.object(pc.ollama, "connection_status", return_value={
            "connected": True, "models": ["qwen3:4b"], "message": "已連接"}):
        result = pc.check_provider(pc.CheckProviderRequest(provider="ollama"))
    assert result["models"] == ["qwen3:4b"]
    with patch.object(pc.ollama, "connection_status", return_value={
            "connected": False, "models": [], "message": "無法連線"}):
        try:
            pc.check_provider(pc.CheckProviderRequest(provider="ollama"))
            assert False
        except HTTPException as exc:
            assert exc.status_code == 503


def test_gemini_selected_model_reaches_router_and_translation():
    assert llm_router.parse("gemini:gemini-3.5-flash") == ("gemini", "gemini-3.5-flash")
    assert subtitle_translation.resolve_provider("gemini:gemini-3.5-flash") == (
        "gemini", "gemini-3.5-flash", "gemini:gemini-3.5-flash")
    with patch.object(llm_router.gemini, "generate", return_value=("ok", "Gemini/test")) as generate:
        llm_router.generate("gemini:gemini-3.5-flash", "prompt")
    assert generate.call_args.kwargs["model"] == "gemini-3.5-flash"



def test_ask_uses_selected_gemini_model_but_preserves_legacy_auto():
    from app.api import ask as ask_api
    from app.llm import gemini
    from app.models.schemas import AskRequest

    with patch.object(ask_api, "_load_transcript", return_value="[0] sample"), \
         patch.object(gemini, "key_count", return_value=1), \
         patch.object(gemini, "generate_chat", return_value=("ok", gemini.MODEL)) as mocked:
        ask_api.ask(AskRequest(question="What?", video_id="dQw4w9WgXcQ", provider=None))
        assert mocked.call_args.kwargs["model"] == gemini.MODEL
        ask_api.ask(AskRequest(question="What?", video_id="dQw4w9WgXcQ",
                                provider="gemini:gemini-custom"))
        assert mocked.call_args.kwargs["model"] == "gemini-custom"



def test_new_cloud_providers_support_verification_generation_and_subtitles():
    from app.llm import openai_compat
    names = ("openrouter", "groq", "mistral", "together")
    for provider in names:
        assert provider in openai_compat.VENDORS
        vendor = openai_compat.VENDORS[provider]
        assert vendor.base_url.startswith("https://")
        assert llm_router.parse(f"{provider}:vendor/model:free") == (
            provider, "vendor/model:free")
        assert subtitle_translation.resolve_provider(f"{provider}:vendor/model:free") == (
            provider, "vendor/model:free", f"{provider}:vendor/model:free")
        with patch.object(pc, "_http_models", return_value=["vendor/model:free"]) as mocked:
            response = pc.check_provider(pc.CheckProviderRequest(provider=provider, api_key="test-key"))
            assert response["models"] == ["vendor/model:free"]
            mocked.assert_called_once_with(provider, "test-key")
        with patch.object(openai_compat, "generate", return_value=("ok", "model")) as generate:
            llm_router.generate(f"{provider}:vendor/model:free", "hello")
            assert generate.call_args.args[0].key == provider
            assert generate.call_args.kwargs["model"] == "vendor/model:free"


def test_openrouter_verifies_key_before_public_model_list():
    # /models 為公開 API，不能只看它的 HTTP 200 就將錯誤金鑰標成已連線。
    key_bad = httpx.Response(401, json={"error": "invalid"})
    models_ok = httpx.Response(200, json={"data": [{"id": "openai/model"}]})
    with patch.object(pc.httpx, "Client") as mock_client:
        get = mock_client.return_value.__enter__.return_value.get
        get.side_effect = [key_bad, models_ok]
        try:
            pc._http_models("openrouter", "invalid")
            assert False, "OpenRouter 401 must stop before listing models"
        except HTTPException as exc:
            assert exc.status_code == 401
        assert get.call_count == 1

    with patch.object(pc.httpx, "Client") as mock_client:
        get = mock_client.return_value.__enter__.return_value.get
        get.side_effect = [httpx.Response(200, json={"data": {}}), models_ok]
        names = pc._http_models("openrouter", "valid")
        assert names == ["openai/model"]
        assert "/key" in get.call_args_list[0].args[0]
        assert "/models" in get.call_args_list[1].args[0]


def test_model_list_filters_non_chat_entries_and_no_free_provider_advertised():
    assert pc._models_from_rows([
        {"id": "whisper-large-v3"}, {"id": "llama-guard-3"}, {"id": "llama-3-instruct"},
    ], provider="groq") == ["llama-3-instruct"]
    assert pc._models_from_rows([
        {"id": "mistral-embed", "capabilities": {"completion_chat": False}},
        {"id": "mistral-chat", "capabilities": {"completion_chat": True}},
        {"id": "mistral-no-capabilities", "capabilities": None},
    ], provider="mistral") == ["mistral-chat", "mistral-no-capabilities"]
    from app.api import models as model_api
    with patch.object(model_api.ollama, "connection_status", return_value={
            "connected": False, "models": []}), patch.object(
            model_api.gemini, "key_count", return_value=0):
        response = model_api.list_models()
    assert "opencode" not in response["providers"]
    for name in ("openrouter", "groq", "mistral", "together"):
        assert response["providers"][name]["models"] == []


if __name__ == "__main__":
    test_provider_check_uses_supplied_key_without_persisting()
    test_existing_key_can_be_verified_without_exposing_it()
    test_wrong_key_and_missing_key_do_not_return_static_models()
    test_ollama_only_returns_installed_models()
    test_gemini_selected_model_reaches_router_and_translation()
    test_ask_uses_selected_gemini_model_but_preserves_legacy_auto()
    test_new_cloud_providers_support_verification_generation_and_subtitles()
    test_openrouter_verifies_key_before_public_model_list()
    test_model_list_filters_non_chat_entries_and_no_free_provider_advertised()
    print("AI provider connection tests passed")
