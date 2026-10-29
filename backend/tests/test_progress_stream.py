"""確認摘要串流先回報來源階段，並以實際片段完成事件推進。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.api.summarize as summarize_api  # noqa: E402
from app.models.schemas import SummarizeRequest  # noqa: E402


async def _events(response):
    items = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        items.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return items


def test_stream_progress_uses_real_work_units():
    original_route = summarize_api.route_content
    original_chunk = summarize_api.chunk_content
    original_run = summarize_api._run_segment
    original_workers = summarize_api.llm_router.parallel_workers
    try:
        summarize_api.route_content = lambda *_args, **_kwargs: {
            "type": "article", "video_id": None, "title": "測試",
            "text": "素材", "is_chinese": True,
            "has_timestamps": False, "transcript_source": None,
        }
        summarize_api.chunk_content = lambda *_args, **_kwargs: ["第一段", "第二段"]
        summarize_api.llm_router.parallel_workers = lambda *_args: 1
        starts = []

        def fake_run(_req, _content, _chunk, index, _multi, on_status=None):
            starts.append(index)
            if on_status:
                on_status({"state": "request", "provider": "opencode",
                           "model": "test-model", "attempt": 1, "tries": 3})
            return ({"title": "測試", "cards": [
                {"heading": f"重點 {index + 1}", "summary": "內容"}
            ]}, "test-model")

        summarize_api._run_segment = fake_run

        response = summarize_api.summarize_stream(SummarizeRequest(url="https://example.com"))
        events = asyncio.run(_events(response))
        assert events[0] == {"type": "progress", "stage": "source", "completed": 0, "total": 0}
        assert events[1]["type"] == "meta" and events[1]["segments"] == 2
        assert starts == [0, 1]
        assert [(event["seg"], event["state"]) for event in events
                if event["type"] == "segment_status"] == [(0, "request"), (1, "request")]
        assert [event["seg"] for event in events if event["type"] == "cards"] == [0, 1]
        assert events[-1]["type"] == "done" and events[-1]["total_cards"] == 2
    finally:
        summarize_api.route_content = original_route
        summarize_api.chunk_content = original_chunk
        summarize_api._run_segment = original_run
        summarize_api.llm_router.parallel_workers = original_workers


if __name__ == "__main__":
    test_stream_progress_uses_real_work_units()
    print("進度串流測試通過。")
