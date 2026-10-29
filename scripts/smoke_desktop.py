"""Smoke-test the PyInstaller sidecar on Windows, including token enforcement."""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url: str, token: str = "", extra: dict | None = None) -> int:
    headers = {"X-Astra-Desktop-Token": token} if token else {}
    headers.update(extra or {})
    try:
        with urlopen(Request(url, headers=headers), timeout=2) as response:
            response.read()
            return response.status
    except HTTPError as exc:
        return exc.code


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_healthy(proc: subprocess.Popen, root: str, token: str) -> None:
    for _ in range(90):
        if proc.poll() is not None:
            raise RuntimeError("Packaged backend exited prematurely.")
        try:
            if request(root+"/health",token)==200:
                return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.4)
    raise RuntimeError("Packaged backend did not become healthy.")


def stopped_answering(root: str, token: str, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            request(root+"/health", token)
        except (URLError, TimeoutError, OSError):
            return True
        time.sleep(0.5)
    return False


def run_backend(binary: Path, data_dir: str, parent_pid: int, log):
    port = free_port()
    token = secrets.token_hex(32)
    env = {**os.environ, "ASTRA_DESKTOP_TOKEN":token,
           "ASTRA_DESKTOP_PORT":str(port),
           "ASTRA_DESKTOP_DATA_DIR":data_dir,
           "ASTRA_DESKTOP_PARENT_PID":str(parent_pid),
           "AUTO_RUN_CLI":"0"}
    proc = subprocess.Popen([str(binary.resolve())], env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    return proc, f"http://127.0.0.1:{port}", token


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


def main(binary: Path) -> None:
    if not binary.is_file():
        raise SystemExit(f"Packaged desktop backend not found: {binary}")
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryFile() as log:
        try:
            proc, root, token = run_backend(binary, data_dir, os.getpid(), log)
            try:
                wait_healthy(proc, root, token)
                assert request(root+"/health")==403, "Missing token must be rejected"
                assert request(root+"/settings")==403, "Settings must require a token"
                assert request(root+"/settings",token)==200, "Authenticated settings must work"
                assert request(root+"/health",token,{"Host":"attacker.example"})==403, \
                    "DNS rebinding Host must be rejected"
                assert request(root+"/health",token,{"Origin":"https://evil.example"})==403, \
                    "Other websites must be rejected even with a token"
            finally:
                stop(proc)

            # 模擬桌面程式當掉：啟動程式消失後，onefile 的外層與內層 Python 都必須停止。
            launcher = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            proc, root, token = run_backend(binary, data_dir, launcher.pid, log)
            try:
                wait_healthy(proc, root, token)
                launcher.kill()
                launcher.wait(timeout=10)
                assert stopped_answering(root, token, 20), \
                    "Backend kept running after the desktop launcher exited"
            finally:
                launcher.kill()
                stop(proc)
            print("Windows desktop backend smoke test passed")
        except Exception:
            log.seek(0)
            print(log.read().decode("utf-8",errors="replace")[-4000:],file=sys.stderr)
            raise


if __name__ == "__main__":
    main(Path(sys.argv[1]))
