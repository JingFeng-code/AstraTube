"""「問模型」端點：以影片逐字稿為背景知識的自由對話（Gemini 可搭 Google 搜尋）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core import config, messages
from app.core.zh import to_traditional
from app.llm import anthropic_api, gemini, opencode, openai_compat
from app.llm import router as llm_router
from app.llm.base import NotConfiguredError, RefusalError
from app.models.schemas import AskRequest
from app.prompts.ask import ask_system
from app.transcript import cache, captions

router = APIRouter(tags=["ask"])

# 逐字稿太長時只取尾端截斷前的部分，避免撐爆 context（約可容納一小時以上影片）
_MAX_TRANSCRIPT_CHARS = 60_000


def _load_transcript(video_id: Optional[str]) -> Optional[str]:
    """依序從 DeepSRT 快取 → whisper 快取 → 線上字幕撈逐字稿。"""
    if not video_id:
        return None
    for key in (f"deepsrt_v1:{video_id}", video_id):
        hit = cache.get(key)
        if hit and hit[0].strip():
            return hit[0]
    try:
        text, _ = captions.fetch_transcript(video_id)
        return text
    except Exception:  # noqa: BLE001
        return None


def _answer_with(kind: str, model: str, messages: list[dict], system: str) -> tuple[str, str]:
    """對單一供應商發問，回傳 (答案, 模型標籤)。"""
    if kind == llm_router.ANTHROPIC:
        return anthropic_api.generate_messages(messages, system, model=model, tries=2)
    if kind in openai_compat.VENDORS:
        return openai_compat.generate_messages(openai_compat.VENDORS[kind], messages,
                                               system, model=model, tries=2)
    return opencode.generate_messages(messages, system, model=model, tries=2)


@router.post("/ask")
def ask(req: AskRequest) -> dict:
    """回傳 {"answer", "model_used", "searched"}。

    auto 模式與摘要相反：有 Gemini 金鑰就優先（有搜尋工具，能查影片外的資料），
    沒有才依序試其他已設定的供應商，最後才是 OpenCode 免費模型接力。
    """
    transcript = _load_transcript(req.video_id)
    if not transcript:
        raise HTTPException(400, messages.t("ask.no_transcript"))
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:_MAX_TRANSCRIPT_CHARS] + "\n（逐字稿過長，以上為截斷後的前段）"

    language = config.get("OUTPUT_LANGUAGE")
    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.question})

    kind, model = llm_router.parse(req.provider)
    is_auto = kind == llm_router.AUTO
    use_gemini = kind == llm_router.GEMINI or (is_auto and gemini.key_count() > 0)

    if use_gemini:
        try:
            text, label = gemini.generate_chat(messages, ask_system(transcript, True, language))
            # 有掛搜尋工具時 generate_chat 會在標籤後加後綴；後綴文字隨介面語言變，
            # 所以比對「標籤有沒有被加料」而不是比對某個語言的字面值
            return {"answer": to_traditional(text, language), "model_used": label,
                    "searched": label != gemini.LABEL}
        except NotConfiguredError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            if kind == llm_router.GEMINI:
                raise HTTPException(500, messages.t("ask.failed", error=e))
            print(f"[ask] Gemini 失敗，改試其他供應商：{e}", flush=True)

    system = ask_system(transcript, False, language)

    # 嚴格模式只試指定的那一個；自動模式先試已設定金鑰的付費供應商，再退回免費接力
    if not is_auto:
        chain: list[tuple[str, str]] = [(kind, model)]
    else:
        chain = [(k, m) for k, m in llm_router.configured_paid_chain() if k != llm_router.GEMINI]
        chain += [(llm_router.OPENCODE, m) for m in opencode.AUTO_CHAIN]

    last: Exception | None = None
    for k, m in chain:
        try:
            text, label = _answer_with(k, m, messages, system)
            return {"answer": to_traditional(text, language), "model_used": label, "searched": False}
        except RefusalError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[ask] {k}/{m} 失敗，換下一個…：{e}", flush=True)
    raise HTTPException(500, messages.t("ask.failed", error=last))
