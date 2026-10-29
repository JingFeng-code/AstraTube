"""Packaged AstraTube FastAPI sidecar.

The desktop launcher supplies a fresh session token, a loopback port and a
per-user data directory. Do not expose this executable as a shared HTTP server.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

# 桌面程式（Tauri）意外結束時，後端最多在這段時間內自行退出，不留背景行程。
PARENT_POLL_SECONDS = 2.0


def process_alive(pid: int) -> bool:
    """確認指定行程是否仍在執行；Windows 不可用 os.kill(pid, 0)（那會直接結束行程）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        synchronize, query_limited = 0x00100000, 0x1000
        handle = kernel32.OpenProcess(synchronize | query_limited, False, pid)
        if not handle:
            # 拒絕存取代表行程存在但權限不同；其他錯誤（找不到行程）代表已結束。
            return ctypes.get_last_error() == 5
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT：仍在執行
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(pid: int, interval: float = PARENT_POLL_SECONDS) -> threading.Thread:
    """背景監看啟動本後端的桌面程式；它不在了就立即結束，避免殘留行程佔用埠與檔案。

    PyInstaller onefile 在 Windows 會多一層啟動行程，Tauri 結束時只保證停掉外層；
    Tauri 當掉時也不會執行正常的關閉流程，所以由後端自己確認。
    """
    def loop() -> None:
        while process_alive(pid):
            time.sleep(interval)
        os._exit(0)

    thread = threading.Thread(target=loop, name="astratube-parent-watch", daemon=True)
    thread.start()
    return thread


def main() -> None:
    token = os.environ.get("ASTRA_DESKTOP_TOKEN", "")
    raw_port = os.environ.get("ASTRA_DESKTOP_PORT", "")
    data_dir = os.environ.get("ASTRA_DESKTOP_DATA_DIR", "")
    if len(token) < 32 or not raw_port.isdigit() or not data_dir:
        print("Desktop launcher configuration is missing.", file=sys.stderr)
        raise SystemExit(2)
    port = int(raw_port)
    if not 1024 <= port <= 65535:
        raise SystemExit(2)
    data_path = Path(data_dir).resolve()
    data_path.mkdir(parents=True, exist_ok=True)
    raw_parent = os.environ.get("ASTRA_DESKTOP_PARENT_PID", "")
    if raw_parent:
        if not raw_parent.isdigit() or not process_alive(int(raw_parent)):
            print("Desktop launcher is not running.", file=sys.stderr)
            raise SystemExit(2)
        watch_parent(int(raw_parent))
    # Import app only after the session/data environment is available.
    import uvicorn
    from app.main import app as application
    uvicorn.run(application, host="127.0.0.1", port=port, reload=False,
                workers=1, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
