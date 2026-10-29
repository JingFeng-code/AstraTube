"""Bilibili 公開影片字幕擷取：只讀可匿名取得的字幕，不下載影音或處理登入態。"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from app.transcript import cache

_BVID = re.compile(r"^BV[0-9A-Za-z]{10}$")
_VIDEO_PATH = re.compile(r"^/video/(BV[0-9A-Za-z]{10})(?:/|$)")
_CACHE_PREFIX = "bilibili_v1:"
_HEADERS = {"User-Agent": "AstraTube/1.0 (public subtitle reader)", "Accept": "application/json"}
_MAX_SUBTITLE_BYTES = 12 * 1024 * 1024


def parse_video_url(url: str) -> tuple[str, int] | None:
    """只接受 B 站官方影片頁網址；避免解析假冒網域或任意使用者 URL。"""
    try:
        parsed = urlparse((url or "").strip())
        if parsed.scheme != "https" or parsed.hostname not in {
            "www.bilibili.com", "m.bilibili.com", "bilibili.com"
        }:
            return None
        match = _VIDEO_PATH.match(parsed.path)
        if not match:
            return None
        pages = parse_qs(parsed.query).get("p", ["1"])
        p = int(pages[0])
        if not 1 <= p <= 1000:
            raise ValueError("Bilibili 分 P 必須在 1–1000 之間。")
        return match.group(1), p
    except (TypeError, AttributeError):
        return None
    except ValueError as exc:
        raise ValueError("Bilibili 連結的分 P 參數無效。") from exc


def transcript_cache_key(bvid: str, page: int) -> str:
    if not _BVID.fullmatch(bvid) or not 1 <= page <= 1000:
        raise ValueError("Bilibili 影片識別碼或分 P 無效。")
    return f"{_CACHE_PREFIX}{bvid}:p{page}"


# Bilibili API 的錯誤碼（公開文件與實際回應整理）；未列出的碼仍會附在訊息中方便回報
_API_CODES = {
    -404: "Bilibili 找不到這支影片，可能已刪除或網址有誤。",
    62002: "這支 Bilibili 影片目前不可見（已下架或僅限特定使用者）。",
    62004: "這支 Bilibili 影片仍在審核中，暫時無法讀取。",
    -403: "Bilibili 拒絕存取這支影片（權限不足或需要登入）。",
    -412: "Bilibili 暫時攔截了這個請求（短時間請求過多或被風控），請稍後再試。",
    -352: "Bilibili 要求額外的安全驗證，目前無法以匿名方式讀取。",
}


def _api_json(path: str, params: dict, referer: str) -> dict:
    try:
        response = requests.get(
            f"https://api.bilibili.com{path}", params=params,
            headers={**_HEADERS, "Referer": referer}, timeout=15,
        )
    except requests.RequestException as exc:
        raise ValueError("無法連線到 Bilibili（網路、Proxy 或防火牆問題），請確認網路後重試。") from exc
    if response.status_code == 412:
        raise ValueError(_API_CODES[-412])
    if response.status_code >= 400:
        raise ValueError(f"Bilibili 服務回應 HTTP {response.status_code}，請稍後重試。")
    try:
        result = response.json()
    except ValueError as exc:
        raise ValueError("Bilibili 回應格式無法解析，請稍後重試。") from exc
    if not isinstance(result, dict):
        raise ValueError("Bilibili 回應格式無法解析，請稍後重試。")
    code = result.get("code")
    if code != 0:
        raise ValueError(_API_CODES.get(code, f"Bilibili 回應失敗（錯誤碼 {code}），影片可能受地區、權限或流量限制。"))
    return result.get("data") or {}


def _subtitle_url(url: str) -> str:
    """CDN URL 必須是 HTTPS 且屬於 Bilibili 字幕供應網域，避免 SSRF。"""
    if not isinstance(url, str) or not url:
        raise ValueError("Bilibili 字幕網址無效。")
    full = "https:" + url if url.startswith("//") else url
    parsed = urlparse(full)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host.endswith(".hdslb.com") or host == "hdslb.com"
        or host.endswith(".bilibili.com") or host == "bilibili.com"
    ):
        raise ValueError("Bilibili 字幕來源網域未被允許。")
    return full


def _load_subtitle(url: str, referer: str) -> list[dict]:
    endpoint = _subtitle_url(url)
    try:
        # 拒絕重導向，以免字幕 CDN 被利用去請求任意內網位置。
        response = requests.get(endpoint, headers={**_HEADERS, "Referer": referer},
                                timeout=20, allow_redirects=False)
        response.raise_for_status()
        if response.status_code in (301, 302, 303, 307, 308):
            raise ValueError("Bilibili 字幕來源轉址，無法安全讀取。")
        if len(response.content) > _MAX_SUBTITLE_BYTES:
            raise ValueError("Bilibili 字幕檔案超過大小限制。")
        payload = response.json()
    except requests.RequestException as exc:
        raise ValueError("Bilibili 字幕下載失敗或遭到限制。") from exc
    except ValueError as exc:
        if "Bilibili" in str(exc):
            raise
        raise ValueError("Bilibili 字幕內容無法解析。") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), list):
        raise ValueError("Bilibili 字幕格式不正確。")
    return payload["body"]


def fetch_transcript(bvid: str, page: int = 1) -> tuple[str, bool]:
    key = transcript_cache_key(bvid, page)
    hit = cache.get(key)
    if hit is not None:
        return hit

    referer = f"https://www.bilibili.com/video/{bvid}/"
    detail = _api_json("/x/web-interface/view", {"bvid": bvid}, referer)
    pages = detail.get("pages") or []
    if not isinstance(pages, list) or not 1 <= page <= len(pages):
        raise ValueError(f"Bilibili 影片沒有第 {page} 個分 P，請確認連結。")
    cid = pages[page - 1].get("cid")
    if not isinstance(cid, int) or cid <= 0:
        raise ValueError("Bilibili 未提供有效的影片 CID。")

    player = _api_json("/x/player/v2", {"bvid": bvid, "cid": cid}, referer)
    subtitles = (player.get("subtitle") or {}).get("subtitles") or []
    if not subtitles:
        if player.get("need_login_subtitle"):
            raise ValueError("這支 Bilibili 影片的字幕需要登入才能讀取；AstraTube 不讀取帳號 Cookie。"
                             "如果你有權使用這支影片的字幕，可以匯入 SRT／VTT 字幕檔後再按「開始」。")
        raise ValueError("這支 Bilibili 影片沒有可公開取得的字幕；目前不會自動下載影音轉錄。"
                         "如果你有權使用字幕，可以匯入 SRT／VTT 字幕檔後再按「開始」。")

    def rank(item: dict) -> tuple:
        lang = str(item.get("lan") or "").lower()
        order = ["zh-tw", "zh-hant", "zh-cn", "zh-hans", "zh", "ai-zh",
                 "en-us", "en", "ai-en"]
        return (bool(item.get("ai_type")), order.index(lang) if lang in order else len(order))

    subtitle = sorted((s for s in subtitles if isinstance(s, dict)), key=rank)
    if not subtitle:
        raise ValueError("Bilibili 字幕列表無有效項目。")
    chosen = subtitle[0]
    rows = _load_subtitle(chosen.get("subtitle_url"), referer)
    lines = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        try:
            second = float(entry.get("from", 0))
        except (TypeError, ValueError):
            continue
        if not 0 <= second <= 360000:
            continue
        text = html.unescape(str(entry.get("content", ""))).strip()
        if text:
            lines.append(f"[{int(second)}] {text}")
    if not lines:
        raise ValueError("Bilibili 提供的字幕內容為空，無法進行分析。")
    result = ("\n".join(lines), str(chosen.get("lan", "")).lower().startswith(("zh", "ai-zh")))
    cache.put(key, *result)
    return result
