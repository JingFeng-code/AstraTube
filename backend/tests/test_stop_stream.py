"""使用者按「停止」：串流被關閉後，排隊中的段落不能再呼叫模型。"""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.api.summarize as summarize_api  # noqa: E402
from app.models.schemas import SummarizeRequest  # noqa: E402


def _patch_slow_segments(started, lock):
    summarize_api.route_content = lambda *_args, **_kwargs: {
        "type": "article", "video_id": None, "title": "測試",
        "text": "素材", "is_chinese": True,
        "has_timestamps": False, "transcript_source": None,
    }
    summarize_api.chunk_content = lambda *_args, **_kwargs: [f"第{i}段" for i in range(10)]
    summarize_api.llm_router.parallel_workers = lambda *_args: 1

    def slow_run(_req, _content, _chunk, index, _multi, on_status=None):
        with lock:
            started.append(index)
        time.sleep(0.2)
        return ({"title": "測試", "cards": [{"heading": f"重點 {index}", "summary": "內容"}]}, "test-model")

    summarize_api._run_segment = slow_run


def test_server_closes_the_stream_when_the_client_goes_away():
    """伺服器發現斷線時會關閉回應的 body；body 要把裡面的 generator 也關掉。"""
    original = (summarize_api.route_content, summarize_api.chunk_content,
                summarize_api._run_segment, summarize_api.llm_router.parallel_workers)
    started, lock = [], threading.Lock()
    try:
        _patch_slow_segments(started, lock)

        async def stop_after_second_segment():
            body = summarize_api.summarize_stream(
                SummarizeRequest(url="https://example.com", provider="auto")).body_iterator
            async for chunk in body:
                text = chunk.decode() if isinstance(chunk, bytes) else chunk
                if any(json.loads(row).get("seg") == 1 and json.loads(row)["type"] == "cards"
                       for row in text.splitlines() if row.strip()):
                    break
            await body.aclose()

        asyncio.run(stop_after_second_segment())
        with lock:
            at_stop = list(started)
        time.sleep(1.5)
        with lock:
            assert started == at_stop and len(started) < 10, (at_stop, started)
    finally:
        (summarize_api.route_content, summarize_api.chunk_content,
         summarize_api._run_segment, summarize_api.llm_router.parallel_workers) = original


def test_waiting_for_a_slow_model_sends_heartbeats():
    """等模型時要定期送空字串，伺服器才有機會在 0.5 秒內發現使用者按了停止。"""
    original = (summarize_api.route_content, summarize_api.chunk_content,
                summarize_api._run_segment, summarize_api.llm_router.parallel_workers)
    try:
        _patch_slow_segments([], threading.Lock())

        def very_slow(_req, _content, _chunk, index, _multi, on_status=None):
            time.sleep(1.2)
            return ({"title": "測試", "cards": []}, "test-model")

        summarize_api._run_segment = very_slow
        summarize_api.chunk_content = lambda *_args, **_kwargs: ["只有一段"]
        rows = list(summarize_api._stream_events(SummarizeRequest(url="https://example.com", provider="auto")))
        assert rows.count("") >= 2, rows
    finally:
        (summarize_api.route_content, summarize_api.chunk_content,
         summarize_api._run_segment, summarize_api.llm_router.parallel_workers) = original


def test_closing_the_stream_cancels_queued_segments():
    original_route = summarize_api.route_content
    original_chunk = summarize_api.chunk_content
    original_run = summarize_api._run_segment
    original_workers = summarize_api.llm_router.parallel_workers
    started = []
    lock = threading.Lock()
    try:
        summarize_api.route_content = lambda *_args, **_kwargs: {
            "type": "article", "video_id": None, "title": "測試",
            "text": "素材", "is_chinese": True,
            "has_timestamps": False, "transcript_source": None,
        }
        summarize_api.chunk_content = lambda *_args, **_kwargs: [f"第{i}段" for i in range(10)]
        # 和本機 Ollama 一樣一次只跑一段：其餘段落都在排隊
        summarize_api.llm_router.parallel_workers = lambda *_args: 1

        def slow_run(_req, _content, _chunk, index, _multi, on_status=None):
            with lock:
                started.append(index)
            time.sleep(0.2)
            return ({"title": "測試", "cards": [{"heading": f"重點 {index}", "summary": "內容"}]}, "test-model")

        summarize_api._run_segment = slow_run
        stream = summarize_api._stream_events(SummarizeRequest(url="https://example.com", provider="auto"))
        for raw in stream:
            if not raw:
                continue  # 心跳
            event = json.loads(raw)
            # 第 1 段出來時，第 2～9 段都已經排進背景工作；這時按停止
            if event["type"] == "cards" and event["seg"] == 1:
                break
        start = time.time()
        stream.close()  # 伺服器偵測到斷線時就是這樣關閉 generator
        assert time.time() - start < 0.5, "關閉時不能等所有段落跑完"
        with lock:
            at_stop = list(started)
        time.sleep(1.5)
        with lock:
            # 停止當下正在跑的那段無法中斷，會做完；但之後不能再開始任何一段
            assert started == at_stop and len(started) < 10, (at_stop, started)
    finally:
        summarize_api.route_content = original_route
        summarize_api.chunk_content = original_chunk
        summarize_api._run_segment = original_run
        summarize_api.llm_router.parallel_workers = original_workers


if __name__ == "__main__":
    test_closing_the_stream_cancels_queued_segments()
    test_server_closes_the_stream_when_the_client_goes_away()
    test_waiting_for_a_slow_model_sends_heartbeats()
    print("停止串流測試通過。")
