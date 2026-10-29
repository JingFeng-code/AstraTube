"""Ollama 模型路由與回環連線安全測試：所有 HTTP 回應皆 mock。"""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import ollama, router as llm_router
from app.llm.base import ProviderError
from app.core import config


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=httpx.Request("GET","http://127.0.0.1:11434/api/tags"),
                                       response=httpx.Response(self.status_code))
    def json(self):
        return self.data


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def get(self, url):
        self.calls.append(("get",url))
        return FakeResponse(self.reply)
    def post(self, url, json):
        self.calls.append(("post",url,json))
        return FakeResponse(self.reply)


def test_only_loopback_hosts():
    for host in ("http://127.0.0.1:11434","http://localhost:11434/"):
        assert ollama.validate_base_url(host).startswith("http:")
    try:
        ollama.validate_model("gpt-oss:120b-cloud")
        assert False, "cloud model should not be eligible for local-only mode"
    except ValueError:
        pass
    for bad in ("http://10.0.0.1:11434","http://127.0.0.1:8000",
                "http://127.0.0.1:11434@evil.com:11434",
                "https://localhost:11434",
                "http://localhost:11434/internal",
                "http://localhost:11434/?x=1",
                "http://localhost:11434#fragment",
                "http://localhost:11434.evil.com:11434"):
        try:
            ollama.validate_base_url(bad)
            assert False, f"Unexpected accepted URL: {bad}"
        except ValueError:
            pass


def test_models_only_reflect_installed():
    fake=FakeClient({"models":[{"name":"qwen3:4b"},{"name":"gemma3:4b"},{"name":"qwen3:4b"}]})
    with patch.object(ollama.httpx,"Client",return_value=fake):
        assert ollama.list_models()==["qwen3:4b","gemma3:4b"]
    assert fake.calls[0][1].endswith("/api/tags")


def test_provider_routing_and_no_paid_fallback():
    assert llm_router.parse("ollama:qwen3:4b")==("ollama","qwen3:4b")
    assert llm_router.parallel_workers("ollama:qwen3:4b",10)==1
    fake=FakeClient({"message":{"role":"assistant","content":"台灣繁體中文"}})
    with patch.object(ollama.httpx,"Client",return_value=fake):
        result=llm_router.generate("ollama:qwen3:4b","影片重點","用繁體中文回答")
    assert result==("台灣繁體中文","Ollama/qwen3:4b")
    method,url,payload=fake.calls[0]
    assert method=="post" and url.endswith("/api/chat")
    assert payload["stream"] is False
    assert payload["model"]=="qwen3:4b"
    assert payload["messages"][0]["role"]=="system"


def test_configured_model_and_missing_model_error():
    original=config.all_settings()
    try:
        config._cache["OLLAMA_MODEL"]="gemma3:4b"
        assert llm_router.parse("ollama:")==("ollama","gemma3:4b")
        with patch.object(ollama, "list_models", return_value=[]):
            config._cache["OLLAMA_MODEL"]=""
            try:
                ollama.generate("test")
                assert False
            except ProviderError as exc:
                assert "沒有" in str(exc) or "尚無" in str(exc)
    finally:
        config._cache.update(original)


def test_ask_uses_ollama_not_opencode():
    from app.api import ask as ask_api
    with patch.object(ask_api, "_load_transcript",return_value="[0] Hello"), \
         patch.object(ollama, "generate_messages", return_value=("你好","Ollama/qwen3:4b")) as ollama_chat, \
         patch.object(ask_api.opencode, "generate_messages") as cloud:
        result=ask_api.ask(ask_api.AskRequest(
            question="說明",video_id="M7lc1UVf-VE",provider="ollama:qwen3:4b"
        ))
    assert result["answer"]
    ollama_chat.assert_called_once()
    cloud.assert_not_called()
    assert result["searched"] is False


def test_failure_status_graceful():
    with patch.object(ollama, "list_models",side_effect=httpx.ConnectError("offline")):
        status=ollama.connection_status()
    assert status["connected"] is False and status["models"] == []


def test_status_for_unsaved_url_keeps_loopback_rule():
    """設定畫面可測試尚未儲存的網址，但仍不得連到回環 11434 以外的位置（防 SSRF）。"""
    fake=FakeClient({"models":[{"name":"llama3.2:3b"},{"name":"remote:cloud"}]})
    with patch.object(ollama.httpx,"Client",return_value=fake):
        status=ollama.connection_status("http://localhost:11434")
    assert status["connected"] is True and status["models"]==["llama3.2:3b"]
    assert fake.calls[0][1]=="http://localhost:11434/api/tags"
    for bad in ("http://192.168.1.5:11434","http://127.0.0.1:8420","https://evil.example"):
        with patch.object(ollama.httpx,"Client") as client:
            status=ollama.connection_status(bad)
        client.assert_not_called()
        assert status["connected"] is False and "11434" in status["message"]


def test_status_endpoint_accepts_base_url():
    from fastapi.testclient import TestClient
    from app.main import app
    fake=FakeClient({"models":[{"name":"qwen3:4b"}]})
    with patch.object(ollama.httpx,"Client",return_value=fake), patch.dict("os.environ",{"ASTRA_DESKTOP_TOKEN":""}):
        response=TestClient(app, base_url="http://127.0.0.1:8420").get(
            "/ollama/status", params={"base_url":"http://127.0.0.1:11434"})
    assert response.status_code==200 and response.json()["models"]==["qwen3:4b"]


if __name__=="__main__":
    test_only_loopback_hosts()
    test_models_only_reflect_installed()
    test_provider_routing_and_no_paid_fallback()
    test_configured_model_and_missing_model_error()
    test_ask_uses_ollama_not_opencode()
    test_failure_status_graceful()
    test_status_for_unsaved_url_keeps_loopback_rule()
    test_status_endpoint_accepts_base_url()
    print("Ollama provider tests passed")
