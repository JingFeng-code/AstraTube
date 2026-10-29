"""使用者持有的 SRT/VTT 字幕；綁定官方影片 ID，保存真正的毫秒起訖時間。

目前為單機工作區資料。對外提供服務前需先加入身分驗證與使用者隔離。
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.transcript import bilibili

CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "imported_subtitles"
MAX_FILE_BYTES = 1024 * 1024
MAX_CUES = 6000
MAX_SECONDS = 360000
MAX_TEXT_LENGTH = 800
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TIME = re.compile(r"(?:(\d{1,3}):)?(\d{2}):(\d{2})[,.](\d{1,3})")
_FORMATS = {".srt", ".vtt"}


def target_from_url(url: str) -> tuple[str, str, int]:
    """只接受官方 URL，避免將字幕綁到惡意站或任意外部資源。"""
    parsed = urlsplit((url or "").strip())
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("請貼上 HTTPS YouTube 或 Bilibili 官方影片網址。")
    if parsed.hostname in {"www.bilibili.com", "m.bilibili.com", "bilibili.com"}:
        target = bilibili.parse_video_url(url)
        if not target:
            raise ValueError("Bilibili 影片網址格式無效。")
        return "bilibili", target[0], target[1]
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        raise ValueError("僅支援 YouTube 或 Bilibili 官方影片網址。")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/")
    elif parsed.path == "/watch":
        videos = parse_qs(parsed.query).get("v", [])
        video_id = videos[0] if len(videos) == 1 else ""
    else:
        match = re.fullmatch(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})/?", parsed.path)
        if match:
            video_id = match.group(1)
    if not _YOUTUBE_ID.fullmatch(video_id):
        raise ValueError("YouTube 影片網址沒有有效的影片 ID。")
    return "youtube", video_id, 1


def validate_identity(platform: str, video_id: str, page: int) -> None:
    if platform == "youtube":
        if not _YOUTUBE_ID.fullmatch(video_id) or page != 1:
            raise ValueError("YouTube 影片 ID 或分集無效。")
    elif platform == "bilibili":
        bilibili.transcript_cache_key(video_id, page)
    else:
        raise ValueError("不支援的影片平台。")


def _file_path(platform: str, video_id: str, page: int) -> Path:
    validate_identity(platform, video_id, page)
    digest = hashlib.sha256(f"imported-srt-vtt-v1:{platform}:{video_id}:p{page}".encode()).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _seconds(value: str) -> float:
    match = _TIME.fullmatch(value.strip())
    if not match:
        raise ValueError("字幕時間格式錯誤：請使用 00:00:01,250 或 00:01.250。")
    hours, minutes, seconds, milliseconds = match.groups()
    mm, ss = int(minutes), int(seconds)
    if mm >= 60 or ss >= 60:
        raise ValueError("字幕時間欄位超過 59。")
    time = int(hours or "0") * 3600 + mm * 60 + ss + int(milliseconds.ljust(3, "0")) / 1000
    if time > MAX_SECONDS:
        raise ValueError("字幕時間超過支援的影片長度。")
    return round(time, 3)


def parse_subtitle_file(filename: str, content: str) -> tuple[str, list[dict]]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in _FORMATS:
        raise ValueError("只能匯入 .srt 或 .vtt 字幕檔。")
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("字幕檔案不可超過 1 MB。")
    text = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if suffix == ".vtt" and not text.startswith("WEBVTT"):
        raise ValueError("VTT 字幕必須以 WEBVTT 開頭。")
    if not text:
        raise ValueError("字幕檔案沒有文字內容。")
    cues: list[dict] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines()]
        if not lines:
            continue
        if lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        cue_idx = next((idx for idx, line in enumerate(lines) if "-->" in line), None)
        if cue_idx is None:
            continue
        timing = lines[cue_idx].split("-->")
        if len(timing) != 2:
            raise ValueError("字幕時間軸無法解析。")
        start = _seconds(timing[0])
        end = _seconds(timing[1].strip().split()[0])
        if end <= start:
            raise ValueError("字幕結束時間必須晚於開始時間。")
        raw_text = " ".join(lines[cue_idx + 1:]).strip()
        # WebVTT 格式標籤只作為字幕標記，顯示時不渲染 HTML。
        clean = html.unescape(re.sub(r"<[^>\n]{1,120}>", "", raw_text)).strip()
        if not clean:
            continue
        if len(clean) > MAX_TEXT_LENGTH:
            raise ValueError("單句字幕不可超過 800 字。")
        cues.append({"start": start, "end": end, "text": clean, "translation": None})
        if len(cues) > MAX_CUES:
            raise ValueError("字幕超過 6000 句，請先拆分檔案。")
    if not cues:
        raise ValueError("找不到有效的字幕時間軸與內容。")
    cues.sort(key=lambda cue: (cue["start"], cue["end"]))
    return suffix[1:], cues


def transcript_from_cues(cues: list[dict]) -> str:
    """沿用現有摘要與問答的逐字稿契約，不改動既有模型 prompt。"""
    return "\n".join(f"[{int(cue['start'])}] {cue['text']}" for cue in cues)


def save(platform: str, video_id: str, page: int, filename: str, content: str) -> dict:
    fmt, cues = parse_subtitle_file(filename, content)
    path = _file_path(platform, video_id, page)
    # 只根據字幕內容猜測；不會將全部原文強制簡繁轉換。
    total = sum(len(cue["text"]) for cue in cues)
    chinese = sum(sum("\u3400" <= char <= "\u9fff" for char in cue["text"]) for cue in cues)
    payload = {
        "format": fmt, "cues": cues, "is_chinese": chinese > total * 0.2,
        "version": 1, "platform": platform, "video_id": video_id, "page": page,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # 原子替換，避免程式中斷時把之前成功匯入的字幕寫壞。
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CACHE_DIR,
                                     prefix=".import-", suffix=".tmp", delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        temp_path = Path(tmp.name)
    try:
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return payload


def load(platform: str, video_id: str, page: int = 1) -> dict | None:
    path = _file_path(platform, video_id, page)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("version") != 1 or data.get("platform") != platform
                or data.get("video_id") != video_id or data.get("page") != page
                or not isinstance(data.get("cues"), list) or not data["cues"]):
            return None
        return data
    except (OSError, TypeError, ValueError, AttributeError):
        return None


def delete(platform: str, video_id: str, page: int = 1) -> bool:
    path = _file_path(platform, video_id, page)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
