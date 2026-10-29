"""摘要相關端點：/summarize（一次回全部）、/summarize_stream（NDJSON 串流）、/deepdive。"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from typing import Any, Callable, Iterator, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from json_repair import repair_json

from app.core import config, messages
from app.core.zh import to_traditional
from app.llm import router as llm_router
from app.models.schemas import DeepDiveRequest, SummarizeRequest
from app.prompts.summarize import (deepdive_prompt, deepdive_system,
                                   summarize_prompt, summarize_system)
from app.services.chunker import chunk_content
from app.transcript.router import Content, route_content

router = APIRouter(tags=["summarize"])


# 模型自己寫的中文欄位要正規化成繁體；transcript_highlight 是逐字引用，保留原文才忠實
_ZH_FIELDS = ("heading", "summary", "visual", "translation", "action_hint")

# 影片類型代碼。決定「下一步」走哪一條 track，前端據此換按鈕文案與 brief 模板
CONTENT_TYPES = ("tutorial", "concept", "interview", "review", "news", "other")

# 模型不一定聽話輸出英文代碼；中文說法映射回代碼，比直接退回 other 更保住資訊
_CT_ALIASES = {
    "教學操作": "tutorial", "教學": "tutorial", "操作": "tutorial", "howto": "tutorial",
    "how-to": "tutorial", "教程": "tutorial",
    "觀念分析": "concept", "觀念": "concept", "分析": "concept", "概念": "concept",
    "訪談對談": "interview", "訪談": "interview", "對談": "interview", "podcast": "interview",
    "評測比較": "review", "評測": "review", "比較": "review", "comparison": "review",
    "新聞資訊": "news", "新聞": "news", "資訊": "news",
}

_TRUTHY = {"true", "yes", "1", "是", "真"}


def _norm_content_type(value: Any) -> str:
    """把模型輸出的類型正規化成固定代碼；認不出來一律 other（絕不讓它擋住解析）。"""
    if not isinstance(value, str):
        return "other"
    v = value.strip()
    if v.lower() in CONTENT_TYPES:
        return v.lower()
    return _CT_ALIASES.get(v, _CT_ALIASES.get(v.lower(), "other"))


def _norm_bool(value: Any) -> bool:
    """模型常把布林寫成字串（"true"／"是"）；一律收斂成真布林，認不出來當 False。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return value == 1


def _pick_content_type(values: list[str]) -> str:
    """多段影片各段可能判成不同類型：取多數決（忽略 other），平手取最先出現的。"""
    votes = [v for v in values if v and v != "other"]
    if not votes:
        return "other"
    return max(dict.fromkeys(votes), key=lambda v: (votes.count(v), -votes.index(v)))


def _parse_cards(raw: str, language: str) -> dict:
    """把模型輸出（可能包 markdown 代碼框、可能有小瑕疵）解析成卡片 JSON。

    輸出語言是繁體中文時順手做簡繁正規化（中國廠商的模型常無視 prompt 吐簡體）；
    其他語言不套這層轉換。content_type／actionable 是後加的欄位，模型漏填是常態，
    一律走正規化補預設值，絕不因為缺欄位就讓整份摘要失敗。
    """
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(repair_json(raw))
    if isinstance(data, dict):
        data["title"] = to_traditional(data.get("title"), language)
        data["content_type"] = _norm_content_type(data.get("content_type"))
        for card in data.get("cards") or []:
            for field in _ZH_FIELDS:
                if card.get(field):
                    card[field] = to_traditional(card[field], language)
            card["actionable"] = _norm_bool(card.get("actionable"))
    return data


def _prepare(req: SummarizeRequest) -> Tuple[Content, list[str], bool]:
    """擷取內容並切段，回傳 (內容, 片段列表, 是否多段)。"""
    try:
        content = route_content(req.url, deep_visual=req.deep_visual)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, messages.t("summarize.fetch_failed", error=e))

    has_ts = content.get("has_timestamps") or content["type"] == "youtube"
    chunks = chunk_content(content["text"], bool(has_ts))
    return content, chunks, len(chunks) > 1


_TS_LINE = re.compile(r"^\[(\d+)\]", re.M)
_VISUAL_LINE = re.compile(r"^【畫面 (\d+):(\d{2})】")


def _last_ts(text: str) -> int:
    """素材中最後（最大）的口說時間戳秒數；沒有時間戳回 0。"""
    ts = _TS_LINE.findall(text)
    return max(map(int, ts)) if ts else 0


def _text_after(text: str, sec: int) -> str:
    """取素材中時間戳 >= sec 之後的行（含其間的【畫面】筆記行）。"""
    out: list[str] = []
    cur = -1
    for line in text.splitlines():
        m = _TS_LINE.match(line)
        if m:
            cur = int(m.group(1))
        else:
            v = _VISUAL_LINE.match(line)
            if v:
                cur = int(v.group(1)) * 60 + int(v.group(2))
        if cur >= sec:
            out.append(line)
    return "\n".join(out)


def _audit_coverage(req: SummarizeRequest, content: Content, chunk: str,
                    index: int, data: dict, model_used: str, language: str,
                    on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[dict, str]:
    """覆蓋率稽核：卡片沒蓋到素材尾端就對缺的後段補做（最多 2 輪）。

    防兩種病：模型只整理前半就自報完成（偷懶）、輸出被截斷後 json_repair 靜默閉合。
    """
    cards = data.get("cards") or []
    target = _last_ts(chunk)
    if not target or not cards:
        return data, model_used

    # 只在「明顯偷懶」時補做：容忍尾端 90 秒（最後一張卡的時間戳是起點，本來就不會貼齊尾端），
    # 短段落改用比例容忍。補做一輪就好——每輪都是一次完整的 LLM 呼叫，會直接翻倍等待時間。
    threshold = max(target - 90, target * 0.75)
    labels = [model_used]
    for _ in range(1):
        covered = max((c.get("timestamp_seconds") or 0) for c in cards)
        if covered >= threshold:
            break
        remaining = _text_after(chunk, covered + 1)
        if len(remaining) < 200:
            break
        print(f"[summarize] 覆蓋率不足（卡片到 {covered}s／素材到 {target}s），補做後段…", flush=True)
        if on_status:
            on_status({"state": "coverage"})
        seg: dict[str, Any] = {**content, "text": remaining,
                               "is_segment": True, "is_continuation": True}
        try:
            def report(event: dict[str, Any]) -> None:
                if on_status:
                    on_status({**event, "phase": "coverage"})

            raw, label = llm_router.generate(req.provider, summarize_prompt(seg, language),
                                             summarize_system(language), seg=index,
                                             on_status=report)
            more = _parse_cards(raw, language)
        except Exception as e:  # noqa: BLE001
            print(f"[summarize] 補做失敗，保留現有卡片：{e}", flush=True)
            break
        new_cards = more.get("cards") or []
        if not new_cards:
            break
        cards = cards + new_cards
        if label and label not in labels:
            labels.append(label)

    data["cards"] = cards
    return data, "、".join(labels)


def _run_segment(req: SummarizeRequest, content: Content, chunk: str,
                 index: int, multi: bool,
                 on_status: Callable[[dict[str, Any]], None] | None = None) -> Tuple[dict, str]:
    """對單一片段做摘要（含覆蓋率稽核），回傳 (卡片 JSON, 模型標籤)。"""
    t0 = time.time()
    language = config.get("OUTPUT_LANGUAGE")
    seg: dict[str, Any] = {**content, "text": chunk, "is_segment": multi}
    raw, model_used = llm_router.generate(req.provider, summarize_prompt(seg, language),
                                          summarize_system(language), seg=index,
                                          on_status=on_status)
    t_gen = time.time() - t0
    data, label = _audit_coverage(req, content, chunk, index, _parse_cards(raw, language),
                                  model_used, language, on_status=on_status)
    print(f"[summarize] 片段 {index + 1} 完成：{len(data.get('cards') or [])} 張卡，"
          f"生成 {t_gen:.1f}s／總計 {time.time() - t0:.1f}s（{label}）", flush=True)
    return data, label


@router.post("/summarize")
def summarize(req: SummarizeRequest) -> dict:
    """一次回傳全部卡片（不串流）。單一片段失敗會跳過，全部失敗才報錯。"""
    content, chunks, multi = _prepare(req)

    all_cards: list[dict] = []
    title: str | None = None
    models_used: list[str] = []
    content_types: list[str] = []
    failed = 0

    for i, chunk in enumerate(chunks):
        try:
            data, model_used = _run_segment(req, content, chunk, i, multi)
        except RuntimeError as e:  # 金鑰未設定等致命錯誤
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[summarize] 片段 {i + 1}/{len(chunks)} 失敗，已跳過：{e}", flush=True)
            continue
        if title is None:
            title = data.get("title")
        all_cards.extend(data.get("cards", []))
        content_types.append(data.get("content_type") or "other")
        if model_used and model_used not in models_used:
            models_used.append(model_used)

    if not all_cards:
        raise HTTPException(500, messages.t("summarize.all_segments_failed"))

    return {"title": title or messages.t("summarize.untitled"),
            "source_type": content["type"],
            "source_url": req.url, "youtube_video_id": content.get("video_id"),
            "transcript_source": content.get("transcript_source"),
            "content_type": _pick_content_type(content_types),
            "cards": all_cards, "model_used": "、".join(models_used),
            "segments": len(chunks), "failed_segments": failed}


@router.post("/summarize_stream")
def summarize_stream(req: SummarizeRequest) -> StreamingResponse:
    """串流版摘要（NDJSON，每行一個事件）。

    事件：progress → meta → title → cards（每段一批）→ done；單段失敗發
    seg_error 但不中斷，致命錯誤發 fatal 後結束。內容擷取移入 generator，
    讓前端能在字幕與文章擷取開始時立即顯示真實工作階段。
    """
    def line(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False) + "\n"

    def gen() -> Iterator[str]:
        yield line({"type": "progress", "stage": "source", "completed": 0, "total": 0})
        try:
            content = route_content(req.url, deep_visual=req.deep_visual)
            has_ts = content.get("has_timestamps") or content["type"] == "youtube"
            chunks = chunk_content(content["text"], bool(has_ts))
        except ValueError as e:
            yield line({"type": "fatal", "error": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            yield line({"type": "fatal",
                        "error": messages.t("summarize.fetch_failed", error=e)})
            return

        multi = len(chunks) > 1
        workers = llm_router.parallel_workers(req.provider, len(chunks))
        yield line({"type": "meta", "source_type": content["type"], "source_url": req.url,
                    "youtube_video_id": content.get("video_id"),
                    "transcript_source": content.get("transcript_source"),
                    "segments": len(chunks), "workers": workers})
        title: str | None = None
        models_used: list[str] = []
        content_types: list[str] = []   # 依段落順序 append（emit 是嚴格時間序），供多數決
        failed = total = 0
        status_events = [Queue() for _ in chunks]
        fatal_error: str | None = None

        def report(i: int):
            def put(event: dict[str, Any]) -> None:
                status_events[i].put({"type": "segment_status", "seg": i, **event})
            return put

        def wait_and_emit(i: int, future) -> Iterator[str]:
            nonlocal title, failed, total, fatal_error
            events = status_events[i]
            # API 等待期間持續把 worker 的「請求／重試／換模型」狀態送到前端。
            while not future.done():
                try:
                    yield line(events.get(timeout=0.5))
                except Empty:
                    continue
            while True:
                try:
                    yield line(events.get_nowait())
                except Empty:
                    break
            try:
                data, model_used = future.result()
            except RuntimeError as e:
                fatal_error = str(e)
                yield line({"type": "fatal", "error": fatal_error})
                return
            except Exception as e:  # noqa: BLE001
                failed += 1
                yield line({"type": "seg_error", "seg": i, "error": str(e)[:200]})
                return
            if title is None and data.get("title"):
                title = data.get("title")
                yield line({"type": "title", "title": title})
            cards = data.get("cards", [])
            total += len(cards)
            if model_used and model_used not in models_used:
                models_used.append(model_used)
            ctype = data.get("content_type") or "other"
            content_types.append(ctype)
            # 每段都帶：前端第一段就能顯示「下一步」入口，done 事件再用多數決校正
            yield line({"type": "cards", "seg": i, "cards": cards, "model": model_used,
                        "content_type": ctype})

        with ThreadPoolExecutor(max_workers=workers) as ex:
            # 第一段優先：不和後段搶免費 API；完成並送到前端後，才平行跑剩餘段落。
            first = ex.submit(_run_segment, req, content, chunks[0], 0, multi, report(0))
            yield from wait_and_emit(0, first)
            if fatal_error:
                return

            futs = [ex.submit(_run_segment, req, content, c, i, multi, report(i))
                    for i, c in enumerate(chunks[1:], start=1)]
            for i, f in enumerate(futs, start=1):  # 嚴格依影片時間順序輸出
                yield from wait_and_emit(i, f)
                if fatal_error:
                    return
        yield line({"type": "done", "title": title or messages.t("summarize.untitled"),
                    "model_used": "、".join(models_used), "segments": len(chunks),
                    "content_type": _pick_content_type(content_types),
                    "failed_segments": failed, "total_cards": total})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/deepdive")
def deepdive(req: DeepDiveRequest) -> dict:
    """對單一張卡片做深度解析。"""
    language = config.get("OUTPUT_LANGUAGE")
    try:
        text, model_used = llm_router.generate(
            req.provider,
            deepdive_prompt(req.source_title, req.card.model_dump(), language),
            deepdive_system(language))
        return {"content": to_traditional(text, language), "model_used": model_used}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, messages.t("summarize.deepdive_failed", error=e))
