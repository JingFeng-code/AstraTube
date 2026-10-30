"""OpenAI 相容的 Chat Completions 供應商共用實作。

DeepSeek 與 OpenAI 兩家都用 `/v1/chat/completions` 這組相同的介面，差別只在
base URL、金鑰欄位與模型清單，因此共用同一個 client，避免兩份幾乎一樣的程式碼。
"""
import time
from dataclasses import dataclass
from typing import Any, Callable, Tuple

import httpx

from app.core import config, messages
from app.llm.budget import groq_pacer, summary_budget, estimate_tokens
from app.llm.base import (EmptyResponseError, NotConfiguredError,
                          ProviderError)
from app.llm.util import connect_error, http_error, with_retry

# 推理型模型（deepseek-reasoner、gpt-5 thinking 等）單次摘要可能跑數分鐘，讀取逾時要給足
_CHAT_TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=60.0, pool=15.0)

_MODELS_TTL = 3600.0  # 模型清單記憶體快取 1 小時


@dataclass(frozen=True)
class Vendor:
    """一家 OpenAI 相容供應商的設定。"""
    key: str                       # 路由前綴，例如 "deepseek"
    label: str                     # 顯示名稱
    base_url: str
    config_key: str                # config 裡的金鑰欄位名
    default_model: str
    static_models: tuple[str, ...]  # 抓不到動態清單時的保底
    console_url: str               # 申請金鑰的網址（給設定畫面提示用）


DEEPSEEK = Vendor(
    key="deepseek",
    label="DeepSeek",
    base_url="https://api.deepseek.com/v1",
    config_key="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
    static_models=("deepseek-chat", "deepseek-reasoner"),
    console_url="https://platform.deepseek.com/api_keys",
)

OPENAI = Vendor(
    key="openai",
    label="OpenAI",
    base_url="https://api.openai.com/v1",
    config_key="OPENAI_API_KEY",
    default_model="gpt-5.1",
    static_models=("gpt-5.1", "gpt-5.1-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"),
    console_url="https://platform.openai.com/api-keys",
)

# 多個 API 供應商共用相同的 Chat Completions 實作，不自行推測是否免費。
# 新供應商的模型由金鑰驗證時動態讀取，不使用可能已過期的固定清單。
OPENROUTER = Vendor(
    key="openrouter", label="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    config_key="OPENROUTER_API_KEY",
    default_model="", static_models=(),
    console_url="https://openrouter.ai/settings/keys",
)
GROQ = Vendor(
    key="groq", label="Groq",
    base_url="https://api.groq.com/openai/v1",
    config_key="GROQ_API_KEY",
    default_model="", static_models=(),
    console_url="https://console.groq.com/keys",
)
MISTRAL = Vendor(
    key="mistral", label="Mistral AI",
    base_url="https://api.mistral.ai/v1",
    config_key="MISTRAL_API_KEY",
    default_model="", static_models=(),
    console_url="https://console.mistral.ai/",
)
TOGETHER = Vendor(
    key="together", label="Together AI",
    base_url="https://api.together.ai/v1",
    config_key="TOGETHER_API_KEY",
    default_model="", static_models=(),
    console_url="https://api.together.ai/settings/api-keys",
)

VENDORS: dict[str, Vendor] = {
    v.key: v for v in (DEEPSEEK, OPENAI, OPENROUTER, GROQ, MISTRAL, TOGETHER)
}

# vendor.key -> (抓取時間, 模型清單, 來源)
_models_cache: dict[str, tuple[float, list[str], str]] = {}


def api_key(vendor: Vendor) -> str:
    return (config.get(vendor.config_key) or "").strip()


def is_configured(vendor: Vendor) -> bool:
    return bool(api_key(vendor))


def _headers(vendor: Vendor) -> dict[str, str]:
    key = api_key(vendor)
    if not key:
        raise NotConfiguredError(messages.t("provider.no_key", vendor=vendor.label))
    return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}


def list_models(vendor: Vendor) -> Tuple[list[str], str]:
    """回傳 (模型 id 清單, 來源)。來源為 "live"（動態抓取）或 "static"（保底清單）。

    沒有金鑰時直接回靜態清單——前端仍要能顯示選項，讓使用者知道填了金鑰能用什麼。
    """
    now = time.monotonic()
    hit = _models_cache.get(vendor.key)
    if hit and now - hit[0] < _MODELS_TTL:
        return list(hit[1]), hit[2]

    models, source = list(vendor.static_models), "static"
    if is_configured(vendor):
        try:
            resp = httpx.get(f"{vendor.base_url}/models", headers=_headers(vendor), timeout=10.0)
            resp.raise_for_status()
            ids = [str(m.get("id", "")) for m in (resp.json().get("data") or [])]
            # 只留對話模型：排除 embedding／tts／whisper／dall-e 這類非文字生成端點
            chat = [i for i in ids if i and not any(
                x in i for x in ("embedding", "tts", "whisper", "dall-e", "moderation", "realtime"))]
            if chat:
                chat.sort(key=lambda i: (i != vendor.default_model, i))
                models, source = chat, "live"
        except Exception as e:  # noqa: BLE001
            print(f"[{vendor.label}] 取得模型清單失敗，改用內建靜態清單：{e}", flush=True)

    _models_cache[vendor.key] = (now, list(models), source)
    return list(models), source


def _post_chat(vendor: Vendor, model: str, chat_messages: list[dict],
               max_completion_tokens: int | None = None,
               on_status: Callable[[dict[str, Any]], None] | None = None) -> str:
    """打一次 /chat/completions。Groq 按模型額度限制輸出並配速。"""
    request = {"model": model, "messages": chat_messages}
    if vendor.key == "groq":
        budget = summary_budget(f"groq:{model}")
        if budget:
            max_completion_tokens = min(max_completion_tokens or budget.max_completion_tokens,
                                        budget.max_completion_tokens)
            request["max_completion_tokens"] = max_completion_tokens
            # Groq Qwen 3.8 支援 none（不消耗思考 Token），比較適合精簡 JSON 卡片。
            # GPT-OSS 不支援 none，改用 low；不要把此選項套到其他模型。
            if model == "qwen/qwen3.8-27b":
                request["reasoning_effort"] = "none"
            elif model in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
                request["reasoning_effort"] = "low"
            planned = estimate_tokens(chat_messages) + max_completion_tokens
            if planned > budget.tokens_per_minute:
                err = ProviderError("Groq 輸入加輸出預算超過目前的保守每分鐘限額，請縮短內容。")
                err.public_message = "Groq 單次請求過大；請減少輸入內容或更換較高額度的模型。"
                raise err
            groq_pacer.before(model, planned, on_status=on_status)
    elif max_completion_tokens is not None:
        request["max_completion_tokens"] = max_completion_tokens
    try:
        resp = httpx.post(
            f"{vendor.base_url}/chat/completions",
            headers=_headers(vendor), json=request, timeout=_CHAT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise connect_error(vendor.label, e)

    if vendor.key == "groq":
        groq_pacer.observe(model, resp.headers)
    if resp.status_code >= 400:
        err = http_error(vendor.label, resp.status_code, resp.text)
        if vendor.key == "groq" and resp.status_code == 429:
            if "request too large" in resp.text.lower():
                err.permanent_rate_limit = True
                err.public_message = ("Groq 單次請求超過此模型的速率額度。"
                                      "請縮短片段或選擇更高額度的模型。")
            else:
                err.retry_after = groq_pacer.retry_delay(model, resp.headers)
                err.public_message = ("Groq 暫時達到速率限制，正在依照服務商回傳的"
                                      "重試時間等待。")
        raise err
    try:
        data = resp.json()
    except Exception:
        raise ProviderError(messages.t("provider.not_json", vendor=vendor.label,
                                       detail=resp.text[:200]))

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise ProviderError(messages.t("provider.error", vendor=vendor.label, detail=msg))

    choices = (data or {}).get("choices") or []
    msg = (choices[0].get("message", {}) or {}) if choices else {}
    text = msg.get("content")
    if not text:
        # 推理模型有時把整份輸出放在 reasoning_content，content 留空
        text = msg.get("reasoning_content") or ""
    if not text.strip():
        finish = choices[0].get("finish_reason") if choices else None
        raise EmptyResponseError(messages.t("provider.empty_response", vendor=vendor.label,
                                            reason=f"finish_reason={finish}"))
    return text


def generate_messages(vendor: Vendor, messages: list[dict], system: str = "",
                      model: str = "", tries: int = 3,
                      on_status: Callable[[dict[str, Any]], None] | None = None,
                      max_completion_tokens: int | None = None) -> Tuple[str, str]:
    """多輪對話生成。messages 為 OpenAI 格式的 user/assistant 交錯清單。"""
    model = model or vendor.default_model
    msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)

    def report(event: dict[str, Any]) -> None:
        if on_status:
            on_status({"provider": vendor.key, "model": model, **event})

    text = with_retry(lambda: _post_chat(vendor, model, msgs,
                                        max_completion_tokens=max_completion_tokens,
                                        on_status=report), tries=tries,
                      label=f"{vendor.label}/{model}", on_status=report)
    return text, f"{vendor.label}/{model}"


def generate(vendor: Vendor, prompt: str, system: str = "", model: str = "",
             tries: int = 3,
             on_status: Callable[[dict[str, Any]], None] | None = None,
             max_completion_tokens: int | None = None) -> Tuple[str, str]:
    """單輪文字生成。回傳 (文字, 模型標籤)。"""
    return generate_messages(vendor, [{"role": "user", "content": prompt}],
                             system=system, model=model, tries=tries,
                             on_status=on_status,
                             max_completion_tokens=max_completion_tokens)
