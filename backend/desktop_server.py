"""Packaged AstraTube FastAPI sidecar.

The desktop launcher supplies a fresh session token, a loopback port and a
per-user data directory. Do not expose this executable as a shared HTTP server.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


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
    # Import app only after the session/data environment is available.
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False,
                workers=1, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
