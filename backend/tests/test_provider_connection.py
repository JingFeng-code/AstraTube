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


if __name__ == "__main__":
    test_provider_check_uses_supplied_key_without_persisting()
    test_existing_key_can_be_verified_without_exposing_it()
    test_wrong_key_and_missing_key_do_not_return_static_models()
    test_ollama_only_returns_installed_models()
    test_gemini_selected_model_reaches_router_and_translation()
    print("AI provider connection tests passed")
