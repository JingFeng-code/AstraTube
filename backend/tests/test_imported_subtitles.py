"""SRT/VTT 匯入端到端契約：全程本機 tmp 資料夾，絕不連線影片平台。"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import subtitles, subtitle_import, ask as ask_api
from app.transcript import imported_subtitles as imported
from app.transcript.router import route_content

YOUTUBE = "M7lc1UVf-VE"
BILIBILI = "BV1B7411m7LV"
SRT = """1
00:00:01,250 --> 00:00:02,875
Hello world

2
00:00:02,875 --> 00:00:04,005
<font color="red">Create an API</font>
"""
VTT = """WEBVTT

NOTE subtitle editor
comment

chapter-1
00:01.025 --> 00:02.125 align:start position:0%
你好 <i>世界</i>

00:02.125 --> 00:04.050
第二句
"""


def test_parsing_preserves_milliseconds_and_text():
    fmt, cues = imported.parse_subtitle_file("mine.srt", "\ufeff"+SRT.replace("\n","\r\n"))
    assert fmt == "srt"
    assert cues[0] == {"start": 1.25, "end": 2.875, "text": "Hello world", "translation": None}
    assert cues[1]["end"] == 4.005
    assert cues[1]["text"] == "Create an API"
    fmt, cues = imported.parse_subtitle_file("mine.vtt", VTT)
    assert fmt == "vtt"
    assert cues[0]["start"] == 1.025
    assert cues[0]["end"] == 2.125
    assert cues[0]["text"] == "你好 世界"
    assert cues[1]["end"] == 4.05


def test_rejects_invalid_files_and_target_hosts():
    for filename, content in (
        ("notebook.txt",SRT), ("bad.vtt", SRT), ("empty.srt","no captions"),
        ("bad.srt", "1\n00:00:02,000 --> 00:00:01,000\nbad"),
        ("bad.srt", "1\n00:66:01,000 --> 00:67:00,000\nbad"),
        ("huge.srt","A"*(imported.MAX_FILE_BYTES+1)),
    ):
        try:
            imported.parse_subtitle_file(filename,content)
            assert False, filename
        except ValueError:
            pass
    for url in (
        f"https://bilibili.com.evil.net/video/{BILIBILI}",
        f"http://www.bilibili.com/video/{BILIBILI}",
        f"https://evil-youtube.com/watch?v={YOUTUBE}",
        f"http://www.youtube.com/watch?v={YOUTUBE}",
        "https://www.youtube.com/watch?v=invalid",
        "https://www.youtube.com/watch?v=bad&v=second",
    ):
        try:
            imported.target_from_url(url)
            assert False, url
        except ValueError:
            pass
    assert imported.target_from_url(f"https://youtu.be/{YOUTUBE}") == ("youtube",YOUTUBE,1)
    assert imported.target_from_url(f"https://www.bilibili.com/video/{BILIBILI}?p=3") == ("bilibili",BILIBILI,3)


def test_imported_youtube_used_by_summary_ask_and_player():
    with TemporaryDirectory() as location:
        with patch.object(imported, "CACHE_DIR", Path(location)):
            result = subtitle_import.import_subtitles(subtitle_import.ImportRequest(
                video_url=f"https://www.youtube.com/watch?v={YOUTUBE}",
                filename="mine.srt",content=SRT))
            assert result["cue_count"] == 2 and result["source"] == "imported"
            with patch.object(subtitles.captions, "fetch_transcript",
                              side_effect=AssertionError("Should not fetch YouTube")):
                player = subtitles.get_subtitles("youtube",YOUTUBE,1)
            assert player["source"] == "imported"
            assert player["timing_precision"] == "milliseconds_original"
            assert player["cues"][0]["start"] == 1.25
            assert player["cues"][0]["end"] == 2.875
            with patch("app.transcript.router.captions.fetch_transcript",
                       side_effect=AssertionError("Do not contact platform")):
                summary = route_content(f"https://www.youtube.com/watch?v={YOUTUBE}")
            assert summary["transcript_source"] == "imported_subtitles"
            assert "[1] Hello world" in summary["text"]
            with patch.object(ask_api.captions, "fetch_transcript",
                              side_effect=AssertionError("Do not contact platform")):
                assert "Create an API" in ask_api._load_transcript(YOUTUBE)
            deleted = subtitle_import.remove_subtitles(subtitle_import.TargetRequest(
                video_url=f"https://www.youtube.com/watch?v={YOUTUBE}"))
            assert deleted["removed"] is True
            assert imported.load("youtube", YOUTUBE,1) is None


def test_imported_bilibili_scoped_to_page():
    with TemporaryDirectory() as location:
        with patch.object(imported, "CACHE_DIR", Path(location)):
            subtitle_import.import_subtitles(subtitle_import.ImportRequest(
                video_url=f"https://www.bilibili.com/video/{BILIBILI}/?p=2",
                filename="mine.vtt",content=VTT))
            assert imported.load("bilibili",BILIBILI,1) is None
            with patch("app.transcript.router.bilibili.fetch_transcript",
                       side_effect=AssertionError("Should not contact Bilibili")):
                summary = route_content(f"https://www.bilibili.com/video/{BILIBILI}/?p=2")
            assert summary["bilibili_page"] == 2
            assert summary["transcript_source"] == "imported_subtitles"
            player = subtitles.get_subtitles("bilibili",BILIBILI,2)
            assert player["cues"][0]["start"] == 1.025
            assert "你好" in ask_api._load_transcript(f"bilibili:{BILIBILI}:p2")
            assert imported.delete("bilibili",BILIBILI,2)
            assert imported.load("bilibili",BILIBILI,2) is None


def test_replacing_subtitles_keeps_latest_only():
    with TemporaryDirectory() as location:
        with patch.object(imported, "CACHE_DIR", Path(location)):
            imported.save("youtube",YOUTUBE,1,"mine.srt",SRT)
            imported.save("youtube",YOUTUBE,1,"mine.vtt",VTT)
            updated = imported.load("youtube",YOUTUBE,1)
            assert updated["format"] == "vtt"
            assert len(updated["cues"]) == 2


def test_rejects_unsupported_extension_at_api_layer():
    try:
        subtitle_import.import_subtitles(subtitle_import.ImportRequest(
            video_url=f"https://www.youtube.com/watch?v={YOUTUBE}",
            filename="notes.exe",content=SRT))
        assert False
    except HTTPException as exc:
        assert exc.status_code == 400


if __name__ == "__main__":
    test_parsing_preserves_milliseconds_and_text()
    test_rejects_invalid_files_and_target_hosts()
    test_imported_youtube_used_by_summary_ask_and_player()
    test_imported_bilibili_scoped_to_page()
    test_replacing_subtitles_keeps_latest_only()
    test_rejects_unsupported_extension_at_api_layer()
    print("Imported SRT/VTT subtitle tests passed")
