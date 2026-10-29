"""OpenCode Zen 供應商（OpenAI-compatible）。

免費模型實測不需要金鑰；有設定 OPENCODE_API_KEY 才帶 Authorization header。
"""
import time
from typing import Any, Callable, Tuple

import httpx

from app.core import config, messages
from app.llm.base import EmptyResponseError, ProviderError
from app.llm.util import with_retry

BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_FREE_MODEL = "deepseek-v4-flash-free"

# 抓不到動態清單時的保底（big-pickle 無 -free 後綴但屬免費模型）
STATIC_FREE_MODELS: tuple[str, ...] = (
    "deepseek-v4-flash-free",
    "big-pickle",
    "mimo-v2.5-free",
    "laguna-s-2.1-free",
    "ling-3.0-flash-free",
    "ling-3.0-tiny-free",
    "nemotron-3-ultra-free",
    "north-mini-code-free",
    "longcat-2.0-free",
)

# 自動模式的接力順序：依「繁中摘要＋嚴格 JSON」適配度排列，前面的失敗才輪到後面。
# 排序依據（2026-08-08 調查）：deepseek=官方+中文強+structured_output true；
# longcat=美團 1.6T MoE 中文強；mimo=小米官方；nemotron=NVIDIA 大模型但偏英語中心。
# 不進鏈：big-pickle（身分未公開且底層會輪換）、laguna/ling-flash/ling-tiny/north-mini-code
# （程式碼專用、已 deprecated、過小、或 structured_output=false），僅留給使用者手動選。
AUTO_CHAIN: tuple[str, ...] = (
    "deepseek-v4-flash-free",
    "longcat-2.0-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
)

_MODELS_TTL = 3600.0  # 模型清單記憶體快取 1 小時
_models_cache: tuple[float, list[str], str] | None = None

# 免費模型會做長篇推理，一次摘要實測可跑到 3 分鐘以上，讀取逾時要給足
_CHAT_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=60.0, pool=15.0)


def _headers() -> dict[str, str]:
    """有金鑰才帶 Authorization（免費模型可不帶）。"""
    headers = {"Content-Type": "application/json"}
    key = (config.get("OPENCODE_API_KEY") or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _is_free(model_id: str) -> bool:
    """免費判定：id 以 -free 結尾，或在靜態免費表內。"""
    return model_id.endswith("-free") or model_id in STATIC_FREE_MODELS


def list_free_models() -> Tuple[list[str], str]:
    """回傳 (免費模型 id 清單, 來源)。來源為 "live"（動態抓取）或 "static"（保底清單）。"""
    global _models_cache
    now = time.monotonic()
    if _models_cache and now - _models_cache[0] < _MODELS_TTL:
        return list(_models_cache[1]), _models_cache[2]

    models, source = list(STATIC_FREE_MODELS), "static"
    try:
        resp = httpx.get(f"{BASE_URL}/models", headers=_headers(), timeout=10.0)
        resp.raise_for_status()
        ids = [str(m.get("id", "")) for m in resp.json().get("data", [])]
        free = [i for i in ids if i and _is_free(i)]
        if free:
            # 預設模型排最前面，其餘保持伺服器回傳順序
            free.sort(key=lambda i: (i != DEFAULT_FREE_MODEL,))
            models, source = free, "live"
    except Exception as e:  # noqa: BLE001
        print(f"[OpenCode] 取得模型清單失敗，改用內建靜態清單：{e}", flush=True)

    _models_cache = (now, list(models), source)
    return list(models), source


def _post_chat(model: str, messages: list[dict]) -> str:
    """打一次 /chat/completions，回傳助手訊息內容。"""
    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers=_headers(),
            json={"model": model, "messages": messages},
            timeout=_CHAT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise ProviderError(messages.t("provider.connect_failed", vendor="OpenCode", error=e))

    if resp.status_code >= 400:
        raise ProviderError(messages.t("provider.http_error", vendor="OpenCode",
                                       status=resp.status_code, detail=resp.text[:200]))
    try:
        data = resp.json()
    except Exception:
        raise ProviderError(messages.t("provider.not_json", vendor="OpenCode",
                                       detail=resp.text[:200]))

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise ProviderError(messages.t("provider.error", vendor="OpenCode", detail=msg))

    choices = (data or {}).get("choices") or []
    msg = (choices[0].get("message", {}) or {}) if choices else {}
    text = msg.get("content")
    if not text:
        # reasoning 模型有時把整份輸出放在 reasoning_content，content 留空
        text = msg.get("reasoning_content") or ""
    if not text.strip():
        finish = choices[0].get("finish_reason") if choices else None
        raise EmptyResponseError(messages.t("provider.empty_response", vendor="OpenCode",
                                            reason=f"finish_reason={finish}"))
    return text


def generate(prompt: str, system: str = "", model: str = DEFAULT_FREE_MODEL,
             seg: int = 0, tries: int = 3,
             on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """文字生成。回傳 (文字, 模型標籤)。tries 供接力鏈調低單模型重試數。"""
    return generate_messages([{"role": "user", "content": prompt}],
                             system=system, model=model, tries=tries, on_status=on_status)


def generate_messages(messages: list[dict], system: str = "",
                      model: str = DEFAULT_FREE_MODEL, tries: int = 3,
                      on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """多輪對話生成（無搜尋工具）。messages 為 OpenAI 格式的 user/assistant 交錯清單。"""
    msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
    def report(event: dict[str, Any]) -> None:
        if on_status:
            on_status({"provider": "opencode", "model": model, **event})

    text = with_retry(lambda: _post_chat(model, msgs), tries=tries,
                      label=f"OpenCode/{model}", on_status=report)
    return text, model
