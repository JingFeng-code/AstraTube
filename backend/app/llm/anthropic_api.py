"""Anthropic（Claude）供應商，走官方 anthropic Python SDK。

刻意不帶 temperature／top_p／top_k 與 thinking 設定：
Claude Opus 5 / Fable 5 / Opus 4.8 / 4.7 會對取樣參數回 400，而 thinking 的可用值
又隨模型版本而異。只送 model／max_tokens／system／messages 這組最小交集，
使用者在下拉選單挑任何 Claude 模型都不會因為參數不相容而失敗。
"""
import time
from typing import Any, Callable, Tuple

from app.core import config, messages
from app.llm.base import (EmptyResponseError, NotConfiguredError,
                          ProviderError, RefusalError)
from app.llm.util import with_retry

LABEL = "Claude"
CONSOLE_URL = "https://console.anthropic.com/settings/keys"

DEFAULT_MODEL = "claude-opus-5"

# 抓不到動態清單時的保底（依能力由高至低）
STATIC_MODELS: tuple[str, ...] = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5",
)

# 摘要輸出是一整份卡片 JSON，需要足夠的輸出上限；
# 16000 是官方建議的「非串流」上限，再往上要改走串流才不會撞到 HTTP 逾時。
MAX_TOKENS = 16000

_MODELS_TTL = 3600.0
_models_cache: tuple[float, list[str], str] | None = None
_clients: dict[str, Any] = {}


def api_key() -> str:
    return (config.get("ANTHROPIC_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(api_key())


def _client():
    """每把金鑰快取一個 client（SDK 內部會重用連線池）。"""
    key = api_key()
    if not key:
        raise NotConfiguredError(messages.t("provider.no_key", vendor="Anthropic"))
    c = _clients.get(key)
    if c is None:
        import anthropic
        c = anthropic.Anthropic(api_key=key)
        _clients[key] = c
    return c


def list_models() -> Tuple[list[str], str]:
    """回傳 (模型 id 清單, 來源)。沒金鑰或抓取失敗時回靜態清單。"""
    global _models_cache
    now = time.monotonic()
    if _models_cache and now - _models_cache[0] < _MODELS_TTL:
        return list(_models_cache[1]), _models_cache[2]

    models, source = list(STATIC_MODELS), "static"
    if is_configured():
        try:
            ids = [m.id for m in _client().models.list() if getattr(m, "id", "")]
            if ids:
                ids.sort(key=lambda i: (i != DEFAULT_MODEL, i))
                models, source = ids, "live"
        except Exception as e:  # noqa: BLE001
            print(f"[{LABEL}] 取得模型清單失敗，改用內建靜態清單：{e}", flush=True)

    _models_cache = (now, list(models), source)
    return list(models), source


def _text_of(resp) -> str:
    """把回應的 content blocks 併成純文字（只取 text 型別）。"""
    parts = []
    for block in resp.content or []:
        if getattr(block, "type", "") == "text" and getattr(block, "text", ""):
            parts.append(block.text)
    return "".join(parts)


def _once(model: str, messages: list[dict], system: str) -> str:
    """打一次 Messages API，回傳純文字。"""
    import anthropic
    try:
        resp = _client().messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            **({"system": system} if system else {}),
            messages=messages,
        )
    except anthropic.APIStatusError as e:
        # 429／5xx 交給 with_retry 判定為暫時性錯誤；其餘（400/401/404）立即失敗
        raise ProviderError(messages.t("provider.http_error", vendor=LABEL,
                                       status=e.status_code, detail=str(e)[:200]))
    except anthropic.APIConnectionError as e:
        raise ProviderError(messages.t("provider.connect_failed", vendor=LABEL, error=e))

    # 安全分類器可能婉拒請求：HTTP 200 但 stop_reason 是 refusal，content 為空或只有片段。
    # 這是內容層面的結果不是錯誤，重試同一份 prompt 沒有意義，要直接讓使用者換模型。
    if getattr(resp, "stop_reason", None) == "refusal":
        detail = getattr(resp, "stop_details", None)
        category = getattr(detail, "category", None) if detail else None
        raise RefusalError(messages.t(
            "provider.refusal", vendor=LABEL,
            category=category or messages.t("provider.refusal_uncategorized")))

    text = _text_of(resp)
    if not text.strip():
        raise EmptyResponseError(messages.t(
            "provider.empty_response", vendor=LABEL,
            reason=f"stop_reason={getattr(resp, 'stop_reason', None)}"))
    return text


def generate_messages(messages: list[dict], system: str = "", model: str = "",
                      tries: int = 3,
                      on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """多輪對話生成。messages 為 [{"role": "user"|"assistant", "content": str}, ...]。"""
    model = model or DEFAULT_MODEL

    def report(event: dict[str, Any]) -> None:
        if on_status:
            on_status({"provider": "anthropic", "model": model, **event})

    text = with_retry(lambda: _once(model, list(messages), system), tries=tries,
                      label=f"{LABEL}/{model}", on_status=report)
    return text, f"{LABEL}/{model}"


def generate(prompt: str, system: str = "", model: str = "", tries: int = 3,
             on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """單輪文字生成。回傳 (文字, 模型標籤)。"""
    return generate_messages([{"role": "user", "content": prompt}], system=system,
                             model=model, tries=tries, on_status=on_status)
