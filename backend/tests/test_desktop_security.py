"""Desktop transport must not leak local settings to a random browser tab."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app

TOKEN = "a" * 48


def test_desktop_token_gate():
    client = TestClient(app)
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": TOKEN}):
        assert client.get("/health").status_code == 403
        assert client.get("/settings").status_code == 403
        assert client.get("/health", headers={"X-Astra-Desktop-Token": TOKEN}).status_code == 200
        assert client.get("/settings", headers={"X-Astra-Desktop-Token": TOKEN}).status_code == 200
        assert client.get("/health", headers={"X-Astra-Desktop-Token": "wrong"}).status_code == 403


def test_web_mode_keeps_existing_contract():
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": ""}):
        response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_desktop_entry_rejects_missing_credentials():
    from desktop_server import main
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": "", "ASTRA_DESKTOP_PORT": "1234",
                                 "ASTRA_DESKTOP_DATA_DIR": "/tmp/invalid"}, clear=False):
        try:
            main()
            assert False
        except SystemExit as exc:
            assert exc.code == 2


if __name__ == "__main__":
    test_desktop_token_gate()
    test_web_mode_keeps_existing_contract()
    test_desktop_entry_rejects_missing_credentials()
    print("Desktop API security tests passed")
