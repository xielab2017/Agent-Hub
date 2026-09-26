"""Double-click start / stop launchers: the stop pair exists for each start launcher and really stops the Hub."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_every_start_launcher_has_a_stop_launcher():
    for start, stop in [("Start Agent Hub.command", "Stop Agent Hub.command"), ("start-agent-hub.bat", "stop-agent-hub.bat"),
                        ("start.sh", "stop.sh")]:
        assert (ROOT / start).is_file() and (ROOT / stop).is_file(), stop
    for bat in ("start-agent-hub.bat", "stop-agent-hub.bat"):
        raw = (ROOT / bat).read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n"), f"{bat} needs CRLF line endings for cmd.exe"
    start_bat = (ROOT / "start-agent-hub.bat").read_text(encoding="utf-8")
    assert "-RedirectStandardError '%ERR_FILE%'" in start_bat  # PowerShell refuses the same file for both


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            import json

            return json.loads(r.read().decode("utf-8"))
    except OSError:
        return None


@pytest.mark.skipif(sys.platform.startswith("win") or not shutil.which("curl"), reason="POSIX launchers need bash + curl")
def test_ctl_start_then_stop_launcher_stops_the_hub():
    from ali.config import VERSION

    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "HERMES_ALI_STATE_DIR": tmp, "HERMES_ALI_PORT": str(port), "HERMES_ALI_HOST": "127.0.0.1",
               "AGENT_HUB_NO_PAUSE": "1"}
        try:
            subprocess.run([str(ROOT / "ctl.sh"), "start"], cwd=ROOT, env=env, check=True, capture_output=True, timeout=60)
            assert (_health(port) or {}).get("version") == VERSION
            out = subprocess.run([str(ROOT / "Stop Agent Hub.command")], cwd=ROOT, env=env, capture_output=True, text=True,
                                 timeout=60)
            assert out.returncode == 0 and "已停止" in out.stdout
            assert _health(port) is None
            again = subprocess.run([str(ROOT / "stop.sh")], cwd=ROOT, env=env, capture_output=True, timeout=60)
            assert again.returncode == 0  # stopping a stopped Hub is fine
        finally:
            subprocess.run([str(ROOT / "ctl.sh"), "stop"], cwd=ROOT, env=env, capture_output=True, timeout=60)


def test_server_starts_when_its_output_is_a_windows_code_page_file():
    """Windows launcher run 36216151908: stdout redirected to a log file used cp1252 and the banner crashed server.py."""
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "ali.log"
        env = {**os.environ, "PYTHONIOENCODING": "cp1252", "HERMES_ALI_STATE_DIR": tmp}
        with open(log, "wb") as fh:
            proc = subprocess.Popen([sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", str(port),
                                     "--no-browser"], stdout=fh, stderr=subprocess.STDOUT, env=env)
        try:
            import time

            for _ in range(60):
                if _health(port) or proc.poll() is not None:
                    break
                time.sleep(0.25)
            assert proc.poll() is None, log.read_text(encoding="utf-8", errors="replace")[-400:]
            assert _health(port)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
