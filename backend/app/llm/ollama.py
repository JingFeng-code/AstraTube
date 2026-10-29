"""本機 Ollama 供應商：不需 API Key，不將影片文字傳送到雲端。

為避免在公開 Web 後端被用作 SSRF 代理，僅允許回環介面及標準 11434 埠。
若 Ollama 與 FastAPI 不在同一台電腦／容器，請改用本地部署或經審核的連線方案。
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import httpx

from app.core import config
from app.llm.base import ProviderError

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_HOSTS = {"127.0.0.1", "localhost", "::1"}
# 改用串流：read 逾時是「兩段輸出之間」的等待上限，而不是整個回答的總時間。
# 長逐字稿＋會先思考的模型（例如 qwen3）總共可能要好幾分鐘，只要持續有輸出就不會被中斷；
# 300 秒涵蓋讀入長逐字稿到吐出第一個字的時間。
_TIMEOUT = httpx.Timeout(connect=3.0, read=300.0, write=30.0, pool=3.0)
# Ollama 預設的上下文長度通常只有 4096 tokens，摘要片段（約 12000 字）會被默默截掉前段。
# 依內容長度取足夠的上下文（中文約 1 字 1 token，另留輸出空間），上限避免吃光顯示記憶體。
_MIN_CTX = 8192
_MAX_CTX = 32768
_OUTPUT_RESERVE = 4096


def validate_base_url(value: str | None) -> str:
    """只允許無認證的 http 回環來源；不接受 URL 路徑、查詢或重新導向。"""
    raw = (value or DEFAULT_BASE_URL).strip()
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme != "http" or parsed.hostname not in _HOSTS or
                parsed.port != 11434 or parsed.username is not None or
                parsed.password is not None or parsed.path not in ("", "/") or
                parsed.query or parsed.fragment):
            raise ValueError
    except ValueError as exc:
        raise ValueError("Ollama 目前僅允許 http://127.0.0.1:11434 或 http://localhost:11434。") from exc
    return raw.rstrip("/")


def base_url() -> str:
    return validate_base_url(config.get("OLLAMA_BASE_URL"))


def validate_model(value: str) -> str:
    name = (value or "").strip()
    # Ollama 也提供雲端模型；此 provider 僅供真正本地推論。
    if name.lower().endswith("-cloud") or name.lower().endswith(":cloud"):
        raise ValueError("這是 Ollama 雲端模型；請選擇下載到本機的模型。")
    if not _MODEL.fullmatch(name):
        raise ValueError("Ollama 模型名稱格式不正確。")
    return name


def default_model() -> str:
    return (config.get("OLLAMA_MODEL") or "").strip()


def list_models(url: str | None = None) -> list[str]:
    """只列出該 Ollama 實例真正已安裝的模型，不生成假選項。

    url 給定時（設定畫面測試尚未儲存的網址）同樣必須通過 validate_base_url。
    """
    target = validate_base_url(url) if url is not None else base_url()
    with httpx.Client(timeout=httpx.Timeout(3.0), trust_env=False, follow_redirects=False) as client:
        response = client.get(target + "/api/tags")
        response.raise_for_status()
        data = response.json()
    raw = data.get("models", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        raise ProviderError("Ollama 模型清單格式不正確。")
    names = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and _MODEL.fullmatch(name) and (
                not name.lower().endswith(("-cloud", ":cloud"))
        ) and name not in names:
            names.append(name)
    return names


def connection_status(url: str | None = None) -> dict:
    if url is not None:
        try:
            validate_base_url(url)
        except ValueError as exc:
            return {"connected": False, "models": [], "message": str(exc)}
    try:
        models = list_models(url)
        return {"connected": True, "models": models, "message": (
            "連線成功，目前尚未安裝模型。請先在本機執行 ollama pull <模型名稱>。"
            if not models else "已連接到本機 Ollama。")}
    except (httpx.HTTPError, ValueError, ProviderError, OSError):
        return {"connected": False, "models": [], "message":
                "無法連線到本機 Ollama。請確認 Ollama 已啟動，且與 AstraTube 後端位於同一環境。"}


def _selected_model(model: str) -> str:
    name = model.strip() if model else default_model()
    if name:
        return validate_model(name)
    installed = list_models()
    if not installed:
        raise ProviderError("Ollama 尚無已安裝模型，請先執行 ollama pull <模型名稱>。")
    return installed[0]


def context_size(payload_messages: list[dict]) -> int:
    """依請求長度估算需要的上下文長度，取 8192 的倍數（同一長度可重用已載入的模型）。"""
    chars = sum(len(str(m.get("content", ""))) for m in payload_messages)
    needed = chars + _OUTPUT_RESERVE
    size = -(-needed // _MIN_CTX) * _MIN_CTX
    return max(_MIN_CTX, min(_MAX_CTX, size))


def generate_messages(messages: list[dict], system: str = "", model: str = "",
                      tries: int = 1, on_status=None) -> tuple[str, str]:
    """串流呼叫 /api/chat 並組回完整文字。local-only，指定 Ollama 不會默默轉到雲端。"""
    name = _selected_model(model)
    payload_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
    if not payload_messages:
        raise ProviderError("Ollama 請求內容不可為空。")
    payload = {"model": name, "messages": payload_messages, "stream": True,
               "options": {"num_ctx": context_size(payload_messages)}}
    parts: list[str] = []
    finished = False
    try:
        with httpx.Client(timeout=_TIMEOUT, trust_env=False, follow_redirects=False) as client:
            with client.stream("POST", base_url() + "/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise ProviderError(f"Ollama 找不到模型 {name}，請先在本機下載該模型。")
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if not isinstance(chunk, dict):
                        raise ValueError("unexpected chunk")
                    if chunk.get("error"):
                        raise ProviderError(f"Ollama 回報錯誤：{str(chunk['error'])[:200]}")
                    piece = (chunk.get("message") or {}).get("content", "")
                    if isinstance(piece, str):
                        parts.append(piece)
                    if chunk.get("done"):
                        finished = True
                        break
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError("無法連線 Ollama，請檢查本機服務是否啟動。") from exc
    except httpx.TimeoutException as exc:
        raise ProviderError("Ollama 超過 5 分鐘沒有任何輸出，可能是模型太大、顯示記憶體不足而改用 CPU；"
                            "建議換用較小的本機模型（例如 qwen3:4b）。") from exc
    except httpx.HTTPStatusError as exc:
        raise ProviderError(f"Ollama 伺服器回應 HTTP {exc.response.status_code}。") from exc
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ProviderError("Ollama 回應格式不正確或本機服務不可用。") from exc
    if not finished:
        # 連線正常結束但沒收到 done：回答被中斷（例如 Ollama 中途卸載模型），不能當成完整答案
        raise ProviderError("Ollama 回答到一半就中斷了，請再試一次；若一直發生，請換用較小的本機模型。")
    content = "".join(parts).strip()
    if not content:
        raise ProviderError("Ollama 沒有回傳文字內容，請檢查模型是否支援文字對話。")
    return content, f"Ollama/{name}"


def generate(prompt: str, system: str = "", model: str = "", seg: int = 0,
             on_status=None) -> tuple[str, str]:
    return generate_messages([{"role": "user", "content": prompt}], system, model,
                             on_status=on_status)
