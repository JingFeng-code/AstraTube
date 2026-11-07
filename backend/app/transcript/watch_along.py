"""陪看模式：使用者在 AstraTube 裡播放官方嵌入播放器時，邊播邊記下聲音和畫面。

- 聲音：只擷取 AstraTube 自己（含 WebView2 子程式）播出的聲音，交給本機 SenseVoice。
- 畫面：只擷取 AstraTube 視窗裡播放器那一塊，畫面有變化時交給本機 Ollama 視覺模型。
- 不下載影片檔，也不呼叫雲端；擷取到的畫面和聲音只在記憶體中處理，不寫入硬碟。
結束時把字幕和【畫面】筆記存成這支影片的字幕，之後沿用既有的分析流程。
"""
from __future__ import annotations

import base64
import io
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from app.core import config, messages
from app.core.zh import to_traditional
from app.llm import ollama
from app.transcript import imported_subtitles, local_speech

SAMPLE_RATE = local_speech.SAMPLE_RATE
_FRAME_INTERVAL = 2.0       # 多久看一次畫面有沒有變
_MIN_GAP = 8.0              # 兩張畫面筆記至少間隔幾秒
_MAX_GAP = 90.0             # 畫面幾乎不變時，最久多久還是記一次
_CHANGE = 10.0              # 縮圖平均差異超過多少才算換畫面
_STALE_FRAMES = 10.0        # 有人在說話、畫面卻這麼久沒更新，多半是視窗被縮小
_AUDIBLE = 0.002            # 平均音量超過這個值才算有聲音；暫停時畫面不更新是正常的
_GAP = 0.3                  # 聲音中斷超過這麼久，就補一段靜音讓語音分段在這裡斷開
_GAP_FILL = 1.0             # 補的靜音最多幾秒：足以讓 VAD 斷句，又不會讓記憶體隨暫停時間增加
_VISION_PROMPT = {
    "zh-Hant": "這是影片播放器目前的畫面。請用繁體中文簡短記下畫面上對理解內容有幫助的資訊："
               "投影片或標題的文字、程式碼、圖表數值、操作步驟。只有人物在說話、沒有其他資訊時，只回覆「無」。",
    "en": "This is the current frame of a video player. Briefly note anything that helps understand the content: "
          "slide or title text, code, chart values, on-screen steps. If it only shows someone talking, reply only \"none\".",
}


def target_pid() -> int | None:
    """桌面版是啟動後端的 AstraTube 主程式；開發時可用環境變數指定瀏覽器的程式編號。"""
    for name in ("ASTRA_WATCH_TARGET_PID", "ASTRA_DESKTOP_PARENT_PID"):
        raw = os.environ.get(name, "")
        if raw.isdigit():
            return int(raw)
    return None


def capture_supported() -> bool:
    if sys.platform != "win32" or not target_pid():
        return False
    try:
        import comtypes  # noqa: F401
        import windows_capture  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def vision_models(base: str | None = None) -> list[str]:
    """只列出本機已安裝、而且 Ollama 回報支援看圖的模型；雲端模型一律排除。"""
    url = base or ollama.base_url()
    found = []
    try:
        names = ollama.list_models()
        with httpx.Client(timeout=httpx.Timeout(5.0), trust_env=False, follow_redirects=False) as client:
            for name in names:
                response = client.post(url + "/api/show", json={"model": name})
                if response.status_code == 200 and "vision" in (response.json().get("capabilities") or []):
                    found.append(name)
    except Exception:  # noqa: BLE001  沒開 Ollama 時只記錄聲音
        return []
    return found


def describe_frame(model: str, image) -> str:
    """把一張畫面交給本機 Ollama；回傳空字串代表畫面沒有值得記的內容。"""
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    language = "en" if config.get("OUTPUT_LANGUAGE") == "en" else "zh-Hant"
    body = {"model": model, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": 300},
            "messages": [{"role": "user", "content": _VISION_PROMPT[language],
                          "images": [base64.b64encode(buffer.getvalue()).decode()]}]}
    with httpx.Client(timeout=httpx.Timeout(120.0), trust_env=False, follow_redirects=False) as client:
        response = client.post(ollama.base_url() + "/api/chat", json=body)
        response.raise_for_status()
        text = " ".join(((response.json().get("message") or {}).get("content") or "").split())
    return "" if text.strip("。.「」\"' ").lower() in ("無", "none", "") else text


def frame_changed(previous, current) -> float:
    """兩張 64×36 灰階縮圖的平均差異；沒有上一張時視為完全不同。"""
    import numpy as np
    if previous is None:
        return 255.0
    return float(np.abs(current.astype("float32") - previous.astype("float32")).mean())


def thumbnail(rgb):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.fromarray(rgb).convert("L").resize((64, 36)))


def clock_time(wall: float, heartbeats: list[tuple[float, float]], started: float, offset: float) -> float:
    """把擷取當下的時間換成影片時間。

    YouTube 會回報播放進度：用最近一次回報往後推，暫停、拖曳進度都對得上。
    Bilibili 讀不到進度：只能從開始陪看的那一刻往後算，中途拖曳會對不準。
    """
    past = [beat for beat in heartbeats if beat[0] <= wall]
    if past:
        at, position = past[-1]
        return max(0.0, position + (wall - at))
    if heartbeats:
        at, position = heartbeats[0]
        return max(0.0, position - (at - wall))
    return max(0.0, offset + wall - started)


@dataclass
class Session:
    platform: str
    video_id: str
    page: int
    region: dict
    offset: float = 0.0
    vision_model: str | None = None
    state: str = "running"
    started: float = field(default_factory=time.time)
    cues: list = field(default_factory=list)
    visuals: list = field(default_factory=list)
    heartbeats: list = field(default_factory=list)
    warnings: set = field(default_factory=set)
    last_frame_wall: float = 0.0
    last_audio_wall: float = 0.0
    last_loud_wall: float = 0.0
    error: str = ""

    def status(self) -> dict:
        language = config.get("OUTPUT_LANGUAGE")
        recent = sorted([(c["start"], to_traditional(c["text"], language)) for c in self.cues[-4:]] +
                        [(v["t"], "【畫面】" + to_traditional(v["text"], language)) for v in self.visuals[-2:]])[-5:]
        return {"state": self.state, "platform": self.platform, "video_id": self.video_id, "page": self.page,
                "elapsed": round(time.time() - self.started), "cue_count": len(self.cues),
                "visual_count": len(self.visuals), "vision_model": self.vision_model,
                "warnings": sorted(self.warnings), "error": self.error,
                "recent": [{"t": round(t, 1), "text": text[:120]} for t, text in recent]}


class Recorder:
    """一次陪看的工作；聲音、畫面、看圖各用一條執行緒。來源都可以替換，方便測試。"""

    def __init__(self, session: Session, pid: int, audio_factory: Callable | None = None,
                 frames_factory: Callable | None = None, recognize: Callable | None = None,
                 describe: Callable | None = None):
        self.session = session
        self.pid = pid
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.audio_factory = audio_factory or _process_audio
        self.frames_factory = frames_factory or _window_frames
        self.recognize = recognize or local_speech.recognize
        self.describe = describe or describe_frame
        self.pending: queue.Queue = queue.Queue(maxsize=1)
        self.threads = [threading.Thread(target=self._audio_loop, name="watch-audio", daemon=True)]
        if session.vision_model:
            self.threads += [threading.Thread(target=self._frame_loop, name="watch-frames", daemon=True),
                             threading.Thread(target=self._vision_loop, name="watch-vision", daemon=True)]

    def start(self) -> None:
        for thread in self.threads:
            thread.start()

    def heartbeat(self, position: float) -> None:
        with self.lock:
            self.session.heartbeats.append((time.time(), float(position)))
            del self.session.heartbeats[:-200]

    def set_region(self, region: dict) -> None:
        with self.lock:
            self.session.region = region

    def _video_time(self, wall: float) -> float:
        with self.lock:
            beats = list(self.session.heartbeats)
        return round(clock_time(wall, beats, self.session.started, self.session.offset), 3)

    # ── 聲音 ──
    def _audio_loop(self) -> None:
        import numpy as np
        try:
            source = self.audio_factory(self.pid)
            vad, window = local_speech.new_vad()
        except Exception as exc:  # noqa: BLE001
            local_speech._log("陪看聲音無法開始", exc)
            self._fail(messages.t("watch.audio_failed"))
            return
        marks: list[tuple[int, float]] = []   # (第幾個樣本, 收到時的時間)
        total = 0
        pending = np.zeros(0, dtype=np.float32)

        def wall_of(sample: int) -> float:
            mark = max((m for m in marks if m[0] <= sample), default=marks[0] if marks else (0, time.time()))
            return mark[1] + (sample - mark[0]) / SAMPLE_RATE

        def drain() -> None:
            while not vad.empty():
                segment = vad.front
                tokens, stamps = self.recognize(segment.samples)
                wall = wall_of(segment.start)
                start = self._video_time(wall)
                end = start + len(segment.samples) / SAMPLE_RATE
                cues = local_speech.build_cues(tokens, stamps, start, end)
                with self.lock:
                    self.session.cues.extend(cues)
                vad.pop()

        last_end = None

        try:
            while not self.stop_event.is_set():
                data = source.read(200)
                if not data:
                    continue
                chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768
                now = time.time()
                chunk_start = now - chunk.size / SAMPLE_RATE
                # Windows 在目標沒有聲音時不送資料（例如暫停）。前後兩段若直接接在一起，
                # VAD 會把它們當成同一句，後段的時間就會被算早；補一段靜音讓它在這裡斷句。
                if last_end is not None and chunk_start - last_end > _GAP:
                    silence = np.zeros(int(min(_GAP_FILL, chunk_start - last_end) * SAMPLE_RATE), dtype=np.float32)
                    marks.append((total, last_end))
                    total += silence.size
                    pending = np.concatenate((pending, silence))
                last_end = now
                marks.append((total, chunk_start))
                del marks[:-500]
                total += chunk.size
                self.session.last_audio_wall = now
                if float(np.abs(chunk).mean()) > _AUDIBLE:
                    self.session.last_loud_wall = now
                pending = np.concatenate((pending, chunk))
                usable = pending.size - pending.size % window
                for start in range(0, usable, window):
                    vad.accept_waveform(pending[start:start + window])
                    drain()
                pending = pending[usable:]
                # 擷取只在畫面有變時送來；影片在播（有聲音）卻一直沒有新畫面，才是視窗被縮小
                if (self.session.vision_model and now - self.session.last_loud_wall < 2
                        and now - max(self.session.last_frame_wall, self.session.started) > _STALE_FRAMES):
                    self.session.warnings.add("frames_stalled")
            if pending.size:
                vad.accept_waveform(pending)
            vad.flush()
            drain()
        except Exception as exc:  # noqa: BLE001
            local_speech._log("陪看聲音中斷", exc)
            self._fail(messages.t("watch.audio_failed"))
        finally:
            try:
                source.close()
            except Exception:  # noqa: BLE001
                pass

    # ── 畫面 ──
    def _frame_loop(self) -> None:
        source: dict = {}
        last_check = [0.0]
        last_key = [0.0]
        previous = [None]

        def on_frame(rgb) -> None:
            now = time.time()
            self.session.last_frame_wall = now
            self.session.warnings.discard("frames_stalled")
            if now - last_check[0] < _FRAME_INTERVAL or self.stop_event.is_set():
                return
            last_check[0] = now
            if "frames" not in source:
                return
            with self.lock:
                region = dict(self.session.region)
            box = source["frames"](region, rgb.shape[1], rgb.shape[0])
            if not box:
                return
            image = rgb[box[1]:box[3], box[0]:box[2]]
            small = thumbnail(image)
            change = frame_changed(previous[0], small)
            since = now - last_key[0]
            if since >= _MIN_GAP and (change >= _CHANGE or (since >= _MAX_GAP and change >= 2)):
                previous[0] = small
                last_key[0] = now
                from PIL import Image
                picture = Image.fromarray(image)
                picture.thumbnail((1280, 720))
                try:
                    self.pending.get_nowait()   # 看圖跟不上時只留最新的一張
                except queue.Empty:
                    pass
                self.pending.put_nowait((now, picture))

        try:
            source["frames"] = self.frames_factory(self.pid, on_frame)
        except Exception as exc:  # noqa: BLE001
            local_speech._log("陪看畫面無法開始", exc)
            self.session.warnings.add("frames_unavailable")
            return
        self.stop_event.wait()
        source["frames"].close()

    def _vision_loop(self) -> None:
        while True:
            try:
                wall, picture = self.pending.get(timeout=0.5)
            except queue.Empty:
                if self.stop_event.is_set():
                    return
                continue
            try:
                text = self.describe(self.session.vision_model, picture)
            except Exception as exc:  # noqa: BLE001
                local_speech._log("看圖失敗", exc)
                self.session.warnings.add("vision_failed")
                continue
            if text:
                position = self._video_time(wall)  # 先算好再上鎖：_video_time 自己也要鎖
                with self.lock:
                    self.session.visuals.append({"t": position, "text": text[:600]})

    def _fail(self, message: str) -> None:
        self.session.state = "error"
        self.session.error = message
        self.stop_event.set()

    def stop(self, timeout: float = 150.0) -> bool:
        """回傳是否全部處理完；看圖請求最久 120 秒，所以多等一點。"""
        self.stop_event.set()
        deadline = time.time() + timeout
        for thread in self.threads:
            thread.join(max(0.1, deadline - time.time()))
        return not any(thread.is_alive() for thread in self.threads)


def audio_pid(pid: int) -> int:
    """找出實際播放聲音的程式。

    桌面版的畫面由 WebView2 負責，聲音從它的瀏覽器程序（以及底下的音訊程序）播出。
    雖然 WebView2 看起來是 AstraTube 的子程序，Windows 錄程序聲音時卻不把它算進
    AstraTube 的程序樹，直接錄 AstraTube 只會錄到靜音；所以改錄 AstraTube 底下的
    WebView2 瀏覽器程序（不帶 --type= 參數的那一個）。找不到時（例如開發時直接指定
    瀏覽器）就用原本的程式編號。
    """
    try:
        import psutil
        for child in psutil.Process(pid).children():
            try:
                if child.name().lower() != "msedgewebview2.exe":
                    continue
                if not any(arg.startswith("--type=") for arg in child.cmdline()):
                    return child.pid
            except psutil.Error:
                continue
    except Exception as exc:  # noqa: BLE001
        local_speech._log("找不到 WebView2 程序，改錄主程式", exc)
    return pid


def _process_audio(pid: int):
    sys.coinit_flags = 0  # comtypes 在匯入的執行緒用 MTA，聲音啟用的回呼才不需要訊息迴圈
    import comtypes
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except OSError:
        pass
    from app.capture.process_loopback import ProcessLoopback
    return ProcessLoopback(audio_pid(pid), SAMPLE_RATE)


class _Frames:
    def __init__(self, capture, region_box):
        self.capture = capture
        self.region_box = region_box

    def __call__(self, region, width, height):
        return self.region_box(region, width, height)

    def close(self):
        self.capture.close()


def _window_frames(pid: int, on_frame: Callable):
    from app.capture import window_capture
    window_capture.make_dpi_aware()
    hwnd = window_capture.find_main_window(pid)
    if not hwnd:
        raise RuntimeError("window not found")
    capture = window_capture.WindowFrames(hwnd, on_frame)
    # 每次都重新讀外框：使用者陪看時可能調整視窗大小或最大化
    return _Frames(capture, lambda region, width, height: window_capture.crop_box(
        region, window_capture.client_offset(hwnd), (width, height)))


# ── 對外 ─────────────────────────────────────────────────

_lock = threading.Lock()
_current: dict = {}


def status() -> dict:
    with _lock:
        recorder = _current.get("recorder")
    return recorder.session.status() if recorder else {"state": "idle"}


def start(platform: str, video_id: str, page: int, region: dict, offset: float, **factories) -> dict:
    imported_subtitles.validate_identity(platform, video_id, page)
    with _lock:
        recorder = _current.get("recorder")
        if recorder and recorder.session.state == "running":
            raise ValueError(messages.t("watch.busy"))
        pid = factories.pop("pid", None) or target_pid()
        if not pid:
            raise ValueError(messages.t("watch.desktop_only"))
        models = factories.pop("models", None)
        models = vision_models() if models is None else models
        preferred = (config.get("WATCH_VISION_MODEL") or "").strip()
        model = preferred if preferred in models else (models[0] if models else None)
        session = Session(platform, video_id, page, region, offset, model)
        if not model:
            session.warnings.add("no_vision_model")
        recorder = Recorder(session, pid, **factories)
        _current["recorder"] = recorder
    recorder.start()
    return session.status()


def heartbeat(position: float) -> None:
    with _lock:
        recorder = _current.get("recorder")
    if recorder and recorder.session.state == "running":
        recorder.heartbeat(position)


def set_region(region: dict) -> None:
    with _lock:
        recorder = _current.get("recorder")
    if recorder:
        recorder.set_region(region)


def finish() -> dict:
    """停止擷取並存成字幕；要等最後一段語音和畫面處理完。"""
    with _lock:
        recorder = _current.get("recorder")
    if not recorder or recorder.session.state not in ("running", "error"):
        raise ValueError(messages.t("watch.not_running"))
    session = recorder.session
    failed = session.state == "error"
    session.state = "finishing"
    if not recorder.stop():
        # 最後一段還在辨識或看圖：先不存，避免存到不完整的內容；再按一次結束就會接著等
        session.state = "running"
        session.error = messages.t("watch.still_processing")
        return session.status()
    session.error = "" if not failed else session.error
    language = config.get("OUTPUT_LANGUAGE")
    cues = sorted(({**cue, "text": to_traditional(cue["text"], language)} for cue in session.cues),
                  key=lambda cue: (cue["start"], cue["end"]))
    visuals = sorted(({"t": v["t"], "text": to_traditional(v["text"], language)} for v in session.visuals),
                     key=lambda item: item["t"])
    if not cues:
        session.state = "error"
        session.error = session.error if failed else messages.t("watch.nothing_heard")
        return session.status()
    imported_subtitles.save_cues(session.platform, session.video_id, session.page, "watch",
                                 local_speech._fit_cue_limit(cues), visuals=visuals)
    session.state = "done"
    return session.status()


def cancel() -> dict:
    with _lock:
        recorder = _current.pop("recorder", None)
    if recorder:
        recorder.session.state = "cancelled"
        recorder.stop(timeout=5)
        return recorder.session.status()
    return {"state": "idle"}
