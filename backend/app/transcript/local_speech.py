"""本地影片的本機語音轉文字：SenseVoice（sherpa-onnx）＋ Silero VAD，只用 CPU。

影片只傳到這台電腦上的後端，處理完就刪除，不會送到任何雲端服務。
模型不隨程式發布：使用者按下才下載，並比對固定的 SHA-256，內容不符就不採用。
引擎套件很大，CI 與一般 API 路徑都不需要，所以全部延遲匯入。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

import requests

from app.core import config, messages
from app.core.zh import to_traditional
from app.transcript import imported_subtitles

_DATA = Path(os.environ["ASTRA_DESKTOP_DATA_DIR"]) if os.environ.get("ASTRA_DESKTOP_DATA_DIR") else Path(__file__).resolve().parents[3]
MODEL_DIR = _DATA / ".cache" / "speech_model"
UPLOAD_DIR = _DATA / ".cache" / "local_video_tmp"
MODEL_NAME = "SenseVoiceSmall"

_HF = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/2365baeacb507f821a0c8120fcee3d484dba7a07"
# (檔名, 下載網址, SHA-256, 位元組數)
MODEL_FILES = (
    ("model.int8.onnx", f"{_HF}/model.int8.onnx",
     "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51", 239233841),
    ("tokens.txt", f"{_HF}/tokens.txt",
     "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc", 315894),
    ("silero_vad.onnx", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
     "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6", 643854),
)
MODEL_BYTES = sum(item[3] for item in MODEL_FILES)

SAMPLE_RATE = 16000
_MAX_SPEECH_SECONDS = 20
_BREAK = frozenset("。！？!?…；;")
_SOFT_BREAK = frozenset("，,、：:")
# 字幕長度以中文字寬計算：英數字約半個字寬，同樣長度可以放比較多字
_SOFT_LENGTH = 14
_MAX_LENGTH = 40


class SpeechError(ValueError):
    """訊息已是給使用者看的文字；原始例外只留在後端紀錄。"""


def _log(stage: str, detail: object) -> None:
    # 訊息可能含本機路徑與使用者名稱，只能留在後端紀錄
    print(f"[speech] {stage}：{str(detail)[-500:]!a}", flush=True)


def engine_available() -> bool:
    try:
        import av  # noqa: F401
        import sherpa_onnx  # noqa: F401
        return True
    except Exception as exc:  # noqa: BLE001  打包缺 DLL 時不一定是 ImportError
        _log("語音引擎無法載入", exc)
        return False


def model_ready() -> bool:
    try:
        return all((MODEL_DIR / name).stat().st_size == size for name, _, _, size in MODEL_FILES)
    except OSError:
        return False


# ── 模型下載 ─────────────────────────────────────────────

_download_lock = threading.Lock()
_download = {"state": "idle", "done": 0, "error": ""}
_download_cancel = threading.Event()


def download_status() -> dict:
    with _download_lock:
        return dict(_download, total=MODEL_BYTES)


def _set_download(**changes) -> None:
    with _download_lock:
        _download.update(changes)


def _fetch_file(name: str, url: str, digest: str, base_done: int) -> None:
    target = MODEL_DIR / name
    partial = MODEL_DIR / f"{name}.part"
    sha = hashlib.sha256()
    done = 0
    try:
        with requests.get(url, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            with open(partial, "wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    if _download_cancel.is_set():
                        raise InterruptedError
                    out.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    _set_download(done=base_done + done)
        if sha.hexdigest() != digest:
            raise SpeechError(messages.t("speech.model_mismatch"))
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _run_download() -> None:
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        done = 0
        for name, url, digest, size in MODEL_FILES:
            target = MODEL_DIR / name
            if not (target.exists() and target.stat().st_size == size):
                _fetch_file(name, url, digest, done)
            done += size
            _set_download(done=done)
        _set_download(state="idle", done=MODEL_BYTES, error="")
    except InterruptedError:
        _set_download(state="idle", done=0, error="")
    except SpeechError as exc:
        _set_download(state="error", error=str(exc))
    except (requests.RequestException, OSError) as exc:
        _log("模型下載失敗", exc)
        _set_download(state="error", error=messages.t("speech.model_download_failed"))


def start_model_download() -> dict:
    with _download_lock:
        running = _download["state"] == "downloading"
        if not running and not model_ready():
            _download.update(state="downloading", done=0, error="")
            _download_cancel.clear()
            threading.Thread(target=_run_download, name="speech-model", daemon=True).start()
    return download_status()


def cancel_model_download() -> dict:
    _download_cancel.set()
    return download_status()


# ── 字幕切句 ─────────────────────────────────────────────

def _width(text: str) -> float:
    return sum(0.5 if char.isascii() else 1 for char in text)


def build_cues(tokens: list[str], timestamps: list[float], offset: float, end: float) -> list[dict]:
    """把模型輸出的字元與時間切成適合閱讀的字幕；標點或長度到了就斷句。"""
    groups: list[tuple[float, str]] = []
    text = ""
    start = None
    for token, stamp in zip(tokens, timestamps):
        piece = token.replace("▁", " ")
        if piece.startswith("<|"):
            continue
        # 長度上限剛好切在句尾時，標點要跟著前一句，不能自己變成一句字幕
        if start is None and groups and piece.strip() and piece.strip()[0] in _BREAK | _SOFT_BREAK:
            groups[-1] = (groups[-1][0], groups[-1][1] + piece.strip())
            continue
        if start is None:
            start = stamp
        text += piece
        last = piece.strip()[-1:] or " "
        width = _width(text.strip())
        if last in _BREAK or (last in _SOFT_BREAK and width >= _SOFT_LENGTH) or width >= _MAX_LENGTH:
            groups.append((start, text.strip()))
            text, start = "", None
    if text.strip() and start is not None:
        groups.append((start, text.strip()))
    cues = []
    for index, (stamp, words) in enumerate(groups):
        begin = round(offset + stamp, 3)
        finish = round(offset + groups[index + 1][0], 3) if index + 1 < len(groups) else round(end, 3)
        if words:
            cues.append({"start": begin, "end": max(finish, round(begin + 0.2, 3)), "text": words, "translation": None})
    return cues


def _fit_cue_limit(cues: list[dict]) -> list[dict]:
    """字幕檔有句數上限；太長的影片把相鄰字幕合併，不丟內容。"""
    while len(cues) > imported_subtitles.MAX_CUES:
        merged = []
        for index in range(0, len(cues), 2):
            pair = cues[index:index + 2]
            merged.append({**pair[0], "end": pair[-1]["end"],
                           "text": " ".join(cue["text"] for cue in pair)[:imported_subtitles.MAX_TEXT_LENGTH]})
        cues = merged
    return cues


# ── 轉文字 ───────────────────────────────────────────────

_recognizer = None
_recognizer_lock = threading.Lock()


def _thread_count() -> int:
    return max(1, min(8, (os.cpu_count() or 4) // 2))


def _get_recognizer():
    global _recognizer
    with _recognizer_lock:
        if _recognizer is None:
            import sherpa_onnx
            _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(MODEL_DIR / "model.int8.onnx"), tokens=str(MODEL_DIR / "tokens.txt"),
                num_threads=_thread_count(), use_itn=True, language="auto")
        return _recognizer


def _pcm_chunks(container, stream) -> Iterator:
    import av
    resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
    for frame in container.decode(stream):
        for out in resampler.resample(frame):
            yield out.to_ndarray().reshape(-1)
    for out in resampler.resample(None):
        yield out.to_ndarray().reshape(-1)


def transcribe_file(path: Path, on_progress: Callable[[float], None], cancelled: Callable[[], bool]) -> list[dict]:
    """解碼影片音軌並逐段辨識；邊讀邊處理，長影片也不會把整段音訊放進記憶體。"""
    import av
    import numpy as np
    import sherpa_onnx

    try:
        recognizer = _get_recognizer()
        settings = sherpa_onnx.VadModelConfig()
        settings.silero_vad.model = str(MODEL_DIR / "silero_vad.onnx")
        settings.silero_vad.min_silence_duration = 0.25
        settings.silero_vad.max_speech_duration = _MAX_SPEECH_SECONDS
        settings.sample_rate = SAMPLE_RATE
        vad = sherpa_onnx.VoiceActivityDetector(settings, buffer_size_in_seconds=_MAX_SPEECH_SECONDS * 3)
    except Exception as exc:  # noqa: BLE001
        _log("語音模型載入失敗", exc)
        raise SpeechError(messages.t("speech.engine_failed")) from exc

    cues: list[dict] = []

    def drain() -> None:
        while not vad.empty():
            segment = vad.front
            stream = recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, segment.samples)
            recognizer.decode_stream(stream)
            result = stream.result
            offset = segment.start / SAMPLE_RATE
            cues.extend(build_cues(list(result.tokens), list(result.timestamps), offset,
                                   offset + len(segment.samples) / SAMPLE_RATE))
            vad.pop()

    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise SpeechError(messages.t("speech.no_audio"))
            audio = container.streams.audio[0]
            total = (container.duration or 0) / av.time_base
            window = settings.silero_vad.window_size
            pending = np.zeros(0, dtype=np.float32)
            heard = 0
            for chunk in _pcm_chunks(container, audio):
                if cancelled():
                    raise InterruptedError
                pending = np.concatenate((pending, chunk)) if pending.size else chunk
                usable = pending.size - pending.size % window
                for start in range(0, usable, window):
                    vad.accept_waveform(pending[start:start + window])
                    drain()
                pending = pending[usable:]
                heard += chunk.size
                if total > 0:
                    on_progress(min(0.99, heard / SAMPLE_RATE / total))
            if pending.size:
                vad.accept_waveform(pending)
            vad.flush()
            drain()
    except (SpeechError, InterruptedError):
        raise
    except Exception as exc:  # noqa: BLE001
        _log("影片解碼或語音辨識失敗", exc)
        raise SpeechError(messages.t("speech.decode_failed")) from exc
    if not cues:
        raise SpeechError(messages.t("whisper.no_speech"))
    language = config.get("OUTPUT_LANGUAGE")
    for cue in cues:
        cue["text"] = to_traditional(cue["text"], language)
    return _fit_cue_limit(cues)


# ── 工作 ─────────────────────────────────────────────────

_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_ACTIVE = ("uploading", "running")


def job_status(video_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(video_id)
        if not job:
            return {"state": "idle", "progress": 0, "cue_count": 0, "error": ""}
        return {key: job[key] for key in ("state", "progress", "cue_count", "error")}


def begin_upload(video_id: str) -> Path:
    """同一時間只處理一支影片：語音辨識會吃滿 CPU，也避免暫存檔互相佔用硬碟。"""
    with _jobs_lock:
        if any(job["state"] in _ACTIVE for job in _jobs.values()):
            raise SpeechError(messages.t("speech.busy"))
        _jobs[video_id] = {"state": "uploading", "progress": 0, "cue_count": 0, "error": "",
                           "cancel": threading.Event()}
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for stale in UPLOAD_DIR.glob("*.video"):  # 上次當機留下的暫存檔
        stale.unlink(missing_ok=True)
    return UPLOAD_DIR / f"{video_id}-{secrets.token_hex(8)}.video"


def abort_upload(video_id: str, path: Path) -> None:
    path.unlink(missing_ok=True)
    with _jobs_lock:
        _jobs.pop(video_id, None)


def _update_job(video_id: str, **changes) -> None:
    with _jobs_lock:
        if video_id in _jobs:
            _jobs[video_id].update(changes)


def _run_job(video_id: str, path: Path, cancel: threading.Event) -> None:
    started = time.time()
    try:
        cues = transcribe_file(path, lambda value: _update_job(video_id, progress=value), cancel.is_set)
        imported_subtitles.save_cues("local", video_id, 1, "asr", cues)
        _update_job(video_id, state="done", progress=1, cue_count=len(cues))
        print(f"[speech] 完成：{len(cues)} 句，耗時 {time.time() - started:.1f}s", flush=True)
    except InterruptedError:
        _update_job(video_id, state="cancelled", progress=0)
    except SpeechError as exc:
        _update_job(video_id, state="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _log("語音轉文字失敗", exc)
        _update_job(video_id, state="error", error=messages.t("speech.engine_failed"))
    finally:
        path.unlink(missing_ok=True)


def start_job(video_id: str, path: Path) -> None:
    with _jobs_lock:
        job = _jobs[video_id]
        job["state"] = "running"
        cancel = job["cancel"]
    threading.Thread(target=_run_job, args=(video_id, path, cancel), name="speech-job", daemon=True).start()


def cancel_job(video_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(video_id)
        if job:
            job["cancel"].set()
    return job_status(video_id)


def has_room_for(size: int) -> bool:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # 多留 1 GB，避免暫存影片把系統碟塞滿
    return shutil.disk_usage(UPLOAD_DIR).free > size + 1024 ** 3
