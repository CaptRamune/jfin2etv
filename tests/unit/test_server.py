"""Smoke tests for the health/metrics server."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jfin2etv.config import Config
from jfin2etv.server import HealthServer


@pytest.mark.asyncio
async def test_healthz_returns_503_without_runs(tmp_path: Path):
    cfg = Config(
        state_dir=str(tmp_path / "state"),
        scripts_dir=str(tmp_path / "scripts"),
    )
    (tmp_path / "state").mkdir(parents=True)
    s = HealthServer(cfg)
    async with TestClient(TestServer(s.app)) as client:
        r = await client.get("/healthz")
    assert r.status == 503


@pytest.mark.asyncio
async def test_metrics_exposes_text(tmp_path: Path):
    cfg = Config(
        state_dir=str(tmp_path / "state"),
        scripts_dir=str(tmp_path / "scripts"),
    )
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    s = HealthServer(cfg)
    async with TestClient(TestServer(s.app)) as client:
        r = await client.get("/metrics")
        body = await r.text()
    assert r.status == 200
    assert "jfin2etv_channels_configured" in body
