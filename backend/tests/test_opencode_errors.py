"""OpenCode API 錯誤處理：保留真正的 HTTP／網路原因，不再被變數遮蔽成 AttributeError（不呼叫真實 API）。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from app.llm import opencode  # noqa: E402
from app.llm.base import EmptyResponseError, ProviderError  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _expect_error(response, error_type, expected):
    with patch.object(opencode.httpx, "post", return_value=response):
        try:
            opencode._post_chat("dummy-free-model", [{"role": "user", "content": "hello"}])
        except error_type as exc:
            assert expected in str(exc), str(exc)
        else:
            raise AssertionError(f"Expected {error_type.__name__}")


def test_http_failure_reports_real_status():
    _expect_error(FakeResponse(429, text="rate limit"), ProviderError, "HTTP 429")
    _expect_error(FakeResponse(404, text="model not found"), ProviderError, "HTTP 404")


def test_invalid_json_reports_parse_error():
    _expect_error(FakeResponse(payload=ValueError("not JSON"), text="not JSON"), ProviderError, "JSON")


def test_provider_error_and_empty_response():
    _expect_error(FakeResponse(payload={"error": {"message": "model overloaded"}}), ProviderError, "model overloaded")
    _expect_error(FakeResponse(payload={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}),
                  EmptyResponseError, "finish_reason=length")


def test_network_failure_reports_connection_problem():
    with patch.object(opencode.httpx, "post", side_effect=httpx.ConnectError("network down")):
        try:
            opencode._post_chat("dummy-free-model", [{"role": "user", "content": "hello"}])
        except ProviderError as exc:
            assert "network down" in str(exc), str(exc)
        else:
            raise AssertionError("Expected ProviderError")


def test_success_keeps_original_payload():
    with patch.object(opencode.httpx, "post", return_value=FakeResponse(payload={
        "choices": [{"message": {"content": "正常回應"}}]
    })) as post:
        assert opencode._post_chat("dummy-free-model", [{"role": "user", "content": "hello"}]) == "正常回應"
        assert post.call_args.kwargs["json"]["messages"] == [{"role": "user", "content": "hello"}]


if __name__ == "__main__":
    test_http_failure_reports_real_status()
    test_invalid_json_reports_parse_error()
    test_provider_error_and_empty_response()
    test_network_failure_reports_connection_problem()
    test_success_keeps_original_payload()
    print("OpenCode error-handling regression tests passed.")
