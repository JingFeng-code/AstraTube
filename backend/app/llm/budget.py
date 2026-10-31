"""各供應商的摘要額度預算。

Groq 先以低 TPM 帳號的保守設定起步，再依官方 x-ratelimit 回應標頭調整請求速度。
這些只是保護措施，不代表帳號實際的額度；Groq 可能依帳號與模型套用不同限制。
"""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class SummaryBudget:
    chunk_chars: int
    max_completion_tokens: int
    tokens_per_minute: int
    compact_prompt: bool = True
    workers: int = 1


# 這些模型實測的 Groq 免費／隨選額度是 8k TPM。
# 其他 Groq 模型同樣從保守值開始，再依回應標頭更新。
GROQ_LOW_TPM_MODELS = frozenset({
    "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
})
_DEFAULT_GROQ_TPM = 6000  # unknown models: conservative until headers arrive
_GROQ_COMPLETION_CAP = 1400
_GROQ_CHUNK_CHARS = 1800
MIN_GROQ_OUTPUT = 350  # 留給輸出的額度低於這個數字就不值得送出


def _groq_start_tpm(model: str) -> int:
    return 8000 if model in GROQ_LOW_TPM_MODELS else _DEFAULT_GROQ_TPM


def summary_budget(provider: str | None) -> SummaryBudget | None:
    """各模型的初始估計值，收到回應標頭後會改用實際的 TPM。"""
    if not provider or not provider.startswith("groq:"):
        return None
    model = provider.removeprefix("groq:").strip()
    if not model:
        return None
    tpm = groq_pacer.limit_for(model)
    ratio = min(1.0, tpm / 8000)
    return SummaryBudget(
        chunk_chars=max(500, int(_GROQ_CHUNK_CHARS * ratio)),
        max_completion_tokens=max(350, int(_GROQ_COMPLETION_CAP * ratio)),
        tokens_per_minute=tpm,
    )


def estimate_tokens(messages: list[dict]) -> int:
    """保守的估算，不是真正的 tokenizer：中日韓文字約每字 1 token，拉丁字母約每字 1/3。"""
    total = 0
    for message in messages:
        content = str(message.get("content") or "")
        cjk = sum(1 for ch in content if ord(ch) >= 0x2E80)
        total += cjk + math.ceil((len(content) - cjk) / 3) + 12
    return total


def trim_to_tokens(text: str, max_tokens: int) -> str:
    """從頭保留文字直到估算 token 數達到 max_tokens，並盡量切在行尾（逐字稿一行一個時間戳）。"""
    used = 0.0
    for index, ch in enumerate(text):
        used += 1 if ord(ch) >= 0x2E80 else 1 / 3
        if used > max_tokens:
            head = text[:index]
            newline = head.rfind("\n")
            return head[:newline] if newline > 0 else head
    return text


def _seconds(value: str | None) -> float | None:
    """解析 Groq 的重置時間（2m59.56s／7.66s／500ms）或 Retry-After 秒數。"""
    if not value:
        return None
    value = value.strip().lower()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", value)
    if not parts or not re.fullmatch(r"(?:\d+(?:\.\d+)?\s*(?:ms|h|m|s)\s*)+", value):
        return None
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    return sum(float(amount) * units[unit] for amount, unit in parts)


class GroqPacer:
    """同一個程序內所有 Groq 請求共用的速度閘門。

    不會儲存 API 憑證。服務端回應標頭優先於我們的保守預設值；
    真的遇到 429 時，仍要走明確的重試或錯誤流程。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._states: dict[str, dict] = {}

    def limit_for(self, model: str) -> int:
        with self._lock:
            state = self._states.get(model)
            return state["tpm"] if state else _groq_start_tpm(model)

    def before(self, model: str, estimated: int, *,
               on_status: Callable[[dict], None] | None = None) -> None:
        # 每個模型依序排隊，避免免費額度被同時送出的請求用完。
        with self._lock:
            state = self._states.setdefault(model, {
                "next_at": 0.0, "tpm": _groq_start_tpm(model),
                "remaining": None, "reset_at": 0.0,
            })
            now = time.monotonic()
            remaining = state["remaining"]
            # 剩餘額度只在重置前有意義，不能一直沿用。
            if remaining is not None and now >= state["reset_at"]:
                state["remaining"] = None
                remaining = None
            delay = max(0.0, state["next_at"] - now)
            if remaining is not None and remaining < estimated:
                delay = max(delay, max(0.0, state["reset_at"] - now))
            # 送出網路請求前先用保守估計佔好額度。
            # 先佔好時段再放開鎖：同模型的請求照樣排隊，但其他模型與查詢不會被這次等待卡住
            state["next_at"] = now + delay + 60.0 * estimated / max(1, state["tpm"])
            if state["remaining"] is not None:
                state["remaining"] = max(0, state["remaining"] - estimated)
        if delay > 0:
            if on_status:
                on_status({"state": "rate_wait", "provider": "groq",
                           "model": model, "delay": math.ceil(delay)})
            time.sleep(delay)

    def observe(self, model: str, headers: Mapping[str, str]) -> None:
        with self._lock:
            state = self._states.setdefault(model, {
                "next_at": 0.0, "tpm": _groq_start_tpm(model),
                "remaining": None, "reset_at": 0.0,
            })
            limit = headers.get("x-ratelimit-limit-tokens")
            remaining = headers.get("x-ratelimit-remaining-tokens")
            reset = _seconds(headers.get("x-ratelimit-reset-tokens"))
            if limit and limit.isdigit() and int(limit) > 0:
                state["tpm"] = int(limit)
            if remaining is not None and remaining.isdigit() and reset is not None:
                state["remaining"] = int(remaining)
                state["reset_at"] = time.monotonic() + reset

    def retry_delay(self, model: str, headers: Mapping[str, str]) -> float | None:
        """依官方額度標頭算出重試等待時間，不做任意的快速重試。"""
        retry = _seconds(headers.get("retry-after"))
        reset = _seconds(headers.get("x-ratelimit-reset-tokens"))
        delay = retry if retry is not None else reset
        if delay is None:
            return None
        delay = min(120.0, delay + 1.0)
        with self._lock:
            state = self._states.setdefault(model, {
                "next_at": 0.0, "tpm": _groq_start_tpm(model),
                "remaining": None, "reset_at": 0.0,
            })
            state["next_at"] = max(state["next_at"], time.monotonic() + delay)
        return delay


groq_pacer = GroqPacer()
