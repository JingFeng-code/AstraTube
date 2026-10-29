"""GET /models：給前端下拉選單用的供應商×模型清單。"""
from fastapi import APIRouter, Query

from app.core import languages, messages
from app.llm import anthropic_api, gemini, opencode, openai_compat, ollama

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> dict:
    """回傳每個供應商的模型 id 清單（不帶前綴，由前端組成 "<provider>:<id>"）。

    每個供應商附上：
      - models：可選模型
      - source："live"（跟供應商動態抓的）或 "static"（內建保底清單）
      - configured：有沒有填金鑰（前端用來灰掉沒設定的供應商）
    """
    free, free_source = opencode.list_free_models()
    deepseek_models, deepseek_source = openai_compat.list_models(openai_compat.DEEPSEEK)
    openai_models, openai_source = openai_compat.list_models(openai_compat.OPENAI)
    claude_models, claude_source = anthropic_api.list_models()

    local = ollama.connection_status()
    # 不把尚未安裝的模型顯示為可用選項。
    return {
        # 舊欄位保留，讓舊版前端不會整個壞掉
        "gemini": [gemini.MODEL],
        "opencode": free,
        "source": free_source,
        "default": f"opencode:{opencode.DEFAULT_FREE_MODEL}",
        "providers": {
            "ollama": {"label": "Ollama（本機）", "models": local["models"],
                       "source": "local", "configured": local["connected"] and bool(local["models"]),
                       "free": True, "connected": local["connected"]},
            "opencode": {"label": messages.t("provider.opencode_label"), "models": free,
                         "source": free_source, "configured": True, "free": True},
            "gemini": {"label": "Google Gemini", "models": [gemini.MODEL],
                       "source": "static", "configured": gemini.key_count() > 0, "free": False},
            "deepseek": {"label": openai_compat.DEEPSEEK.label, "models": deepseek_models,
                         "source": deepseek_source,
                         "configured": openai_compat.is_configured(openai_compat.DEEPSEEK),
                         "free": False},
            "openai": {"label": openai_compat.OPENAI.label, "models": openai_models,
                       "source": openai_source,
                       "configured": openai_compat.is_configured(openai_compat.OPENAI),
                       "free": False},
            "anthropic": {"label": "Anthropic Claude", "models": claude_models,
                          "source": claude_source,
                          "configured": anthropic_api.is_configured(), "free": False},
        },
        "languages": languages.codes(),
    }


@router.get("/ollama/status")
def ollama_status(base_url: str | None = Query(None, max_length=200)) -> dict:
    """設定畫面讀取本機 Ollama 狀態與已安裝模型（不回傳祕密）。

    base_url 讓使用者不必先儲存就能測試輸入中的網址；仍只接受本機 11434 埠。
    """
    return ollama.connection_status(base_url)
