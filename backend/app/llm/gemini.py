"""Gemini 供應商：兩個模型分工，支援多把金鑰輪替。

- MODEL（flash-lite）：卡片摘要、影片轉錄、問答。量大、要便宜。
- MODEL_HEAVY（flash）：實作產出。要一次寫出幾萬字的 HTML，值得用大一級的模型。

用 `-latest` 別名而不是寫死版本號，新模型出來不必改程式碼。代價是官方明說別名可能
指到 preview 版、且配額與功能會隨指向變動（更新前兩週會發信通知）。要完全穩定的人
可以在設定裡填明確版本字串。

除了一般文字生成，另提供 generate_video()：把公開 YouTube 網址直接當影片輸入
（file_data.file_uri），供 DeepSRT 轉錄路徑使用。
"""
import re
import time
from typing import Any, Callable, Optional, Tuple

from google import genai
from google.genai import types

from app.core import config, messages
from app.llm.base import KeyExhaustedError, NotConfiguredError
from app.llm.util import is_transient

MODEL = "gemini-flash-lite-latest"          # 卡片、轉錄、問答
MODEL_HEAVY = "gemini-flash-latest"         # 實作產出
LABEL = MODEL

# 影片攝取很慢，給足逾時（毫秒）
_HTTP_TIMEOUT_MS = 600_000

# 搜尋 grounding 額度全滅後的冷卻期：期間內的問答直接走純對話，不再逐把 key 白試
_SEARCH_COOLDOWN_S = 1800.0
_search_down_until = 0.0

_clients: dict[str, genai.Client] = {}


def _keys() -> list[str]:
    """GEMINI_API_KEY 支援多把：以換行、逗號或空白分隔。"""
    raw = config.get("GEMINI_API_KEY") or ""
    return [k for k in re.split(r"[,\s]+", raw.strip()) if k]


def key_count() -> int:
    """目前可用的 Gemini 金鑰把數。"""
    return len(_keys())


def _client(key: str) -> genai.Client:
    """每把金鑰快取一個 client。"""
    c = _clients.get(key)
    if c is None:
        try:
            c = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=_HTTP_TIMEOUT_MS))
        except Exception:  # SDK 版本較舊不吃 http_options 時退回預設
            c = genai.Client(api_key=key)
        _clients[key] = c
    return c


def _is_auth_error(e: Exception) -> bool:
    """判斷是否為金鑰無效／權限不足（該把 key 直接跳過）。"""
    msg = str(e).lower()
    return ("api key" in msg and ("invalid" in msg or "not valid" in msg)) \
        or "api_key_invalid" in msg or "permission_denied" in msg or "unauthenticated" in msg


def _require_keys() -> list[str]:
    keys = _keys()
    if not keys:
        raise NotConfiguredError(messages.t("provider.no_key", vendor="Gemini"))
    return keys


def _over_keys(run, *, seg: int, label: str, tries: int,
               on_status: Callable[[dict[str, Any]], None] | None = None):
    """依序輪替金鑰執行 run(key)。

    錯誤分流（lessons：不同失敗原因要走不同路）：
    - 金鑰無效 → 標記跳過
    - 額度上限（429/quota）→ 立即換下一把，不對同一把重試（等 0.8 秒再試必然還是 429）
    - 其他暫時性錯誤（503/塞車）→ 同一把退避重試 tries 次，再換下一把
    """
    keys = _require_keys()
    last: Exception | None = None
    dead: set[str] = set()
    for j in range(len(keys)):
        key = keys[(seg + j) % len(keys)]
        if key in dead:
            continue
        for attempt in range(tries):
            if on_status:
                on_status({"state": "request", "provider": "gemini", "model": MODEL,
                           "attempt": attempt + 1, "tries": tries})
            try:
                return run(key)
            except Exception as e:  # noqa: BLE001
                last = e
                if _is_auth_error(e):
                    print("[LLM] 有一把 Gemini key 無效，已跳過。", flush=True)
                    if on_status:
                        on_status({"state": "key_switch", "provider": "gemini", "model": MODEL})
                    dead.add(key)
                    break
                if is_quota_error(e):
                    print(f"[LLM] {label} 第 {j + 1} 把 key 額度上限，立即換下一把。", flush=True)
                    if on_status:
                        on_status({"state": "key_switch", "provider": "gemini", "model": MODEL})
                    break
                if is_transient(e) and attempt < tries - 1:
                    sleep = min(0.8 * (2 ** attempt), 6.0)
                    print(f"[LLM] {label} 暫時性錯誤，{sleep:.1f}s 後重試：{e}", flush=True)
                    if on_status:
                        on_status({"state": "retry_wait", "provider": "gemini", "model": MODEL,
                                   "attempt": attempt + 2, "tries": tries, "delay": sleep})
                    time.sleep(sleep)
                    continue
                if len(keys) > 1 and is_transient(e):
                    break  # 換下一把 key
                raise
    raise last  # type: ignore[misc]


def generate(prompt: str, system: str = "", seg: int = 0,
             on_status: Callable[[dict[str, Any]], None] | None = None,
             model: str | None = None, max_output_tokens: int | None = None) -> Tuple[str, str]:
    """文字生成。回傳 (文字, 模型標籤)。seg 用來讓不同段落錯開使用不同金鑰。

    model 省略時用 flash-lite；實作路徑會傳 MODEL_HEAVY。
    max_output_tokens 供實作使用——一份教學 HTML 約 15-20k tokens，預設值會被截斷。
    """
    use = model or MODEL
    full = f"{system}\n\n{prompt}" if system else prompt
    cfg = types.GenerateContentConfig(max_output_tokens=max_output_tokens) \
        if max_output_tokens else None

    def run(key: str) -> str:
        return _client(key).models.generate_content(
            model=use, contents=full, config=cfg).text

    return _over_keys(run, seg=seg, label=f"Gemini/{use}", tries=3,
                      on_status=on_status), use


def generate_chat(messages: list[dict], system: str = "", seg: int = 0,
                  search: bool = True) -> Tuple[str, str]:
    """多輪對話生成，預設掛 Google 搜尋工具（grounding），供「問模型」使用。

    messages 為 [{"role": "user"|"assistant", "content": str}, ...]。
    搜尋工具不可用時自動退回純對話。回傳 (文字, 模型標籤)。
    """
    contents = [
        types.Content(role=("user" if m["role"] == "user" else "model"),
                      parts=[types.Part(text=m["content"])])
        for m in messages
    ]

    def make_config(use_search: bool):
        kwargs: dict = {}
        if system:
            kwargs["system_instruction"] = system
        if use_search:
            kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        return types.GenerateContentConfig(**kwargs) if kwargs else None

    def run_with(use_search: bool):
        def run(key: str) -> str:
            resp = _client(key).models.generate_content(
                model=MODEL, contents=contents, config=make_config(use_search))
            return resp.text or ""
        return _over_keys(run, seg=seg, label=f"Gemini/{MODEL}/chat", tries=2)

    global _search_down_until
    if search and time.time() < _search_down_until:
        search = False  # 搜尋工具額度冷卻中，直接走純對話省時間
    if search:
        try:
            return run_with(True), LABEL + messages.t("gemini.search_suffix")
        except Exception as e:  # noqa: BLE001
            if is_quota_error(e):
                _search_down_until = time.time() + _SEARCH_COOLDOWN_S
                print(f"[LLM] 搜尋工具額度全數上限，{int(_SEARCH_COOLDOWN_S / 60)} 分鐘內改走純對話。", flush=True)
            else:
                print(f"[LLM] Gemini 搜尋工具失敗，退回純對話：{e}", flush=True)
    return run_with(False), LABEL


def is_quota_error(e: Exception) -> bool:
    """判斷是否為額度／流量上限錯誤（換金鑰有救，但不代表金鑰壞掉）。"""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    try:
        if int(code) == 429:
            return True
    except (TypeError, ValueError):
        pass
    msg = str(e).lower()
    return "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg or "429" in msg


def generate_video(youtube_url: str, directive: str, *,
                   start_offset: Optional[str] = None,
                   end_offset: Optional[str] = None,
                   key_index: int = 0) -> str:
    """把公開 YouTube 網址當影片輸入送給 Gemini（指定第 key_index 把金鑰），回傳純文字輸出。

    start_offset／end_offset 形如 "125s"，用來補跑影片的某個時間範圍。
    額度耗盡或金鑰無效時拋 KeyExhaustedError，讓呼叫端換下一把金鑰接續補跑。
    """
    keys = _require_keys()
    key = keys[key_index % len(keys)]

    def run() -> str:
        part = types.Part(file_data=types.FileData(file_uri=youtube_url))
        if start_offset or end_offset:
            part.video_metadata = types.VideoMetadata(
                start_offset=start_offset, end_offset=end_offset,
            )
        contents = types.Content(parts=[part, types.Part(text=directive)])
        resp = _client(key).models.generate_content(model=MODEL, contents=contents)
        return resp.text or ""

    for attempt in range(2):
        try:
            return run()
        except Exception as e:  # noqa: BLE001
            if is_quota_error(e) or _is_auth_error(e):
                raise KeyExhaustedError(str(e))
            if attempt == 0 and is_transient(e):
                print(f"[LLM] Gemini/{MODEL}/video 暫時性錯誤，1.5s 後重試：{e}", flush=True)
                time.sleep(1.5)
                continue
            raise
    raise KeyExhaustedError(messages.t("gemini.video_failed"))
