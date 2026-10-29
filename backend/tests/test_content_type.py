"""影片類型（content_type）與卡片 actionable 欄位的解析、正規化與向後相容。

重點不是「新欄位有沒有出現」，而是「模型漏填新欄位時，原本的摘要功能不能壞」——
專案沒有 structured output，全靠 prompt 約束＋json_repair，模型漏欄位是常態不是例外。
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.api.summarize as summarize_api  # noqa: E402
from app.core import languages  # noqa: E402
from app.models.schemas import Card, SummarizeRequest  # noqa: E402
from app.prompts.summarize import summarize_prompt  # noqa: E402

LANG = languages.DEFAULT


def test_norm_content_type_always_returns_valid_code():
    """不變式：不論模型吐什麼，輸出一定落在 CONTENT_TYPES 內。"""
    cases = {
        "tutorial": "tutorial", "TUTORIAL": "tutorial", " concept ": "concept",
        "教學操作": "tutorial", "教學": "tutorial", "how-to": "tutorial",
        "觀念分析": "concept", "訪談": "interview", "評測比較": "review", "新聞資訊": "news",
        # 認不出來的一律 other，絕不拋例外擋住整份解析
        "": "other", "隨便亂寫": "other", "video": "other",
    }
    for raw, expected in cases.items():
        got = summarize_api._norm_content_type(raw)
        assert got == expected, f"{raw!r} → {got!r}，預期 {expected!r}"
    for junk in (None, 123, [], {}, True):
        assert summarize_api._norm_content_type(junk) == "other", f"{junk!r} 應退回 other"
    assert set(cases.values()) <= set(summarize_api.CONTENT_TYPES)


def test_norm_bool_handles_string_booleans():
    """模型常把布林寫成字串；認不出來一律 False（寧可漏推薦，不可誤判擋人）。"""
    for truthy in (True, "true", "True", " TRUE ", "yes", "1", "是", 1):
        assert summarize_api._norm_bool(truthy) is True, f"{truthy!r} 應為 True"
    for falsy in (False, "false", "no", "0", "", None, [], "不確定", 0, 2):
        assert summarize_api._norm_bool(falsy) is False, f"{falsy!r} 應為 False"


def test_pick_content_type_majority_vote():
    assert summarize_api._pick_content_type(["tutorial", "tutorial", "concept"]) == "tutorial"
    # other 不參與投票：開場段常被判 other，不該蓋掉主體性質
    assert summarize_api._pick_content_type(["other", "concept", "other"]) == "concept"
    assert summarize_api._pick_content_type(["other", "other"]) == "other"
    assert summarize_api._pick_content_type([]) == "other"
    # 平手取最先出現的（＝影片較前面的段落）
    assert summarize_api._pick_content_type(["review", "news"]) == "review"


def test_legacy_json_without_new_fields_still_parses():
    """向後相容（本檔最重要的一條）：模型完全沒輸出新欄位時，舊有解析行為不得改變。"""
    legacy = json.dumps({"title": "測試影片", "cards": [
        {"heading": "重點一", "summary": "• 內容", "timestamp_seconds": 12},
    ]}, ensure_ascii=False)
    data = summarize_api._parse_cards(legacy, LANG)
    assert data["title"] == "測試影片"
    assert len(data["cards"]) == 1
    assert data["cards"][0]["heading"] == "重點一"
    assert data["cards"][0]["timestamp_seconds"] == 12
    # 缺欄位要被補成安全預設，而不是缺鍵或 None
    assert data["content_type"] == "other"
    assert data["cards"][0]["actionable"] is False

    # pydantic 模型同樣要能吃下沒有新欄位的卡片
    card = Card(**{"heading": "重點一", "summary": "• 內容"})
    assert card.actionable is False and card.action_hint is None


def test_new_fields_parsed_and_normalized():
    raw = json.dumps({"title": "教學影片", "content_type": "教學操作", "cards": [
        {"heading": "設定 webhook", "summary": "• 步驟",
         "actionable": "true", "action_hint": "照著設定一次 webhook"},
        {"heading": "背景介紹", "summary": "• 內容", "actionable": False},
    ]}, ensure_ascii=False)
    data = summarize_api._parse_cards(raw, LANG)
    assert data["content_type"] == "tutorial"
    assert data["cards"][0]["actionable"] is True          # 字串 "true" 要收斂成真布林
    assert data["cards"][0]["action_hint"] == "照著設定一次 webhook"
    assert data["cards"][1]["actionable"] is False


def test_prompt_lists_exactly_the_supported_codes():
    """不變式：prompt 列的代碼與後端枚舉必須一致（改了一邊忘了另一邊，模型會吐無效值）。"""
    prompt = summarize_prompt({"type": "youtube", "text": "[0] 測試素材",
                               "has_timestamps": True}, LANG)
    for code in summarize_api.CONTENT_TYPES:
        assert code in prompt, f"prompt 沒有提到類型代碼 {code}"


async def _events(response):
    items = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        items.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return items


def test_stream_emits_content_type_per_segment_and_final_vote():
    original_route = summarize_api.route_content
    original_chunk = summarize_api.chunk_content
    original_run = summarize_api._run_segment
    original_workers = summarize_api.llm_router.parallel_workers
    try:
        summarize_api.route_content = lambda *_a, **_k: {
            "type": "article", "video_id": None, "title": "測試", "text": "素材",
            "is_chinese": True, "has_timestamps": False, "transcript_source": None,
        }
        summarize_api.chunk_content = lambda *_a, **_k: ["第一段", "第二段"]
        summarize_api.llm_router.parallel_workers = lambda *_a: 1

        # 第一段判 other（開場鋪陳），第二段判 tutorial → 最終應為 tutorial
        types = ["other", "tutorial"]

        def fake_run(_req, _content, _chunk, index, _multi, on_status=None):
            return ({"title": "測試", "content_type": types[index],
                     "cards": [{"heading": f"重點 {index}", "summary": "內容"}]}, "test-model")

        summarize_api._run_segment = fake_run

        response = summarize_api.summarize_stream(SummarizeRequest(url="https://example.com"))
        events = asyncio.run(_events(response))
        assert [e["content_type"] for e in events if e["type"] == "cards"] == ["other", "tutorial"]
        assert events[-1]["type"] == "done" and events[-1]["content_type"] == "tutorial"
    finally:
        summarize_api.route_content = original_route
        summarize_api.chunk_content = original_chunk
        summarize_api._run_segment = original_run
        summarize_api.llm_router.parallel_workers = original_workers


if __name__ == "__main__":
    test_norm_content_type_always_returns_valid_code()
    test_norm_bool_handles_string_booleans()
    test_pick_content_type_majority_vote()
    test_legacy_json_without_new_fields_still_parses()
    test_new_fields_parsed_and_normalized()
    test_prompt_lists_exactly_the_supported_codes()
    test_stream_emits_content_type_per_segment_and_final_vote()
    print("content_type 測試通過。")
