"""陪看模式：不需要 Windows 擷取元件、語音模型或 Ollama 的 mock 測試。"""
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from fastapi import HTTPException

from app.api import ask as ask_api
from app.api import subtitles, watch as watch_api
from app.transcript import imported_subtitles as imported
from app.transcript import watch_along as watch
from app.transcript.router import route_content

YOUTUBE = "dQw4w9WgXcQ"
REGION = {"x": 10, "y": 20, "width": 640, "height": 360, "dpr": 1.5}


def test_video_time_follows_youtube_heartbeats_and_falls_back_for_bilibili():
    beats = [(100.0, 30.0), (110.0, 200.0)]  # 第二次回報代表使用者拖曳到 200 秒
    assert watch.clock_time(105.0, beats, 90.0, 0) == 35.0
    assert watch.clock_time(112.5, beats, 90.0, 0) == 202.5
    assert watch.clock_time(99.0, beats, 90.0, 0) == 29.0
    # Bilibili 沒有進度回報：從開始陪看的時間往後算
    assert watch.clock_time(130.0, [], 100.0, 12.0) == 42.0
    assert watch.clock_time(90.0, [], 100.0, 0) == 0.0


def test_crop_box_maps_page_pixels_to_the_captured_frame():
    from app.capture import window_capture as wc
    # 內容區在擷取畫面的 (8, 31)，擷取畫面與外框同大小
    assert wc.crop_box(REGION, (8, 31, 1936, 1100), (1936, 1100)) == (23, 61, 983, 601)
    # 擷取畫面被縮小一半時，裁切範圍跟著縮
    assert wc.crop_box(REGION, (8, 31, 1936, 1100), (968, 550)) == (11, 30, 491, 300)
    # 播放器整個在畫面外就不擷取
    assert wc.crop_box({**REGION, "x": 5000}, (0, 0, 1000, 800), (1000, 800)) is None


def test_frame_change_detection():
    still = np.zeros((36, 64), dtype=np.uint8)
    assert watch.frame_changed(None, still) == 255.0
    assert watch.frame_changed(still, still) == 0.0
    assert watch.frame_changed(still, still + 40) == 40.0


def test_transcript_interleaves_visual_notes_and_labels_the_source():
    cues = [{"start": 5.2, "end": 7, "text": "大家好"}, {"start": 70.4, "end": 72, "text": "請看這裡"}]
    visuals = [{"t": 69.9, "text": "投影片：三個階段"}]
    text = imported.transcript_from_cues(cues, visuals)
    assert text.splitlines() == ["[5] 大家好", "【畫面 1:09】投影片：三個階段", "[70] 請看這裡"]
    assert imported.source_label({"format": "watch"}) == "watch_along"
    assert imported.source_label({"format": "asr"}) == "local_speech"
    assert imported.source_label({"format": "srt"}) == "imported_subtitles"


class FakeAudio:
    """每次讀取回傳 0.2 秒的聲音，直到用完。"""
    def __init__(self, seconds=3):
        self.left = int(seconds * 5)
        self.closed = False

    def read(self, _timeout):
        time.sleep(0.01)
        if self.left <= 0:
            return b""
        self.left -= 1
        return (np.ones(3200, dtype=np.int16) * 1000).tobytes()

    def close(self):
        self.closed = True


class FakeVad:
    """收到第一段聲音就吐出一段語音。"""
    def __init__(self):
        self.ready = []
        self.fed = 0

    def accept_waveform(self, samples):
        self.fed += 1
        if self.fed == 1:
            self.ready.append(type("Seg", (), {"start": 0, "samples": np.zeros(16000, dtype=np.float32)})())

    def empty(self):
        return not self.ready

    @property
    def front(self):
        return self.ready[0]

    def pop(self):
        self.ready.pop(0)

    def flush(self):
        pass


class FakeFrames:
    def __init__(self, pid, on_frame):
        self.on_frame = on_frame
        self.closed = False
        threading.Thread(target=self._feed, daemon=True).start()

    def _feed(self):
        for shade in (0, 200):
            if self.closed:
                return
            self.on_frame(np.full((800, 1200, 3), shade, dtype=np.uint8))
            time.sleep(0.05)

    def __call__(self, region, width, height):
        return (0, 0, 640, 360)

    def close(self):
        self.closed = True


def run_session(models, describe):
    audio = FakeAudio()
    with patch.object(watch.local_speech, "new_vad", return_value=(FakeVad(), 512)), \
         patch.object(watch, "_MIN_GAP", 0), patch.object(watch, "_FRAME_INTERVAL", 0):
        status = watch.start("youtube", YOUTUBE, 1, REGION, 0, pid=1234, models=models,
                             audio_factory=lambda pid: audio, frames_factory=FakeFrames,
                             recognize=lambda samples: (list("大家好。"), [0.0, 0.2, 0.4, 0.6]),
                             describe=describe)
        watch.heartbeat(0.0)
        time.sleep(0.6)
        result = watch.finish()
    return status, result, audio


def test_session_records_speech_and_frames_then_saves_for_analysis():
    seen = []

    def describe(model, picture):
        seen.append((model, picture.size))
        return "投影片：三個階段"

    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}):
        status, result, audio = run_session(["qwen3.5:latest"], describe)
        assert status["vision_model"] == "qwen3.5:latest" and status["state"] == "running"
        assert result["state"] == "done" and result["cue_count"] >= 1 and audio.closed
        assert seen and seen[0][0] == "qwen3.5:latest"
        stored = imported.load("youtube", YOUTUBE)
        assert stored["format"] == "watch" and stored["visuals"][0]["text"] == "投影片：三個階段"
        # 之後的分析、問答、字幕面板都用這份資料，不再連 YouTube
        with patch("app.transcript.router.captions.fetch_transcript", side_effect=AssertionError("no network")):
            content = route_content(f"https://www.youtube.com/watch?v={YOUTUBE}")
        assert content["transcript_source"] == "watch_along"
        assert "【畫面 0:00】投影片：三個階段" in content["text"] and "大家好" in content["text"]
        assert "【畫面" in ask_api._load_transcript(YOUTUBE)
        assert subtitles.get_subtitles("youtube", YOUTUBE, 1)["source"] == "watch_along"


def test_without_vision_model_only_audio_is_recorded():
    def describe(model, picture):
        raise AssertionError("must not look at frames without a local vision model")

    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}):
        status, result, _ = run_session([], describe)
        assert "no_vision_model" in status["warnings"] and status["vision_model"] is None
        assert result["state"] == "done" and result["visual_count"] == 0


def test_nothing_heard_does_not_overwrite_existing_subtitles():
    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}):
        imported.save_cues("youtube", YOUTUBE, 1, "srt", [{"start": 0, "end": 1, "text": "原本", "translation": None}])
        with patch.object(watch.local_speech, "new_vad", return_value=(FakeVad(), 512)):
            watch.start("youtube", YOUTUBE, 1, REGION, 0, pid=1, models=[], audio_factory=lambda pid: FakeAudio(0),
                        recognize=lambda samples: ([], []))
            time.sleep(0.1)
            result = watch.finish()
        assert result["state"] == "error" and result["error"]
        assert imported.load("youtube", YOUTUBE)["cues"][0]["text"] == "原本"


def test_one_session_at_a_time_and_cancel():
    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}):
        endless = FakeAudio(1000)
        with patch.object(watch.local_speech, "new_vad", return_value=(FakeVad(), 512)):
            watch.start("bilibili", "BV1B7411m7LV", 1, REGION, 0, pid=1, models=[], audio_factory=lambda pid: endless,
                        recognize=lambda samples: ([], []))
            try:
                watch.start("youtube", YOUTUBE, 1, REGION, 0, pid=1, models=[])
                assert False, "second session must wait"
            except ValueError:
                pass
            assert watch.cancel()["state"] == "cancelled"
            assert watch.status() == {"state": "idle"}
        assert imported.load("bilibili", "BV1B7411m7LV") is None


def test_api_rejects_remote_and_bad_input():
    request = type("Req", (), {"client": type("C", (), {"host": "10.0.0.2"}), "headers": {"origin": "http://localhost:15273"}})()
    for call in (lambda: watch_api.watch_finish(request), lambda: watch_api.watch_cancel(request)):
        try:
            call()
            assert False
        except HTTPException as exc:
            assert exc.status_code == 403
    local = type("Req", (), {"client": type("C", (), {"host": "127.0.0.1"}), "headers": {"origin": "http://localhost:15273"}})()
    assert watch_api.watch_status(local)["available"] in (True, False)
    with patch.object(watch, "capture_supported", return_value=False):
        try:
            watch_api.watch_start(watch_api.StartRequest(platform="youtube", video_id=YOUTUBE, region=REGION), local)
            assert False
        except HTTPException as exc:
            assert exc.status_code == 409
    try:
        watch.start("youtube", "../../etc", 1, REGION, 0, pid=1, models=[])
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    test_video_time_follows_youtube_heartbeats_and_falls_back_for_bilibili()
    test_crop_box_maps_page_pixels_to_the_captured_frame()
    test_frame_change_detection()
    test_transcript_interleaves_visual_notes_and_labels_the_source()
    test_session_records_speech_and_frames_then_saves_for_analysis()
    test_without_vision_model_only_audio_is_recorded()
    test_nothing_heard_does_not_overwrite_existing_subtitles()
    test_one_session_at_a_time_and_cancel()
    test_api_rejects_remote_and_bad_input()
    print("Watch-along tests passed")
