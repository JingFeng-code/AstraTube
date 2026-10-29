"""字幕時間軸測試：所有來源均 mock，不需公開影片或 API Key。"""
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import subtitles


def test_timestamp_conversion_and_merging():
    cues = subtitles.parse_timed_cues("[3] Hello\n[3] world\n[8] next\n【畫面 0:12】 image\n[16] last")
    assert len(cues) == 3
    assert cues[0] == {"start": 3, "end": 8, "text": "Hello world", "translation": None}
    assert cues[1]["end"] == 16
    assert cues[2]["end"] == 21
    assert subtitles.parse_timed_cues("no timestamps\n【畫面 01:22】some image") == []


def test_youtube_subtitle_response():
    with patch.object(subtitles.captions, "fetch_transcript", return_value=("[0] Hello\n[5] World", False)):
        result = subtitles.get_subtitles("youtube", "M7lc1UVf-VE", 1)
    assert result["platform"] == "youtube"
    assert len(result["cues"]) == 2
    assert result["cues"][0]["text"] == "Hello"
    assert result["translation_status"] == "not_available"


def test_bilibili_subtitle_response_and_page():
    with patch.object(subtitles.bilibili, "fetch_transcript", return_value=("[0] 測試\n[12] 下一句", True)) as mock:
        result = subtitles.get_subtitles("bilibili", "BV1B7411m7LV", 3)
    mock.assert_called_once_with("BV1B7411m7LV", 3)
    assert result["page"] == 3
    assert result["is_chinese"] is True


def test_invalid_id_and_missing_subtitles():
    for platform, vid in (("youtube", "bad"), ("bilibili", "wrong")):
        try:
            subtitles.get_subtitles(platform, vid, 1)
            assert False, "bad IDs should be rejected"
        except HTTPException as exc:
            assert exc.status_code == 400
    missing = subtitles.captions.CaptionError("missing", "no transcript")
    with patch.object(subtitles.captions, "fetch_transcript", side_effect=missing), \
         patch.object(subtitles.cache, "get", return_value=None):
        try:
            subtitles.get_subtitles("youtube", "M7lc1UVf-VE", 1)
            assert False, "no source should not be reported as successful"
        except HTTPException as exc:
            assert exc.status_code == 404
            assert "沒有提供公開字幕" in exc.detail
    # 斷線不是「沒有字幕」：回 503 並說明影片可能仍有字幕
    network = subtitles.captions.CaptionError("network", "ProxyError")
    with patch.object(subtitles.captions, "fetch_transcript", side_effect=network), \
         patch.object(subtitles.cache, "get", return_value=None):
        try:
            subtitles.get_subtitles("youtube", "M7lc1UVf-VE", 1)
            assert False
        except HTTPException as exc:
            assert exc.status_code == 503
            assert "可能有字幕" in exc.detail


if __name__ == "__main__":
    test_timestamp_conversion_and_merging()
    test_youtube_subtitle_response()
    test_bilibili_subtitle_response_and_page()
    test_invalid_id_and_missing_subtitles()
    print("subtitle contract tests passed")
