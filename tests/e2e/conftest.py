"""Pytest fixtures that spin up real Jellyfin + ErsatzTV-Next containers."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

E2E_DIR = Path(__file__).parent
COMPOSE_FILE = E2E_DIR / "docker-compose.yml"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001
        return False
    return True


@pytest.fixture(scope="session")
def docker_stack():
    if not _docker_available():
        pytest.skip("docker not available on this runner")
    if os.environ.get("JFIN2ETV_E2E") != "1":
        pytest.skip("set JFIN2ETV_E2E=1 to run end-to-end tests")

    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        check=True,
    )

    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            r = httpx.get("http://127.0.0.1:18096/System/Info/Public", timeout=2)
            if r.status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    else:
        subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"])
        pytest.fail("Jellyfin did not become healthy within 5 minutes")

    yield {
        "jellyfin_url": "http://127.0.0.1:18096",
        "ersatztv_url": "http://127.0.0.1:18409",
    }

    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"])
