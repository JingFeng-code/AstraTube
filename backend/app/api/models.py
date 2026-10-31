"""GET /models：列出使用者可設定的供應商，實際模型在驗證後才載入。"""
from fastapi import APIRouter, Query

from app.core import languages
from app.llm import anthropic_api, gemini, openai_compat, ollama

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> dict:
    """避免啟動時呼叫多家雲端；只回傳金鑰設定狀態與本機已安裝模型。

    雲端模型清單由 POST /providers/check 在 API Key 驗證後讀取。
    未驗證不得以靜態模型清單假裝可用。
    """
    local = ollama.connection_status()
    providers = {
        "ollama": {
            "label": "Ollama（本機）", "models": local["models"],
            "source": "local", "configured": local["connected"] and bool(local["models"]),
            "free": True, "connected": local["connected"],
        },
        "gemini": {
            "label": "Google Gemini", "models": [],
            "source": "unverified", "configured": gemini.key_count() > 0, "free": False,
        },
        "anthropic": {
            "label": "Anthropic Claude", "models": [],
            "source": "unverified", "configured": anthropic_api.is_configured(), "free": False,
        },
    }
    for vendor in openai_compat.VENDORS.values():
        providers[vendor.key] = {
            "label": vendor.label, "models": [], "source": "unverified",
            "configured": openai_compat.is_configured(vendor), "free": False,
        }
    return {"providers": providers, "languages": languages.codes()}


@router.get("/ollama/status")
def ollama_status(base_url: str | None = Query(None, max_length=200)) -> dict:
    return ollama.connection_status(base_url)
