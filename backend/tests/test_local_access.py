"""本機 API 不能被使用者瀏覽的其他網站讀寫（CORS "*"、DNS rebinding 回歸測試）。"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import access, config
from app.main import app

LOCAL = "http://127.0.0.1:8420"
EVIL = {"Origin": "https://evil.example"}
WEB_ENV = {"ASTRA_DESKTOP_TOKEN": "", "ASTRA_ALLOWED_ORIGINS": "", "ASTRA_ALLOWED_HOSTS": "",
           "CODESPACE_NAME": "", "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": ""}


def client() -> TestClient:
    return TestClient(app, base_url=LOCAL)


def test_cross_site_page_cannot_read_or_change_settings():
    saved = []
    with patch.dict(os.environ, WEB_ENV), patch.object(config, "save", lambda u: saved.append(u) or {}):
        c = client()
        preflight = c.options("/settings", headers={**EVIL, "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "content-type"})
        assert preflight.status_code == 403
        assert "access-control-allow-origin" not in preflight.headers
        assert c.get("/settings", headers=EVIL).status_code == 403
        assert c.post("/settings", headers=EVIL, json={"obsidian_vault_path": "/"}).status_code == 403
        # 沒帶 Origin、但瀏覽器標示 cross-site 的請求也不放行
        assert c.get("/settings", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert saved == [], "惡意來源不得寫入設定"


def test_dns_rebinding_host_is_rejected():
    with patch.dict(os.environ, WEB_ENV):
        response = client().get("/health", headers={"Host": "attacker.example:8420"})
    assert response.status_code == 403
    assert response.json()["reason"] == "host"


def test_local_frontend_and_tools_still_work():
    with patch.dict(os.environ, WEB_ENV):
        c = client()
        # 終端機 curl／Vite 代理（changeOrigin 後 Host 為 127.0.0.1）
        assert c.get("/health").status_code == 200
        assert c.get("/health", headers={"Host": "localhost:8420"}).status_code == 200
        assert c.get("/health", headers={"Host": "[::1]:8420"}).status_code == 200
        # 本機 Vite 頁面（同源 /api 代理會原樣轉送瀏覽器的 Origin）
        r = c.get("/health", headers={"Origin": "http://127.0.0.1:15273", "Sec-Fetch-Site": "same-origin"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:15273"
        preflight = c.options("/settings", headers={"Origin": "http://localhost:15273",
                                                    "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "content-type"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:15273"


def test_codespaces_only_accepts_this_codespace():
    env = {**WEB_ENV, "CODESPACE_NAME": "fluffy-space-x9",
           "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev"}
    with patch.dict(os.environ, env):
        assert access.origin_allowed("https://fluffy-space-x9-15273.app.github.dev")
        assert not access.origin_allowed("https://other-space-15273.app.github.dev")
        assert not access.origin_allowed("https://fluffy-space-x9-15273.app.github.dev.evil.example")
        assert not access.origin_allowed("http://fluffy-space-x9-15273.app.github.dev")
        r = client().get("/health", headers={"Origin": "https://fluffy-space-x9-15273.app.github.dev"})
        assert r.status_code == 200


def test_origin_parser_rejects_lookalikes():
    with patch.dict(os.environ, WEB_ENV):
        for bad in ("null", "", "http://127.0.0.1.evil.example", "http://localhost@evil.example",
                    "file://", "http://127.0.0.1:99999", "https://evil.example"):
            assert not access.origin_allowed(bad), bad
        for good in ("http://tauri.localhost", "tauri://localhost", "http://[::1]:5173"):
            assert access.origin_allowed(good), good
    with patch.dict(os.environ, {**WEB_ENV, "ASTRA_ALLOWED_ORIGINS": "https://lab.internal"}):
        assert access.origin_allowed("https://lab.internal")


def test_desktop_mode_still_requires_token():
    with patch.dict(os.environ, {**WEB_ENV, "ASTRA_DESKTOP_TOKEN": "b" * 48}):
        c = client()
        tauri = {"Origin": "http://tauri.localhost"}
        assert c.get("/health", headers=tauri).status_code == 403
        assert c.get("/health", headers={**tauri, "X-Astra-Desktop-Token": "b" * 48}).status_code == 200
        # 就算猜到 Token，其他網站仍被擋
        assert c.get("/health", headers={**EVIL, "X-Astra-Desktop-Token": "b" * 48}).status_code == 403


if __name__ == "__main__":
    test_cross_site_page_cannot_read_or_change_settings()
    test_dns_rebinding_host_is_rejected()
    test_local_frontend_and_tools_still_work()
    test_codespaces_only_accepts_this_codespace()
    test_origin_parser_rejects_lookalikes()
    test_desktop_mode_still_requires_token()
    print("Local API access tests passed")
