"""Per-provider summarization budgets.

For Groq, use conservative initial settings for low-TPM accounts, then pace requests
with the official x-ratelimit headers. These are safeguards, not verified account
entitlements; Groq can apply different limits per account and per model.
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


# The user's observed free/on-demand Groq limits for these models are 8k TPM.
# Other Groq models begin conservatively and update from response headers.
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
    """Initial per-model estimates, adapted to actual TPM once headers are observed."""
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
    """Conservative heuristic, not a tokenizer: CJK ≈ 1 token/char, Latin ≈ 1/3."""
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
    """Groq reset values: 2m59.56s / 7.66s / 500ms, or Retry-After seconds."""
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
    """A process-local rate gate shared across simultaneous Groq requests.

    It never stores API credentials. The server's own headers override our
    conservative default; actual 429s still need an explicit retry/error path.
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
        # Serialized per model, preventing free-tier parallel bursts.
        with self._lock:
            state = self._states.setdefault(model, {
                "next_at": 0.0, "tpm": _groq_start_tpm(model),
                "remaining": None, "reset_at": 0.0,
            })
            now = time.monotonic()
            remaining = state["remaining"]
            # Remaining is only meaningful until the reset; never reuse it forever.
            if remaining is not None and now >= state["reset_at"]:
                state["remaining"] = None
                remaining = None
            delay = max(0.0, state["next_at"] - now)
            if remaining is not None and remaining < estimated:
                delay = max(delay, max(0.0, state["reset_at"] - now))
            if delay > 0:
                if on_status:
                    on_status({"state": "rate_wait", "provider": "groq",
                               "model": model, "delay": math.ceil(delay)})
                time.sleep(delay)
            # Reserve pessimistically before any network request starts.
            state["next_at"] = time.monotonic() + 60.0 * estimated / max(1, state["tpm"])
            if state["remaining"] is not None:
                state["remaining"] = max(0, state["remaining"] - estimated)

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
        """Retry delay from official rate-limit headers, not arbitrary rapid retries."""
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
