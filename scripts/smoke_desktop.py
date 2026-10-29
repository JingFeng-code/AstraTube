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


def request(url: str, token: str = "") -> int:
    headers = {"X-Astra-Desktop-Token": token} if token else {}
    try:
        with urlopen(Request(url, headers=headers), timeout=2) as response:
            response.read()
            return response.status
    except HTTPError as exc:
        return exc.code


def main(binary: Path) -> None:
    if not binary.is_file():
        raise SystemExit(f"Packaged desktop backend not found: {binary}")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = secrets.token_hex(32)
    with tempfile.TemporaryDirectory() as data_dir:
        env = {**os.environ, "ASTRA_DESKTOP_TOKEN":token,
               "ASTRA_DESKTOP_PORT":str(port),
               "ASTRA_DESKTOP_DATA_DIR":data_dir,
               "AUTO_RUN_CLI":"0"}
        with tempfile.TemporaryFile() as log:
            proc = subprocess.Popen([str(binary.resolve())], env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                root = f"http://127.0.0.1:{port}"
                for attempt in range(90):
                    if proc.poll() is not None:
                        raise RuntimeError("Packaged backend exited prematurely.")
                    try:
                        if request(root+"/health",token)==200:
                            break
                    except (URLError, TimeoutError, OSError):
                        pass
                    time.sleep(0.4)
                else:
                    raise RuntimeError("Packaged backend did not become healthy.")
                assert request(root+"/health")==403, "Missing token must be rejected"
                assert request(root+"/settings")==403, "Settings must require a token"
                assert request(root+"/settings",token)==200, "Authenticated settings must work"
                print("Windows desktop backend smoke test passed")
            except Exception:
                log.seek(0)
                print(log.read().decode("utf-8",errors="replace")[-4000:],file=sys.stderr)
                raise
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=8)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
