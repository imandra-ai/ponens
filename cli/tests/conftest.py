"""Shared fixtures for E2E tests."""

import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

import pytest

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "app")

# Preferred port for tests; falls back to existing dev server on 3001
PORTS_TO_TRY = [3099, 3001]


def _server_alive(url: str) -> bool:
    try:
        urllib.request.urlopen(f"{url}/api/auth/current-user", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _wait_for_server(url: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_alive(url):
            return True
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def hub_server():
    """Provide a running hub URL. Reuses an existing dev server if found."""
    # Check if a server is already running
    for port in PORTS_TO_TRY:
        url = f"http://localhost:{port}"
        if _server_alive(url):
            yield url
            return

    # Start one ourselves. If the app/npm isn't available (e.g. the standalone
    # ponens repo without the TraceHub pilot), skip the hub-dependent E2E tests
    # rather than failing the whole run.
    port = PORTS_TO_TRY[0]
    url = f"http://localhost:{port}"
    try:
        proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(port)],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        pytest.skip("npm/app not available; skipping hub-dependent E2E tests")
    if not _wait_for_server(url):
        proc.terminate()
        pytest.skip("TraceHub server did not start; skipping hub-dependent E2E tests")

    yield url

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(autouse=True)
def set_hub_env(hub_server, monkeypatch):
    """Point the CLI at the test hub server."""
    monkeypatch.setenv("TRACEHUB_URL", hub_server)
