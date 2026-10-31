"""音訊下載與本機轉寫失敗時，瀏覽器只能看到固定說明（全部使用 Mock，不下載真實影片）。

原始輸出可能含本機路徑與使用者名稱，只能留在後端紀錄。
"""
import asyncio
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from youtube_transcript_api import _errors as yt  # noqa: E402

from app.api import summarize as summarize_api  # noqa: E402
from app.core import messages  # noqa: E402
from app.models.schemas import SummarizeRequest  # noqa: E402
from app.transcript import cache, imported_subtitles, router, whisper_local  # noqa: E402

VID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VID}"
SECRET_USER = "secret-user"
PYTHON_PATH = rf"C:\Users\{SECRET_USER}\app\python.exe"
MISSING_MODULE = f"{PYTHON_PATH}: No module named yt_dlp\n"
DOWNLOAD_ERROR = (f"WARNING: cookies at C:\\Users\\{SECRET_USER}\\c.txt\n"
                  "ERROR: [youtube] RAW_YTDLP_OUTPUT: Video unavailable\n")
RAW_MARKERS = (SECRET_USER, "Users", "python.exe", "No module named", "RAW_YTDLP_OUTPUT", "yt_dlp", "Traceback")


def _assert_public(text):
    for marker in RAW_MARKERS:
        assert marker not in text, (marker, text)


def _failed_run(stderr="", stdout=""):
    return subprocess.CalledProcessError(1, ["python"], output=stdout, stderr=stderr)


def _stream_events(request):
    async def collect():
        rows = []
        async for chunk in summarize_api.summarize_stream(request).body_iterator:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            rows.extend(json.loads(item) for item in text.splitlines() if item.strip())
        return rows
    return asyncio.run(collect())


def _isolated(**patches):
    """走真正的路由與轉錄瀑布：字幕失敗、快取與匯入字幕用空的暫存目錄。"""
    return (patch.object(imported_subtitles, "CACHE_DIR", Path(tempfile.mkdtemp())),
            patch.object(cache, "CACHE_DIR", Path(tempfile.mkdtemp())),
            patch.object(router.captions, "fetch_transcript", side_effect=yt.TranscriptsDisabled(VID)),
            patch.object(whisper_local.subprocess, "run", **patches))


def _responses(**patches):
    """同時走串流與一般兩個端點，回傳 (串流錯誤, 一般錯誤, 後端紀錄)。"""
    request = SummarizeRequest(url=URL, provider="ollama:qwen3")
    log = io.StringIO()
    a, b, c, d = _isolated(**patches)
    with a, b, c, d, contextlib.redirect_stdout(log):
        events = _stream_events(request)
        try:
            summarize_api._prepare(request)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            detail = exc.detail
    fatal = [event["error"] for event in events if event["type"] == "fatal"]
    assert len(fatal) == 1 and events[-1]["type"] == "fatal", events
    _assert_public(json.dumps(events, ensure_ascii=False))
    return fatal[0], detail, log.getvalue()


def test_missing_yt_dlp_explains_environment_and_suggests_import():
    fatal, detail, log = _responses(side_effect=_failed_run(MISSING_MODULE))
    for text in (fatal, detail):
        _assert_public(text)
        assert "沒有安裝影片下載工具" in text and "SRT" in text, text
    assert SECRET_USER in log and "No module named yt_dlp" in log, "原始輸出要留在後端紀錄"


def test_missing_yt_dlp_quoted_form_is_also_recognised():
    error = _failed_run("ModuleNotFoundError: No module named 'yt_dlp'\n")
    fatal, _, _ = _responses(side_effect=error)
    assert "沒有安裝影片下載工具" in fatal, fatal


def test_general_download_failure_shows_fixed_text_only():
    for error in (_failed_run(DOWNLOAD_ERROR), _failed_run(stdout=DOWNLOAD_ERROR)):
        fatal, detail, log = _responses(side_effect=error)
        for text in (fatal, detail):
            _assert_public(text)
            assert "無法下載此影片的音訊" in text and "沒有安裝" not in text, text
        assert "RAW_YTDLP_OUTPUT" in log and SECRET_USER in log, "原始輸出要留在後端紀錄"


def test_failure_without_any_output_and_start_failure_are_public_safe():
    fatal, _, _ = _responses(side_effect=_failed_run())
    assert "無法下載此影片的音訊" in fatal, fatal
    fatal, detail, log = _responses(side_effect=FileNotFoundError(2, "not found", PYTHON_PATH))
    for text in (fatal, detail):
        _assert_public(text)
        assert "無法下載此影片的音訊" in text, text
    assert SECRET_USER in log


def test_download_decodes_output_without_raising():
    with patch.object(whisper_local.subprocess, "run") as run:
        try:
            whisper_local.download_audio(URL, tempfile.mkdtemp())
        except ValueError:
            pass  # 沒有真的下載，找不到音檔是預期結果
    assert run.call_args.kwargs["errors"] == "replace", "解碼失敗不可蓋掉給使用者的說明"


def test_logging_survives_console_encoding_that_cannot_print_output():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp950", errors="strict")
    error = _failed_run(f"ERROR: 無法存取 😀 {PYTHON_PATH}\n")
    with patch.object(whisper_local.subprocess, "run", side_effect=error), \
         patch.object(sys, "stdout", stream):
        try:
            whisper_local.download_audio(URL, tempfile.mkdtemp())
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "無法下載此影片的音訊" in str(exc), exc


def _transcribe_error(model):
    log = io.StringIO()
    with patch.object(whisper_local, "_get_model", **model), contextlib.redirect_stdout(log):
        try:
            whisper_local.transcribe_file("audio.webm")
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            return str(exc), log.getvalue()


def test_missing_engine_and_decode_failures_are_public_safe():
    shown, log = _transcribe_error({"side_effect": ModuleNotFoundError("No module named 'faster_whisper'")})
    _assert_public(shown)
    assert "沒有安裝語音轉錄工具" in shown and "SRT" in shown and "faster_whisper" in log, shown

    def broken_segments():
        raise RuntimeError(f"Invalid data: {PYTHON_PATH}")
        yield  # 惰性產生器：錯誤在讀取片段時才發生

    model = MagicMock()
    model.transcribe.return_value = (broken_segments(), MagicMock(language="en"))
    shown, log = _transcribe_error({"return_value": model})
    _assert_public(shown)
    assert "無法轉錄這段音訊" in shown and SECRET_USER in log, shown


def test_no_speech_message_is_kept():
    model = MagicMock()
    model.transcribe.return_value = ([], MagicMock(language="en"))
    shown, _ = _transcribe_error({"return_value": model})
    assert shown == messages.t("whisper.no_speech")


def test_unexpected_fetch_errors_do_not_reach_the_browser():
    request = SummarizeRequest(url=URL, provider="ollama:qwen3")
    log = io.StringIO()
    with patch.object(summarize_api, "route_content", side_effect=RuntimeError(MISSING_MODULE)), \
         contextlib.redirect_stdout(log):
        events = _stream_events(request)
        try:
            summarize_api._prepare(request)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 500
            _assert_public(exc.detail)
    assert events[-1]["type"] == "fatal", events
    _assert_public(json.dumps(events, ensure_ascii=False))
    assert SECRET_USER in log.getvalue(), "原始內容要留在後端紀錄"


def test_public_messages_have_no_placeholder_for_raw_output():
    keys = ("whisper.downloader_missing", "whisper.download_failed", "whisper.engine_missing",
            "whisper.transcribe_failed", "summarize.fetch_failed")
    for key in keys:
        for text in messages.MESSAGES[key].values():
            assert "{" not in text, (key, text)


if __name__ == "__main__":
    test_missing_yt_dlp_explains_environment_and_suggests_import()
    test_missing_yt_dlp_quoted_form_is_also_recognised()
    test_general_download_failure_shows_fixed_text_only()
    test_failure_without_any_output_and_start_failure_are_public_safe()
    test_download_decodes_output_without_raising()
    test_logging_survives_console_encoding_that_cannot_print_output()
    test_missing_engine_and_decode_failures_are_public_safe()
    test_no_speech_message_is_kept()
    test_unexpected_fetch_errors_do_not_reach_the_browser()
    test_public_messages_have_no_placeholder_for_raw_output()
    print("Whisper error tests passed")
