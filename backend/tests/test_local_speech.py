"""本機語音轉文字：不下載模型也不需要語音引擎的 mock 測試。"""
import asyncio
import hashlib
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.api import local_video
from app.transcript import imported_subtitles as imported
from app.transcript import local_speech as speech
from app.transcript.router import route_content

VIDEO = "0123456789abcdef"


def test_cues_break_on_punctuation_and_length():
    tokens = list("大家好，今天我們要介紹語音辨識模型。") + ["\u2581Hello", "\u2581world", "."]
    stamps = [index * 0.2 for index in range(len(tokens))]
    cues = speech.build_cues(tokens, stamps, 10.0, 16.0)
    assert [cue["text"] for cue in cues] == ["大家好，今天我們要介紹語音辨識模型。", "Hello world."]
    assert cues[0]["start"] == 10.0 and cues[1]["start"] == cues[0]["end"]
    assert cues[1]["end"] == 16.0
    # 沒有標點的長句也要斷開，模型標記不能進字幕
    long = speech.build_cues(["<|zh|>"] + ["字"] * 90, [0.0] + [i * 0.1 for i in range(90)], 0, 9)
    assert all(len(cue["text"]) <= 40 for cue in long) and "<" not in long[0]["text"]
    assert speech.build_cues([], [], 0, 1) == []
    # 英文可以放比較長；切在句尾時句點不能自己變成一句
    words = ["▁word"] * 16 + ["."]
    english = speech.build_cues(words, [i * 0.3 for i in range(len(words))], 0, 6)
    assert len(english) == 1 and english[0]["text"].endswith("word.") and " word" in english[0]["text"]


def test_cue_limit_merges_instead_of_dropping():
    cues = [{"start": i, "end": i + 1, "text": f"w{i}", "translation": None} for i in range(imported.MAX_CUES + 5)]
    merged = speech._fit_cue_limit(cues)
    assert len(merged) <= imported.MAX_CUES
    assert merged[-1]["end"] == imported.MAX_CUES + 5
    assert "w0 w1" in merged[0]["text"]


def test_only_this_computer_may_send_video():
    allowed = local_video.on_this_computer
    assert allowed("127.0.0.1", "http://localhost:15273")
    assert allowed("127.0.0.1", "http://tauri.localhost")
    assert allowed("127.0.0.1", None)
    assert not allowed("10.0.0.5", "http://localhost:15273")
    assert not allowed("127.0.0.1", "https://example.com")
    assert not allowed("127.0.0.1", "https://name-15273.app.github.dev")
    with patch.dict("os.environ", {"CODESPACE_NAME": "x"}):
        assert not allowed("127.0.0.1", "http://localhost:15273")


def test_model_download_verifies_hash_and_never_keeps_a_bad_file():
    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield self.body

    good = b"model bytes"
    files = (("m.bin", "https://example.invalid/m", hashlib.sha256(good).hexdigest(), len(good)),)
    with TemporaryDirectory() as location:
        folder = Path(location)
        with patch.object(speech, "MODEL_DIR", folder), patch.object(speech, "MODEL_FILES", files), \
             patch.object(speech, "MODEL_BYTES", len(good)), patch.object(speech, "_download", dict(speech._download)):
            with patch.object(speech.requests, "get", return_value=Response(b"tampered")):
                speech._run_download()
            assert speech.download_status()["state"] == "error"
            assert not (folder / "m.bin").exists() and not (folder / "m.bin.part").exists()
            assert not speech.model_ready()
            with patch.object(speech.requests, "get", return_value=Response(good)):
                speech._run_download()
            assert speech.download_status()["state"] == "idle"
            assert speech.model_ready()
            with patch.object(speech.requests, "get", side_effect=AssertionError("already downloaded")):
                speech._run_download()


def test_pinned_model_files_are_https_and_hashed():
    for name, url, digest, size in speech.MODEL_FILES:
        assert url.startswith("https://") and len(digest) == 64 and size > 0, name


class FakeRequest:
    def __init__(self, body=b"video", headers=None, client="127.0.0.1"):
        self.headers = {"content-length": str(len(body)), "origin": "http://localhost:15273", **(headers or {})}
        self.client = type("Client", (), {"host": client})
        self.body = body

    async def stream(self):
        yield self.body[:2]
        yield self.body[2:]


def _wait(video_id):
    for _ in range(200):
        status = speech.job_status(video_id)
        if status["state"] not in ("uploading", "running"):
            return status
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_upload_transcribes_saves_and_deletes_video():
    cues = [{"start": 1.0, "end": 2.0, "text": "本機語音", "translation": None}]
    with TemporaryDirectory() as location:
        folder = Path(location)
        seen = {}

        def fake_transcribe(path, on_progress, cancelled):
            seen["bytes"] = Path(path).read_bytes()
            on_progress(0.5)
            return cues

        with patch.object(speech, "UPLOAD_DIR", folder / "tmp"), patch.object(imported, "CACHE_DIR", folder / "subs"), \
             patch.object(speech, "engine_available", return_value=True), patch.object(speech, "model_ready", return_value=True), \
             patch.object(speech, "transcribe_file", side_effect=fake_transcribe), patch.object(speech, "_jobs", {}):
            asyncio.run(local_video.upload_and_transcribe(VIDEO, FakeRequest(b"video-bytes")))
            status = _wait(VIDEO)
            assert status["state"] == "done" and status["cue_count"] == 1
            assert seen["bytes"] == b"video-bytes"
            assert list((folder / "tmp").glob("*")) == []
            stored = imported.load("local", VIDEO)
            assert stored["format"] == "asr" and stored["is_chinese"] is True
            content = route_content(f"local://{VIDEO}")
            assert content["transcript_source"] == "local_speech" and "本機語音" in content["text"]


def test_upload_rejections_leave_nothing_behind():
    with TemporaryDirectory() as location:
        folder = Path(location)
        run = lambda request, vid=VIDEO: asyncio.run(local_video.upload_and_transcribe(vid, request))

        def status_of(request, vid=VIDEO):
            try:
                run(request, vid)
            except HTTPException as exc:
                return exc.status_code
            raise AssertionError("must be rejected")

        with patch.object(speech, "UPLOAD_DIR", folder), patch.object(speech, "_jobs", {}), \
             patch.object(speech, "engine_available", return_value=True), patch.object(speech, "model_ready", return_value=True):
            assert status_of(FakeRequest(client="10.0.0.5")) == 403
            assert status_of(FakeRequest(headers={"origin": "https://evil.example"})) == 403
            assert status_of(FakeRequest(), "../../etc") == 400
            assert status_of(FakeRequest(headers={"content-length": "abc"})) == 411
            assert status_of(FakeRequest(headers={"content-length": "0"})) == 413
            # 宣告大小和實際收到不同：不開始處理，也不留暫存檔
            assert status_of(FakeRequest(b"short", headers={"content-length": "999"})) == 400
            assert list(folder.glob("*.video")) == []
            assert speech.job_status(VIDEO)["state"] == "idle"
            with patch.object(speech, "has_room_for", return_value=False):
                assert status_of(FakeRequest()) == 507
            with patch.object(speech, "model_ready", return_value=False):
                assert status_of(FakeRequest()) == 409
            with patch.object(speech, "engine_available", return_value=False):
                assert status_of(FakeRequest()) == 409


def test_one_job_at_a_time_and_cancel():
    release = threading.Event()

    def slow(path, on_progress, cancelled):
        release.wait(2)
        if cancelled():
            raise InterruptedError
        return []

    with TemporaryDirectory() as location:
        folder = Path(location)
        with patch.object(speech, "UPLOAD_DIR", folder), patch.object(speech, "_jobs", {}), \
             patch.object(speech, "engine_available", return_value=True), patch.object(speech, "model_ready", return_value=True), \
             patch.object(speech, "transcribe_file", side_effect=slow):
            asyncio.run(local_video.upload_and_transcribe(VIDEO, FakeRequest()))
            try:
                asyncio.run(local_video.upload_and_transcribe("fedcba9876543210", FakeRequest()))
                assert False, "second job must wait"
            except HTTPException as exc:
                assert exc.status_code == 409
            assert list(folder.glob("*.video"))  # 忙碌時不能刪掉正在處理的影片
            speech.cancel_job(VIDEO)
            release.set()
            assert _wait(VIDEO)["state"] == "cancelled"
            assert list(folder.glob("*.video")) == []


def test_engine_errors_never_expose_paths():
    with TemporaryDirectory() as location:
        folder = Path(location)
        secret = r"C:\Users\someone\video.mp4"
        with patch.object(speech, "UPLOAD_DIR", folder), patch.object(speech, "_jobs", {}), \
             patch.object(speech, "engine_available", return_value=True), patch.object(speech, "model_ready", return_value=True), \
             patch.object(speech, "transcribe_file", side_effect=RuntimeError(secret)):
            asyncio.run(local_video.upload_and_transcribe(VIDEO, FakeRequest()))
            status = _wait(VIDEO)
            assert status["state"] == "error" and secret not in status["error"] and status["error"]


if __name__ == "__main__":
    test_cues_break_on_punctuation_and_length()
    test_cue_limit_merges_instead_of_dropping()
    test_only_this_computer_may_send_video()
    test_model_download_verifies_hash_and_never_keeps_a_bad_file()
    test_pinned_model_files_are_https_and_hashed()
    test_upload_transcribes_saves_and_deletes_video()
    test_upload_rejections_leave_nothing_behind()
    test_one_job_at_a_time_and_cancel()
    test_engine_errors_never_expose_paths()
    print("Local speech tests passed")
