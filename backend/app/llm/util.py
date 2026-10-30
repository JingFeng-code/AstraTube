"""LLM 呼叫的重試／退避工具。"""
import re
import time
from typing import Any, Callable, TypeVar

from app.core import messages

T = TypeVar("T")

# 視為「暫時性、可重試」的錯誤特徵（伺服器過載、塞車、次數上限等）
_TRANSIENT_HINTS = (
    "overloaded", "high demand", "unavailable", "resource_exhausted",
    "resource has been exhausted", "rate limit", "ratelimit", "try again",
    "temporarily", "deadline", "timeout", "503", "429", "500", "502", "504",
)


def is_transient(e: Exception) -> bool:
    """判斷是否為暫時性錯誤（值得重試／換金鑰／換供應商）。"""
    from app.llm.base import EmptyResponseError, TruncatedOutputError
    if isinstance(e, EmptyResponseError):
        return True  # 空回應重試通常就好，不該當成永久失敗直接放棄整段
    if isinstance(e, TruncatedOutputError):
        return False  # 同一份請求重試還是會被截斷
    if getattr(e, "model_unavailable", False) or getattr(e, "permanent_rate_limit", False):
        return False  # 模型下架／暫停：重試同一個模型沒用，直接換下一個
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    try:
        if int(code) in (429, 500, 502, 503, 504):
            return True
    except (TypeError, ValueError):
        pass
    msg = str(e).lower()
    return any(h in msg for h in _TRANSIENT_HINTS)


def with_retry(fn: Callable[[], T], *, tries: int = 3, base: float = 0.8,
               max_sleep: float = 6.0, label: str = "",
               on_status: Callable[[dict[str, Any]], None] | None = None) -> T:
    """重試 fn()。只在暫時性錯誤時退避重試；其他錯誤（如金鑰錯誤）立即拋出。"""
    last: Exception | None = None
    for i in range(tries):
        if on_status:
            on_status({"state": "request", "attempt": i + 1, "tries": tries})
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i == tries - 1 or not is_transient(e):
                raise
            suggested = getattr(e, "retry_after", None)
            sleep = (min(120.0, max(0.0, float(suggested))) if suggested is not None
                     else min(base * (2 ** i), max_sleep))
            print(f"[LLM] {label} 暫時性錯誤，{sleep:.1f}s 後重試（第 {i + 1} 次）：{e}", flush=True)
            if on_status:
                on_status({"state": "retry_wait", "attempt": i + 2,
                           "tries": tries, "delay": sleep})
            time.sleep(sleep)
    raise last  # type: ignore[misc]


# ── 給使用者看的錯誤說明 ─────────────────────────────────────
# 供應商錯誤要讓人看得出「是誰的問題、下一步做什麼」，不能只丟一個狀態碼。

_TAG = re.compile(r"<[^>]{0,200}>")


def _clean_detail(body: str, limit: int = 160) -> str:
    """把回應內容整理成短句：去掉 HTML 標籤（例如 Cloudflare 擋頁）與多餘空白。"""
    text = _TAG.sub(" ", body or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _status_hint(status: int) -> str:
    if status in (401, 403):
        return messages.t("provider.hint_auth")
    if status == 404:
        return messages.t("provider.hint_not_found")
    if status == 429:
        return messages.t("provider.hint_rate_limit")
    if status >= 500:
        return messages.t("provider.hint_server")
    return ""


# 空回應時可以顯示的結束原因（OpenAI 相容服務與 Anthropic 的標準值）
_KNOWN_FINISH_REASONS = frozenset({
    "stop", "length", "content_filter", "tool_calls", "function_call",
    "end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
})


def safe_finish_reason(value: Any) -> str:
    """結束原因由上游提供，可能夾帶任意文字；只放行已知的值，其餘一律不顯示原文。"""
    return value if isinstance(value, str) and value in _KNOWN_FINISH_REASONS else "unknown"


def public_reason(error: Exception) -> str:
    """可以安全顯示給瀏覽器的原因：只含狀態碼與我們自己寫的建議，不含服務端回應原文。

    服務端錯誤內容可能回顯金鑰或送出去的字幕，這類內容只留在後端紀錄。
    """
    return getattr(error, "public_message", "") or ""


def user_error(error: Exception | None, provider: str | None = None) -> str:
    """給瀏覽器看的錯誤文字。絕不回傳上游回應內容：它可能回顯金鑰或送出去的字幕。

    例外本身的 str() 只有確定由我們自己產生時才能用；其餘只說狀態碼或通用說明，
    完整內容留在後端紀錄。Ollama 的錯誤訊息全由本機程式產生，可以直接顯示。
    """
    from app.llm.base import NotConfiguredError, ProviderError, RefusalError
    if error is None:
        return messages.t("provider.failed_generic")
    public = public_reason(error)
    if public:
        return public
    if isinstance(error, (ValueError, NotConfiguredError, RefusalError)):
        return str(error)
    if (provider or "").startswith("ollama:") and isinstance(error, ProviderError):
        return str(error)
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    try:
        status = int(code)
    except (TypeError, ValueError):
        return messages.t("provider.failed_generic")
    return f"HTTP {status} {_status_hint(status)}".strip()


def response_error(vendor: str, message: str) -> "ProviderError":
    """上游回了無法使用的內容：message 可含內容摘要供後端紀錄，公開訊息只說明狀況。"""
    from app.llm.base import ProviderError
    error = ProviderError(message)
    error.public_message = messages.t("provider.bad_response", vendor=vendor)
    return error


def http_error(vendor: str, status: int, body: str) -> "ProviderError":
    """建立 HTTP 錯誤：完整訊息（含回應摘要）供後端紀錄與重試判斷，公開訊息只含狀態碼與建議。"""
    from app.llm.base import ProviderError
    error = ProviderError(http_error_message(vendor, status, body))
    error.status_code = status
    error.public_message = f"{vendor} HTTP {status} {_status_hint(status)}".strip()
    return error


def connect_error(vendor: str, cause: Exception) -> "ProviderError":
    """建立連線錯誤；公開訊息只說明是逾時還是連不上。"""
    import httpx
    from app.llm.base import ProviderError
    error = ProviderError(connect_error_message(vendor, cause))
    key = "provider.hint_timeout" if isinstance(cause, httpx.TimeoutException) else "provider.hint_network"
    error.public_message = f"{messages.t('provider.connect_failed', vendor=vendor, error=type(cause).__name__)} {messages.t(key)}"
    return error


def http_error_message(vendor: str, status: int, body: str) -> str:
    """HTTP 錯誤：原始狀態碼與內容摘要＋下一步建議。狀態碼保留在字串中，供重試判斷使用。"""
    text = messages.t("provider.http_error", vendor=vendor, status=status,
                      detail=_clean_detail(body) or "-")
    hint = _status_hint(status)
    return f"{text} {hint}".strip()


def connect_error_message(vendor: str, error: Exception) -> str:
    """連線層錯誤：區分逾時與連不上。逾時字樣保留給重試判斷。"""
    import httpx
    key = "provider.hint_timeout" if isinstance(error, httpx.TimeoutException) else "provider.hint_network"
    text = messages.t("provider.connect_failed", vendor=vendor,
                      error=_clean_detail(str(error)) or type(error).__name__)
    return f"{text} {messages.t(key)}"
