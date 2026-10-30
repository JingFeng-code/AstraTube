"""OpenCode Zen 供應商（OpenAI-compatible）。

免費模型實測不需要金鑰；有設定 OPENCODE_API_KEY 才帶 Authorization header。
"""
import time
from typing import Any, Callable, Tuple

import httpx

from app.core import config, messages
from app.llm.base import EmptyResponseError, ProviderError
from app.llm.util import connect_error, http_error, response_error, with_retry

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

# 不適合摘要的免費模型（見上方說明）：接力時跳過，只留給使用者在開發者模式手動選
_NOT_FOR_RELAY = frozenset({
    "laguna-s-2.1-free", "ling-3.0-flash-free", "ling-3.0-tiny-free", "north-mini-code-free",
})

_MODELS_TTL = 3600.0  # 模型清單記憶體快取 1 小時
_models_cache: tuple[float, list[str], str] | None = None

# 免費模型會無預警下架或暫停（例如 HTTP 400「Model is unavailable」）。
# 回報「模型不可用」的模型先排到接力鏈最後，10 分鐘後再給它機會。
_UNAVAILABLE_TTL = 600.0
_unavailable: dict[str, float] = {}

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


def _says_model_unavailable(body: str) -> bool:
    """回應是否表示「這個模型不能用」（下架、暫停、不存在），而不是請求本身有誤。"""
    text = body.lower()
    return "model" in text and any(h in text for h in (
        "unavailable", "not found", "does not exist", "not supported", "disabled"))


def _post_chat(model: str, chat_messages: list[dict]) -> str:
    """打一次 /chat/completions，回傳助手訊息內容。"""
    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers=_headers(),
            json={"model": model, "messages": chat_messages},
            timeout=_CHAT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise connect_error("OpenCode", e)

    if resp.status_code >= 400:
        error = http_error("OpenCode", resp.status_code, resp.text)
        if resp.status_code in (400, 404) and _says_model_unavailable(resp.text):
            _unavailable[model] = time.monotonic()
            error.model_unavailable = True
        raise error
    try:
        data = resp.json()
    except Exception:
        raise response_error("OpenCode", messages.t("provider.not_json", vendor="OpenCode",
                                                    detail=resp.text[:200]))

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise response_error("OpenCode", messages.t("provider.error", vendor="OpenCode", detail=msg))

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


def free_chain() -> list[str]:
    """免費模型的接力順序：AUTO_CHAIN 中目前仍上架的優先，其餘上架、適合摘要的免費模型接在後面
    （例如 OpenCode 新上架的免費模型），讓預設模型下架時仍有模型可用。

    最近回報「模型不可用」的移到最後，避免每一段都先撞同一個已下架的模型。
    """
    live, source = list_free_models()
    if source == "live":
        chain = [m for m in AUTO_CHAIN if m in live] + [
            m for m in live if m not in AUTO_CHAIN and m not in _NOT_FOR_RELAY]
    else:
        chain = list(AUTO_CHAIN)
    now = time.monotonic()
    recent = {m for m, at in _unavailable.items() if now - at < _UNAVAILABLE_TTL}
    return [m for m in chain if m not in recent] + [m for m in chain if m in recent]


def generate_free(chat_messages: list[dict], system: str = "",
                  on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """只在 OpenCode 免費模型之間接力，絕不改用付費供應商。回傳 (文字, 實際使用的模型)。

    單一模型下架或忙碌時換下一個；全部失敗才拋錯，訊息列出試過的模型與最後的原因。
    """
    tried: list[str] = []
    last: Exception | None = None
    for index, model in enumerate(free_chain()):
        if index and on_status:
            on_status({"state": "model_switch", "provider": "opencode", "model": model})
        try:
            return generate_messages(chat_messages, system=system, model=model, tries=2,
                                     on_status=on_status)
        except Exception as e:  # noqa: BLE001
            tried.append(model)
            last = e
            print(f"[OpenCode] {model} 失敗，換下一個免費模型…：{e}", flush=True)
    summary = messages.t("llm.free_chain_failed", models="、".join(tried) or "-")
    error = ProviderError(f"{summary} {last}" if last else summary)
    # 字幕翻譯等端點只顯示公開訊息：不含上游回應內容
    public = getattr(last, "public_message", "")
    error.public_message = f"{summary} {public}".strip()
    raise error


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
