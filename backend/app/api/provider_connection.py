"""AI 供應商連線檢查：只使用預先定義的官方端點，不暴露 API Key。

這個端點用於設定精靈：驗證使用者輸入（或已儲存）的金鑰，成功後取得
該金鑰實際可見的模型清單。失敗時不使用假資料或靜態模型冒充連線成功。
"""
from __future__ import annotations

import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import config
from app.llm import ollama

router = APIRouter(prefix="/providers", tags=["providers"])

Provider = Literal["gemini", "openai", "deepseek", "anthropic", "ollama",
                   "openrouter", "groq", "mistral", "together"]
_CONFIG_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
}
_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "deepseek": "https://api.deepseek.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "together": "https://api.together.ai/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
}
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_EXCLUDE = ("embed", "audio", "speech", "transcrib", "whisper", "image", "dall-e",
            "tts", "moderation", "realtime", "search", "rerank")


class CheckProviderRequest(BaseModel):
    provider: Provider
    api_key: str | None = Field(default=None, max_length=4096)
    ollama_base_url: str | None = Field(default=None, max_length=200)


def _models_from_rows(rows: list, *, provider: str = "") -> list[str]:
    names = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        value = item.get("id", "")
        if not isinstance(value, str) or not _MODEL_ID.fullmatch(value):
            continue
        if any(block in value.lower() for block in _EXCLUDE):
            continue
        if provider == "groq" and any(block in value.lower() for block in ("guard", "prompt-guard")):
            continue
        # Mistral 直接提供是否支援 Chat Completion 的能力旗標。
        if provider == "mistral" and (item.get("capabilities") or {}).get("completion_chat") is False:
            continue
        # OpenRouter 可能包含僅產生圖片／音訊的模型；只列有文字輸出者。
        if provider == "openrouter":
            output = (item.get("architecture") or {}).get("output_modalities") or ["text"]
            if "text" not in output:
                continue
        if value not in names:
            names.append(value)
    # OpenRouter 的目錄可能超過數百筆，搭配前端搜尋欄而不是在此截斷。
    return names[:1500] if provider == "openrouter" else names[:300]


def _require_http_ok(res: httpx.Response) -> None:
    if res.status_code in (401, 403):
        raise HTTPException(res.status_code, "API Key 無效，或沒有讀取模型清單的權限。")
    if res.status_code == 429:
        raise HTTPException(429, "供應商目前限制請求，請稍後再試。")
    if res.status_code >= 400:
        raise HTTPException(503, "供應商無法提供模型清單，請稍後再試。")


def _http_models(provider: str, key: str) -> list[str]:
    # 只使用固定白名單 URL，不能讓輸入的供應商／模型組成任意 HTTP 目的地。
    headers = {"Authorization": f"Bearer {key}"} if provider != "anthropic" else {
        "x-api-key": key, "anthropic-version": "2023-06-01",
    }
    try:
        with httpx.Client(timeout=12.0, follow_redirects=False, trust_env=False) as client:
            if provider == "openrouter":
                # /models 可公開查詢，不能用它的 200 判斷 API Key 有效。
                auth = client.get("https://openrouter.ai/api/v1/key", headers=headers)
                _require_http_ok(auth)
            res = client.get(_ENDPOINTS[provider], headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "無法連線 AI 供應商，請檢查網路後重試。") from exc
    _require_http_ok(res)
    try:
        data = res.json()
        rows = data.get("data")
        if not isinstance(rows, list):
            raise ValueError("unexpected response")
        return _models_from_rows(rows, provider=provider)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(502, "供應商回傳了無法辨識的模型清單。") from exc


def _gemini_models(key: str) -> list[str]:
    try:
        from google import genai
        client = genai.Client(api_key=key, http_options={"timeout": 12000})
        names = []
        for item in client.models.list():
            actions = (getattr(item, "supported_actions", None) or
                       getattr(item, "supported_generation_methods", None) or [])
            if "generateContent" not in actions:
                continue
            model = (getattr(item, "name", "") or "").removeprefix("models/")
            if _MODEL_ID.fullmatch(model) and model not in names:
                names.append(model)
            if len(names) >= 200:
                break
        return names
    except Exception as exc:  # SDK 對驗證、權限與網路錯誤使用不同例外
        code = getattr(exc, "code", None)
        if code in (401, 403):
            raise HTTPException(code, "Gemini API Key 無效，或沒有模型清單權限。") from exc
        if code == 429:
            raise HTTPException(429, "Gemini 已達請求限制，請稍後再試。") from exc
        raise HTTPException(503, "無法驗證 Gemini API Key 或載入模型，請確認金鑰與網路。") from exc


@router.post("/check")
def check_provider(req: CheckProviderRequest) -> dict:
    """傳回已驗證連線的模型；只在雲端使用者明確按下檢查時傳送其金鑰。"""
    if req.provider == "ollama":
        status = ollama.connection_status(req.ollama_base_url)
        if not status["connected"]:
            raise HTTPException(503, status["message"])
        return {"provider": "ollama", "connected": True, "models": status["models"], "source": "live"}
    key = (req.api_key or "").strip() or (config.get(_CONFIG_KEYS[req.provider]) or "").strip()
    # 保留原有 Gemini 多金鑰設定格式；連線驗證使用第一把。
    if req.provider == "gemini":
        key = re.split(r"[,\s]+", key)[0]
    if not key:
        raise HTTPException(400, "請先輸入 API Key。")
    models = _gemini_models(key) if req.provider == "gemini" else _http_models(req.provider, key)
    if not models:
        raise HTTPException(422, "連線成功，但找不到可用的文字生成模型。")
    return {"provider": req.provider, "connected": True, "models": models, "source": "live"}
