"""LLM 呼叫的重試／退避工具。"""
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# 視為「暫時性、可重試」的錯誤特徵（伺服器過載、塞車、次數上限等）
_TRANSIENT_HINTS = (
    "overloaded", "high demand", "unavailable", "resource_exhausted",
    "resource has been exhausted", "rate limit", "ratelimit", "try again",
    "temporarily", "deadline", "timeout", "503", "429", "500", "502", "504",
)


def is_transient(e: Exception) -> bool:
    """判斷是否為暫時性錯誤（值得重試／換金鑰／換供應商）。"""
    from app.llm.base import EmptyResponseError
    if isinstance(e, EmptyResponseError):
        return True  # 空回應重試通常就好，不該當成永久失敗直接放棄整段
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
            sleep = min(base * (2 ** i), max_sleep)
            print(f"[LLM] {label} 暫時性錯誤，{sleep:.1f}s 後重試（第 {i + 1} 次）：{e}", flush=True)
            if on_status:
                on_status({"state": "retry_wait", "attempt": i + 2,
                           "tries": tries, "delay": sleep})
            time.sleep(sleep)
    raise last  # type: ignore[misc]
