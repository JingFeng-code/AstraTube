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
_DEFAULT_GROQ_TPM = 8000
_GROQ_COMPLETION_CAP = 1400
_GROQ_CHUNK_CHARS = 1800


def summary_budget(provider: str | None) -> SummaryBudget | None:
    """Only opt in strict providers; never silently change other AI backends."""
    if not provider or not provider.startswith("groq:"):
        return None
    model = provider.removeprefix("groq:").strip()
    if not model:
        return None
    return SummaryBudget(
        chunk_chars=_GROQ_CHUNK_CHARS, max_completion_tokens=_GROQ_COMPLETION_CAP,
        tokens_per_minute=_DEFAULT_GROQ_TPM,
    )


def estimate_tokens(messages: list[dict]) -> int:
    """Conservative heuristic, not a tokenizer: CJK ≈ 1 token/char, Latin ≈ 1/3."""
    total = 0
    for message in messages:
        content = str(message.get("content") or "")
        cjk = sum(1 for ch in content if ord(ch) >= 0x2E80)
        total += cjk + math.ceil((len(content) - cjk) / 3) + 12
    return total


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

    def before(self, model: str, estimated: int, *,
               on_status: Callable[[dict], None] | None = None) -> None:
        # Serialized per model, preventing free-tier parallel bursts.
        with self._lock:
            state = self._states.setdefault(model, {
                "next_at": 0.0, "tpm": _DEFAULT_GROQ_TPM,
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
                "next_at": 0.0, "tpm": _DEFAULT_GROQ_TPM,
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
                "next_at": 0.0, "tpm": _DEFAULT_GROQ_TPM,
                "remaining": None, "reset_at": 0.0,
            })
            state["next_at"] = max(state["next_at"], time.monotonic() + delay)
        return delay


groq_pacer = GroqPacer()
