"""本機語音轉寫（轉錄瀑布最後一層）：
yt-dlp 下載音訊 → faster-whisper 轉成帶時間戳的逐字稿 → 用完即刪。

加速策略：
  1. 轉寫結果快取（同一支影片第二次直接秒回）
  2. 多執行緒 + 貪婪解碼（beam_size=1）讓第一次也更快
不需要系統 ffmpeg：yt-dlp 抓單一 bestaudio 串流、faster-whisper 用 PyAV 解碼。
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from app.core import config, messages
from app.transcript import cache

_model = None
_model_size: Optional[str] = None


def _get_model():
    """延遲載入 Whisper 模型（第一次會自動下載模型檔）。"""
    global _model, _model_size
    size = (config.get("WHISPER_MODEL") or "large-v3-turbo").strip() or "large-v3-turbo"
    if _model is None or size != _model_size:
        from faster_whisper import WhisperModel
        # CPU + int8 + 用滿執行緒：在一般筆電（含 Apple Silicon）上盡量快
        _model = WhisperModel(size, device="cpu", compute_type="int8",
                              cpu_threads=os.cpu_count() or 4)
        _model_size = size
    return _model


def download_audio(url: str, tmpdir: str) -> str:
    """用 venv 內的 yt-dlp 下載音訊（不含影像），回傳音檔路徑。"""
    out_tmpl = os.path.join(tmpdir, "audio.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best",
           "--no-playlist", "--no-warnings", "-o", out_tmpl, url]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1800)
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip().splitlines()
        tail = msg[-1] if msg else str(e)
        raise ValueError(messages.t("whisper.download_failed", detail=tail))
    except subprocess.TimeoutExpired:
        raise ValueError(messages.t("whisper.download_timeout"))
    files = glob.glob(os.path.join(tmpdir, "audio.*"))
    if not files:
        raise ValueError(messages.t("whisper.audio_missing"))
    return files[0]


def transcribe_file(path: str) -> Tuple[str, bool]:
    """轉寫本機音檔，回傳 (帶時間戳逐字稿, is_chinese)。"""
    model = _get_model()
    # beam_size=1（貪婪）較快；關閉 condition_on_previous_text 避免長音訊重複迴圈
    segments, info = model.transcribe(path, vad_filter=True, beam_size=1,
                                      condition_on_previous_text=False)
    lines = [f"[{int(s.start)}] {(s.text or '').strip()}" for s in segments if (s.text or "").strip()]
    text = "\n".join(lines)
    if not text:
        raise ValueError(messages.t("whisper.no_speech"))
    return text, (getattr(info, "language", "") or "").startswith("zh")


def transcribe_url(url: str, cache_key: Optional[str] = None) -> Tuple[str, bool]:
    """下載音訊→轉寫→清除暫存。回傳 (逐字稿, is_chinese)。
    cache_key 建議用影片 id（同片秒回）；沒給就用 url。"""
    key = cache_key or url
    cached = cache.get(key)
    if cached is not None:
        print(f"[transcribe] 命中快取，直接回傳（{key}）", flush=True)
        return cached

    tmpdir = tempfile.mkdtemp(prefix="ycr_audio_")
    try:
        audio = download_audio(url, tmpdir)
        text, is_chinese = transcribe_file(audio)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    cache.put(key, text, is_chinese)
    return text, is_chinese
