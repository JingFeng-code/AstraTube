"""YouTube／Bilibili 字幕失敗時的錯誤分類（Issue #19 案例 A、B；全部使用 Mock）。

重點：只有「影片確實沒有字幕」才能說沒有字幕；被擋、斷線、服務異常都必須說出真正原因。
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402
from youtube_transcript_api import _errors as yt  # noqa: E402

from app.transcript import bilibili, cache, captions, imported_subtitles, router  # noqa: E402

VID = "Y5UobXTOZEY"
URL = f"https://www.youtube.com/watch?v={VID}"


def _http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} Client Error", response=response)


def test_every_library_error_is_classified():
    cases = [
        (yt.TranscriptsDisabled(VID), "missing"),
        (yt.NoTranscriptFound(VID, ["zh"], MagicMock()), "missing"),
        (StopIteration(), "missing"),
        (yt.VideoUnavailable(VID), "unavailable"),
        (yt.AgeRestricted(VID), "unavailable"),
        (yt.InvalidVideoId(VID), "unavailable"),
        (yt.VideoUnplayable(VID, "region", []), "unavailable"),
        (yt.RequestBlocked(VID), "blocked"),
        (yt.IpBlocked(VID), "blocked"),
        (yt.PoTokenRequired(VID), "blocked"),
        (yt.YouTubeRequestFailed(VID, _http_error(429)), "blocked"),
        (yt.YouTubeRequestFailed(VID, _http_error(500)), "service"),
        (yt.YouTubeDataUnparsable(VID), "service"),
        (requests.ConnectionError("dns failure"), "network"),
        (requests.exceptions.ProxyError("Tunnel connection failed: 403"), "network"),
        (requests.Timeout("timed out"), "network"),
        (RuntimeError("unexpected"), "service"),
    ]
    for error, kind in cases:
        classified = captions.classify_error(error)
        assert classified.kind == kind, (type(error).__name__, classified.kind)
        assert isinstance(classified, ValueError)
    # 只有 missing 的訊息可以說「沒有提供公開字幕」
    for kind in ("unavailable", "blocked", "network", "service"):
        assert "沒有提供公開字幕" not in str(captions.CaptionError(kind))


def _fake_api(list_result=None, list_error=None):
    api = MagicMock()
    if list_error is not None:
        api.list.side_effect = list_error
    else:
        api.list.return_value = list_result
    return api


def test_fetch_transcript_does_not_hide_download_failures():
    found = MagicMock()
    found.fetch.side_effect = yt.RequestBlocked(VID)
    transcripts = MagicMock()
    transcripts.find_transcript.return_value = found
    with patch.object(captions, "YouTubeTranscriptApi", return_value=_fake_api(transcripts)), \
         patch.object(captions.cache, "get", return_value=None):
        try:
            captions.fetch_transcript(VID)
        except captions.CaptionError as exc:
            assert exc.kind == "blocked", exc.kind
        else:
            raise AssertionError("expected CaptionError")


def test_fetch_transcript_network_and_empty_list():
    with patch.object(captions, "YouTubeTranscriptApi",
                      return_value=_fake_api(list_error=requests.ConnectionError("offline"))), \
         patch.object(captions.cache, "get", return_value=None):
        try:
            captions.fetch_transcript(VID)
        except captions.CaptionError as exc:
            assert exc.kind == "network"
    empty = MagicMock()
    empty.find_transcript.side_effect = yt.NoTranscriptFound(VID, ["zh"], MagicMock())
    empty.__iter__ = lambda self: iter([])
    with patch.object(captions, "YouTubeTranscriptApi", return_value=_fake_api(empty)), \
         patch.object(captions.cache, "get", return_value=None):
        try:
            captions.fetch_transcript(VID)
        except captions.CaptionError as exc:
            assert exc.kind == "missing"


def _route_frozen(error):
    with patch.object(imported_subtitles, "CACHE_DIR", Path(tempfile.mkdtemp())), \
         patch.object(cache, "CACHE_DIR", Path(tempfile.mkdtemp())), \
         patch.object(router.captions, "fetch_transcript", side_effect=error), \
         patch.object(router.whisper_local.sys, "frozen", True, create=True):
        try:
            router.route_content(URL, allow_cloud_fallback=False)
        except ValueError as exc:
            return str(exc)
    raise AssertionError("expected ValueError")


def test_desktop_message_names_the_real_caption_problem():
    network = _route_frozen(requests.exceptions.ProxyError("Tunnel connection failed: 403"))
    assert "無法連線到 YouTube" in network and "沒有提供公開字幕" not in network, network
    assert "SRT" in network, "仍要提供匯入字幕的下一步"
    blocked = _route_frozen(yt.IpBlocked(VID))
    assert "暫時拒絕" in blocked and "沒有提供公開字幕" not in blocked
    missing = _route_frozen(yt.TranscriptsDisabled(VID))
    assert "沒有提供公開字幕" in missing and "SRT" in missing


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _bilibili_error(**kw):
    with patch.object(bilibili.requests, "get", **kw):
        try:
            bilibili._api_json("/x/web-interface/view", {"bvid": "BV1WQHP66EPS"}, "https://www.bilibili.com/")
        except ValueError as exc:
            return str(exc)
    raise AssertionError("expected ValueError")


def test_bilibili_errors_are_distinguished():
    assert "攔截" in _bilibili_error(return_value=_Resp(412))
    assert "攔截" in _bilibili_error(return_value=_Resp(200, {"code": -412, "message": "request was banned"}))
    assert "找不到" in _bilibili_error(return_value=_Resp(200, {"code": -404}))
    assert "不可見" in _bilibili_error(return_value=_Resp(200, {"code": 62002}))
    assert "錯誤碼 -999" in _bilibili_error(return_value=_Resp(200, {"code": -999}))
    assert "HTTP 503" in _bilibili_error(return_value=_Resp(503))
    assert "無法連線" in _bilibili_error(side_effect=requests.ConnectionError("offline"))
    assert "無法解析" in _bilibili_error(return_value=_Resp(200, ValueError("not json")))


def test_bilibili_login_restriction_is_kept_and_suggests_import():
    responses = [
        _Resp(200, {"code": 0, "data": {"pages": [{"cid": 123}]}}),
        _Resp(200, {"code": 0, "data": {"subtitle": {"subtitles": []}, "need_login_subtitle": True}}),
    ]
    with patch.object(bilibili.requests, "get", side_effect=responses), \
         patch.object(bilibili.cache, "get", return_value=None):
        try:
            bilibili.fetch_transcript("BV1WQHP66EPS", 1)
        except ValueError as exc:
            assert "需要登入" in str(exc) and "不會使用你的帳號" in str(exc) and "SRT" in str(exc)
        else:
            raise AssertionError("login-only subtitles must not be fetched")


def test_bilibili_deep_visual_still_rejected_by_backend():
    try:
        router.route_content("https://www.bilibili.com/video/BV1WQHP66EPS/", deep_visual=True)
    except ValueError as exc:
        assert "深視覺" in str(exc)
    else:
        raise AssertionError("backend must keep rejecting unsupported Bilibili deep visual")


if __name__ == "__main__":
    test_every_library_error_is_classified()
    test_fetch_transcript_does_not_hide_download_failures()
    test_fetch_transcript_network_and_empty_list()
    test_desktop_message_names_the_real_caption_problem()
    test_bilibili_errors_are_distinguished()
    test_bilibili_login_restriction_is_kept_and_suggests_import()
    test_bilibili_deep_visual_still_rejected_by_backend()
    print("Caption diagnostics tests passed")
