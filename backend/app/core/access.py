"""本機後端的來源防護：避免使用者瀏覽的其他網站操作 AstraTube 的本機 API。

AstraTube 後端預設只監聽 127.0.0.1，但瀏覽器裡任何網頁都能對 127.0.0.1 發送請求。
若沒有這層防護，惡意網站可以讀取／修改設定、把 Obsidian vault 指到任意資料夾，
或消耗使用者自己的 API 額度。這裡做兩道檢查：

  1. Host 檢查：擋下 DNS rebinding（惡意網域解析到 127.0.0.1，偽裝成同源）。
  2. Origin 檢查：只接受本機開發頁面、桌面版 Tauri 視窗、目前這個 Codespace
     的轉送網址，以及使用者用環境變數明確加入的來源。

這不是帳號系統：通過檢查只代表「請求來自這台電腦上的 AstraTube 介面」，
不能拿來當多人公開服務的權限控管。
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# Windows 正式版 Tauri 使用 http://tauri.localhost；macOS／Linux 使用 tauri://localhost。
TAURI_ORIGINS = frozenset({"http://tauri.localhost", "https://tauri.localhost", "tauri://localhost"})


def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _hostname(host_header: str) -> str:
    """從 Host 標頭取出主機名稱（支援 [::1]:8420 這種 IPv6 寫法）。"""
    try:
        return (urlsplit("//" + (host_header or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


def host_allowed(host_header: str) -> bool:
    """Host 只能是回環位址，或 ASTRA_ALLOWED_HOSTS 明確列出的名稱。"""
    name = _hostname(host_header)
    if not name:
        return False
    extra = {item.lower() for item in _env_list("ASTRA_ALLOWED_HOSTS")}
    return name in LOOPBACK_HOSTS or name in extra


def _codespaces_origin(scheme: str, hostname: str) -> bool:
    """只接受「目前這個 Codespace」的轉送網址，不接受其他人的 Codespace。"""
    name = os.environ.get("CODESPACE_NAME", "").strip().lower()
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip().lower()
    if scheme != "https" or not name or not domain:
        return False
    suffix = "." + domain
    if not hostname.endswith(suffix):
        return False
    label = hostname[: -len(suffix)]
    prefix = name + "-"
    return label.startswith(prefix) and label[len(prefix):].isdigit()


def origin_allowed(origin: str) -> bool:
    """瀏覽器帶來的 Origin 是否屬於 AstraTube 自己的介面。"""
    value = (origin or "").strip()
    if not value or value == "null":
        return False
    if value in TAURI_ORIGINS or value in _env_list("ASTRA_ALLOWED_ORIGINS"):
        return True
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower()
        parsed.port  # 埠號格式錯誤會在這裡拋 ValueError
    except ValueError:
        return False
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return False
    if parsed.scheme in ("http", "https") and hostname in LOOPBACK_HOSTS:
        return True
    return _codespaces_origin(parsed.scheme, hostname)


def rejection_reason(host: str, origin: str | None, fetch_site: str | None) -> str | None:
    """回傳拒絕原因；可放行時回傳 None。

    沒有 Origin 的請求（終端機 curl、健康檢查、伺服器端代理）只要 Host 正確就放行；
    瀏覽器標示為 cross-site 卻沒帶 Origin 的請求一律拒絕。
    """
    if not host_allowed(host):
        return "host"
    if origin is not None:
        return None if origin_allowed(origin) else "origin"
    if (fetch_site or "").lower() == "cross-site":
        return "cross-site"
    return None
