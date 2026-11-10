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


def test_user_picks_vision_model_or_turns_it_off():
    models = ["llava:7b", "qwen3.5:latest"]
    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}), \
         patch.object(watch.local_speech, "new_vad", return_value=(FakeVad(), 512)):
        # 選了第二個模型就用第二個，不再固定挑第一個
        status = watch.start("youtube", YOUTUBE, 1, REGION, 0, vision_model="qwen3.5:latest", pid=1, models=models,
                             audio_factory=lambda pid: FakeAudio(0), frames_factory=FakeFrames,
                             recognize=lambda samples: ([], []), describe=lambda model, picture: "")
        assert status["vision_model"] == "qwen3.5:latest" and "audible" in status
        watch.cancel()
        # 只記聲音：不看畫面，也不顯示「沒有看圖模型」的提醒
        status = watch.start("youtube", YOUTUBE, 1, REGION, 0, use_vision=False, pid=1, models=models,
                             audio_factory=lambda pid: FakeAudio(0), recognize=lambda samples: ([], []))
        assert status["vision_model"] is None and "no_vision_model" not in status["warnings"]
        watch.cancel()
        # 不在本機看圖模型清單裡（例如雲端模型）就拒絕，不偷偷換成別的模型
        try:
            watch.start("youtube", YOUTUBE, 1, REGION, 0, vision_model="gpt-4o:cloud", pid=1, models=models)
        except ValueError as exc:
            assert "gpt-4o:cloud" in str(exc)
        else:
            raise AssertionError("unknown vision model must be rejected")
        assert watch.status()["state"] != "running"


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


class GappyAudio:
    """先說話 1 秒、停 2 秒（Windows 不送資料）、再說話 1 秒。"""
    def __init__(self):
        self.step = 0

    def read(self, _timeout):
        self.step += 1
        if self.step <= 5 or 16 <= self.step <= 20:
            time.sleep(0.2)
            return (np.ones(3200, dtype=np.int16) * 1000).tobytes()
        time.sleep(0.2)
        return b""

    def close(self):
        pass


class RecordingVad(FakeVad):
    def __init__(self):
        super().__init__()
        self.samples = []

    def accept_waveform(self, samples):
        self.samples.append(np.asarray(samples).copy())


def test_audio_pause_inserts_silence_so_sentences_split():
    vad = RecordingVad()
    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}), \
         patch.object(watch.local_speech, "new_vad", return_value=(vad, 512)):
        watch.start("youtube", YOUTUBE, 1, REGION, 0, pid=1, models=[], audio_factory=lambda pid: GappyAudio(),
                    recognize=lambda samples: ([], []))
        time.sleep(4.6)
        watch.cancel()
    joined = np.concatenate(vad.samples)
    zero_runs = np.flatnonzero(np.diff(np.concatenate(([0], (joined == 0).astype(int), [0]))))
    longest = max(end - start for start, end in zip(zero_runs[::2], zero_runs[1::2]))
    assert longest >= watch.SAMPLE_RATE * 0.9, longest  # 中間補了將近 1 秒的靜音


def test_finish_waits_for_slow_workers_instead_of_saving_partial_results():
    release = threading.Event()

    def slow_recognize(samples):
        release.wait(5)
        return (list("好。"), [0.0, 0.2])

    with TemporaryDirectory() as location, patch.object(imported, "CACHE_DIR", Path(location)), patch.object(watch, "_current", {}), \
         patch.object(watch.local_speech, "new_vad", return_value=(FakeVad(), 512)):
        watch.start("youtube", YOUTUBE, 1, REGION, 0, pid=1, models=[], audio_factory=lambda pid: FakeAudio(1),
                    recognize=slow_recognize)
        time.sleep(0.3)
        recorder = watch._current["recorder"]
        with patch.object(recorder, "stop", wraps=lambda timeout=150.0: watch.Recorder.stop(recorder, 0.2)):
            first = watch.finish()
        assert first["state"] == "running" and first["error"]
        assert imported.load("youtube", YOUTUBE) is None  # 還沒處理完就不存
        release.set()
        second = watch.finish()
        assert second["state"] == "done" and second["cue_count"] == 1 and not second["error"]


def test_crop_uses_current_window_bounds():
    calls = []
    fake_capture = type("Cap", (), {"close": lambda self: None})()
    from app.capture import window_capture as wc
    with patch.object(wc, "make_dpi_aware"), patch.object(wc, "find_main_window", return_value=42), \
         patch.object(wc, "WindowFrames", return_value=fake_capture), \
         patch.object(wc, "client_offset", side_effect=lambda hwnd: calls.append(hwnd) or (0, 0, 1000 + 1000 * (len(calls) > 1), 800)):
        frames = watch._window_frames(1, lambda rgb: None)
        small = frames(REGION, 1000, 800)
        large = frames(REGION, 2000, 800)  # 視窗被放大：外框和擷取畫面一起變寬，裁切不能再被縮放一次
    assert calls == [42, 42]
    assert small == large


class FakeProc:
    def __init__(self, pid, name, args=(), children=(), broken=False):
        self.pid, self._name, self._args, self._children, self._broken = pid, name, list(args), list(children), broken

    def name(self):
        if self._broken:
            import psutil
            raise psutil.AccessDenied(self.pid)
        return self._name

    def cmdline(self):
        return self._args

    def children(self):
        return self._children


def test_audio_is_recorded_from_the_webview2_browser_process():
    import psutil
    # 實機發現：錄 AstraTube 主程式只會錄到靜音，要錄它底下的 WebView2 瀏覽器程序
    tree = FakeProc(100, "AstraTube.exe", children=[
        FakeProc(101, "astratube-backend.exe"),
        FakeProc(102, "msedgewebview2.exe", broken=True),
        FakeProc(103, "msedgewebview2.exe", ["msedgewebview2.exe", "--type=renderer"]),
        FakeProc(104, "msedgewebview2.exe", ["msedgewebview2.exe", "--embedded-browser-webview=1"]),
    ])
    with patch.object(psutil, "Process", return_value=tree):
        assert watch.audio_pid(100) == 104
    # 開發時直接指定瀏覽器：沒有 WebView2 子程序，就錄原本的程式
    with patch.object(psutil, "Process", return_value=FakeProc(200, "msedge.exe")):
        assert watch.audio_pid(200) == 200
    with patch.object(psutil, "Process", side_effect=psutil.NoSuchProcess(300)):
        assert watch.audio_pid(300) == 300


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
    test_user_picks_vision_model_or_turns_it_off()
    test_nothing_heard_does_not_overwrite_existing_subtitles()
    test_audio_pause_inserts_silence_so_sentences_split()
    test_finish_waits_for_slow_workers_instead_of_saving_partial_results()
    test_crop_uses_current_window_bounds()
    test_audio_is_recorded_from_the_webview2_browser_process()
    test_one_session_at_a_time_and_cancel()
    test_api_rejects_remote_and_bad_input()
    print("Watch-along tests passed")
