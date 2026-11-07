"""擷取 AstraTube 視窗裡播放器那一塊的畫面（Windows Graphics Capture）。

只擷取指定程式自己的視窗，不擷取整個螢幕；視窗被其他視窗擋住時仍讀得到內容，縮小時則沒有畫面。
"""
from __future__ import annotations

import ctypes
import threading
try:
    from ctypes import wintypes
except ValueError:  # 非 Windows 的 Python 可能無法載入，只會用到裁切計算
    wintypes = None
from typing import Callable


DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _user32():
    # 用到時才載入：裁切計算在 CI（Linux）上也要能測
    return ctypes.WinDLL("user32", use_last_error=True)


def _dwmapi():
    return ctypes.WinDLL("dwmapi")


def make_dpi_aware() -> None:
    """座標要用實際像素，否則高解析度螢幕上的裁切位置會偏掉。"""
    try:
        _user32().SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass


def find_main_window(pid: int, title_hint: str = "AstraTube") -> int | None:
    """只找目標程式自己擁有、標題含 AstraTube 的頂層視窗。

    不能用「程式樹裡最大的視窗」：那可能抓到使用者自己的瀏覽器或其他視窗，把私人畫面送去分析。
    """
    found: list[tuple[int, int]] = []
    user32 = _user32()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # 有 owner 的是對話框之類
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if title_hint in title.value:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append(((rect.right - rect.left) * (rect.bottom - rect.top), hwnd))
        return True

    user32.EnumWindows(visit, 0)
    return max(found)[1] if found else None


def client_offset(hwnd: int) -> tuple[int, int, int, int]:
    """回傳 (內容區相對擷取畫面的 x, y, 擷取畫面寬, 高)；擷取畫面以 DWM 的外框為準。"""
    frame = wintypes.RECT()
    _dwmapi().DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame), ctypes.sizeof(frame))
    origin = wintypes.POINT(0, 0)
    _user32().ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x - frame.left, origin.y - frame.top, frame.right - frame.left, frame.bottom - frame.top


def crop_box(region: dict, offset: tuple[int, int, int, int], frame_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """把網頁座標（CSS 像素 × 縮放比例）換成擷取畫面上的裁切範圍；超出畫面就回傳 None。"""
    dx, dy, bounds_w, bounds_h = offset
    width, height = frame_size
    scale_x = width / bounds_w if bounds_w else 1
    scale_y = height / bounds_h if bounds_h else 1
    ratio = float(region.get("dpr") or 1)
    left = (dx + region["x"] * ratio) * scale_x
    top = (dy + region["y"] * ratio) * scale_y
    right = left + region["width"] * ratio * scale_x
    bottom = top + region["height"] * ratio * scale_y
    box = (max(0, int(left)), max(0, int(top)), min(width, int(right)), min(height, int(bottom)))
    return box if box[2] - box[0] >= 32 and box[3] - box[1] >= 32 else None


class WindowFrames:
    """持續收畫面，每次有新畫面就呼叫 on_frame(RGB 陣列)。"""

    def __init__(self, hwnd: int, on_frame: Callable, interval_ms: int = 1000):
        from windows_capture import WindowsCapture

        self.hwnd = hwnd
        self._capture = WindowsCapture(cursor_capture=False, window_hwnd=hwnd, minimum_update_interval=interval_ms)
        self._closed = threading.Event()

        @self._capture.event
        def on_frame_arrived(frame, control):
            if self._closed.is_set():
                control.stop()
                return
            on_frame(frame.frame_buffer[:, :, 2::-1])

        @self._capture.event
        def on_closed():
            self._closed.set()

        self._control = self._capture.start_free_threaded()

    def close(self) -> None:
        self._closed.set()
        try:
            self._control.stop()
        except Exception:  # noqa: BLE001  視窗已關閉時停止會失敗，不影響結果
            pass
