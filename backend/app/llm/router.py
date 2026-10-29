"""文字生成的供應商路由：解析 provider 字串並決定要不要跨供應商備援。

provider 格式：
  - None / "" / "auto"        自動：先免費模型接力，全滅才落到已設定金鑰的付費供應商
  - "gemini"                  嚴格：只用 gemini-flash-lite-latest
  - "opencode:<model_id>"     嚴格：只用該 OpenCode 免費模型
  - "deepseek:<model_id>"     嚴格：只用該 DeepSeek 模型
  - "openai:<model_id>"       嚴格：只用該 OpenAI 模型
  - "anthropic:<model_id>"    嚴格：只用該 Claude 模型
"""
from typing import Any, Callable, Optional, Tuple

from app.core import messages
from app.llm import anthropic_api, gemini, opencode, openai_compat
from app.llm.base import NotConfiguredError, RefusalError

AUTO = "auto"
GEMINI = "gemini"
OPENCODE = "opencode"
DEEPSEEK = "deepseek"
OPENAI = "openai"
ANTHROPIC = "anthropic"

# 帶 "<kind>:<model>" 前綴的供應商
_PREFIXED = (OPENCODE, DEEPSEEK, OPENAI, ANTHROPIC)

# 自動模式的首選（免費、不需金鑰）
DEFAULT_AUTO_MODEL = opencode.DEFAULT_FREE_MODEL


def parse(provider: Optional[str]) -> Tuple[str, str]:
    """把 provider 字串解析成 (種類, 模型 id)。"""
    p = (provider or "").strip()
    if not p or p == AUTO:
        return AUTO, DEFAULT_AUTO_MODEL
    for kind in _PREFIXED:
        if p.startswith(f"{kind}:"):
            model = p[len(kind) + 1:].strip()
            return kind, (model or _default_model(kind))
    if p == GEMINI:
        return GEMINI, gemini.MODEL
    # 未知字串一律當自動，避免舊設定（如已下架的模型 id）讓使用者卡住
    print(f"[LLM] 不認得的 provider「{p}」，改用自動模式。", flush=True)
    return AUTO, DEFAULT_AUTO_MODEL


def _default_model(kind: str) -> str:
    if kind == ANTHROPIC:
        return anthropic_api.DEFAULT_MODEL
    if kind in openai_compat.VENDORS:
        return openai_compat.VENDORS[kind].default_model
    return DEFAULT_AUTO_MODEL


def _call(kind: str, model: str, prompt: str, system: str, seg: int,
          on_status: Callable[[dict[str, Any]], None] | None) -> Tuple[str, str]:
    """對單一供應商發一次生成請求。"""
    if kind == GEMINI:
        return gemini.generate(prompt, system, seg=seg, on_status=on_status)
    if kind == ANTHROPIC:
        return anthropic_api.generate(prompt, system, model=model, on_status=on_status)
    if kind in openai_compat.VENDORS:
        return openai_compat.generate(openai_compat.VENDORS[kind], prompt, system,
                                      model=model, on_status=on_status)
    return opencode.generate(prompt, system, model=model, seg=seg, on_status=on_status)


def configured_paid_chain() -> list[Tuple[str, str]]:
    """自動模式的付費備援順序：只列出「已填金鑰」的供應商。

    順序依「摘要品質／額度寬鬆度」排：Gemini 有免費額度排最前，其餘依成本遞增。
    """
    chain: list[Tuple[str, str]] = []
    if gemini.key_count() > 0:
        chain.append((GEMINI, gemini.MODEL))
    for kind in (DEEPSEEK, OPENAI):
        vendor = openai_compat.VENDORS[kind]
        if openai_compat.is_configured(vendor):
            chain.append((kind, vendor.default_model))
    if anthropic_api.is_configured():
        chain.append((ANTHROPIC, anthropic_api.DEFAULT_MODEL))
    return chain


def generate(provider: Optional[str], prompt: str, system: str = "", seg: int = 0,
             on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[str, str]:
    """回傳 (文字, 實際產生答案的模型標籤)。seg 是段落索引，用來錯開 Gemini 金鑰。"""
    kind, model = parse(provider)

    if kind != AUTO:
        return _call(kind, model, prompt, system, seg, on_status)

    # 自動模式：先跑 OpenCode 免費模型接力（單模型重試 2 次就換下一個），
    # 整條鏈耗盡才依序備援到有金鑰的付費供應商。
    last: Exception | None = None
    for index, m in enumerate(opencode.AUTO_CHAIN):
        if index and on_status:
            on_status({"state": "model_switch", "provider": OPENCODE, "model": m})
        try:
            return opencode.generate(prompt, system, model=m, seg=seg, tries=2,
                                     on_status=on_status)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[LLM] OpenCode/{m} 失敗，換下一個免費模型…：{e}", flush=True)

    paid = configured_paid_chain()
    if not paid:
        raise last if last else RuntimeError(messages.t("llm.all_free_failed"))

    for kind_p, model_p in paid:
        print(f"[LLM] OpenCode 接力鏈耗盡，自動備援到 {kind_p}/{model_p}…", flush=True)
        if on_status:
            on_status({"state": "model_switch", "provider": kind_p, "model": model_p})
        try:
            return _call(kind_p, model_p, prompt, system, seg, on_status)
        except RefusalError:
            raise  # 內容被婉拒，換供應商也是同一份 prompt，直接讓使用者知道
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[LLM] {kind_p}/{model_p} 失敗，換下一個供應商…：{e}", flush=True)
    raise last  # type: ignore[misc]


def parallel_workers(provider: Optional[str], chunks: int) -> int:
    """依供應商決定分段並行度。

    Gemini 一把金鑰一個 worker（額度分開）；其餘供應商併發上限 4——
    免費模型單段實測約 40-60 秒，併發不足時長影片要跑好幾批，
    但再往上拉容易撞到未公開的免費層／低方案併發限制。
    """
    kind, _ = parse(provider)
    if kind == GEMINI:
        return max(1, min(gemini.key_count() or 1, chunks, 6))
    return max(1, min(4, chunks))


__all__ = ["AUTO", "GEMINI", "OPENCODE", "DEEPSEEK", "OPENAI", "ANTHROPIC",
           "DEFAULT_AUTO_MODEL", "NotConfiguredError", "RefusalError",
           "generate", "parse", "parallel_workers", "configured_paid_chain"]
