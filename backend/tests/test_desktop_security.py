"""Desktop transport must not leak local settings to a random browser tab."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app

TOKEN = "a" * 48


def test_desktop_token_gate():
    client = TestClient(app, base_url="http://127.0.0.1:8420")
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": TOKEN}):
        assert client.get("/health").status_code == 403
        assert client.get("/settings").status_code == 403
        assert client.get("/health", headers={"X-Astra-Desktop-Token": TOKEN}).status_code == 200
        assert client.get("/settings", headers={"X-Astra-Desktop-Token": TOKEN}).status_code == 200
        assert client.get("/health", headers={"X-Astra-Desktop-Token": "wrong"}).status_code == 403


def test_web_mode_keeps_existing_contract():
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": ""}):
        response = TestClient(app, base_url="http://127.0.0.1:8420").get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_desktop_entry_rejects_missing_credentials():
    from desktop_server import main
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": "", "ASTRA_DESKTOP_PORT": "1234",
                                 "ASTRA_DESKTOP_DATA_DIR": "/tmp/invalid"}, clear=False):
        try:
            main()
            assert False
        except SystemExit as exc:
            assert exc.code == 2


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_process_alive_detects_finished_process():
    import subprocess
    from desktop_server import process_alive
    assert process_alive(os.getpid())
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait(timeout=10)
    assert not process_alive(done.pid)
    assert not process_alive(0)


def test_sidecar_exits_when_desktop_launcher_dies():
    """Tauri 當掉或 PyInstaller onefile 只停掉外層時，後端不得殘留在背景。"""
    import subprocess
    import tempfile
    import time
    backend = Path(__file__).resolve().parents[1]
    launcher = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with tempfile.TemporaryDirectory() as data_dir:
        env = {**os.environ, "ASTRA_DESKTOP_TOKEN": TOKEN, "ASTRA_DESKTOP_PORT": str(_free_port()),
               "ASTRA_DESKTOP_DATA_DIR": data_dir, "ASTRA_DESKTOP_PARENT_PID": str(launcher.pid)}
        sidecar = subprocess.Popen([sys.executable, str(backend / "desktop_server.py")], cwd=backend,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(3)
            assert sidecar.poll() is None, "啟動程式還在時後端應持續執行"
            launcher.kill()
            launcher.wait(timeout=10)
            sidecar.wait(timeout=15)
        finally:
            launcher.kill()
            if sidecar.poll() is None:
                sidecar.kill()
                sidecar.wait(timeout=10)
                raise AssertionError("啟動程式結束後，後端沒有自行退出")


def test_desktop_entry_rejects_dead_launcher():
    import subprocess
    from desktop_server import main
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait(timeout=10)
    with patch.dict(os.environ, {"ASTRA_DESKTOP_TOKEN": TOKEN, "ASTRA_DESKTOP_PORT": "34567",
                                 "ASTRA_DESKTOP_DATA_DIR": str(Path(__file__).parent / ".tmp-desktop"),
                                 "ASTRA_DESKTOP_PARENT_PID": str(done.pid)}):
        try:
            main()
            assert False
        except SystemExit as exc:
            assert exc.code == 2
        finally:
            (Path(__file__).parent / ".tmp-desktop").rmdir()


if __name__ == "__main__":
    test_desktop_token_gate()
    test_web_mode_keeps_existing_contract()
    test_desktop_entry_rejects_missing_credentials()
    test_process_alive_detects_finished_process()
    test_sidecar_exits_when_desktop_launcher_dies()
    test_desktop_entry_rejects_dead_launcher()
    print("Desktop API security tests passed")
