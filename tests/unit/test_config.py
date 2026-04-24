"""Tests for Config loader."""

from __future__ import annotations

from pathlib import Path

from jfin2etv.config import load_config


def test_load_defaults_when_missing(tmp_path: Path):
    missing = tmp_path / "nope.yml"
    cfg = load_config(missing)
    assert cfg.jellyfin.url == "http://jellyfin:8096"
    assert cfg.scheduler.run_time == "04:00"


def test_load_with_overrides(tmp_path: Path):
    yml = tmp_path / "j.yml"
    yml.write_text(
        """
jellyfin:
  url: http://jelly.local:9000
scheduler:
  run_time: "03:30"
  channels_in_parallel: 5
""".strip()
    )
    cfg = load_config(yml)
    assert cfg.jellyfin.url == "http://jelly.local:9000"
    assert cfg.scheduler.run_time == "03:30"
    assert cfg.scheduler.channels_in_parallel == 5


def test_env_url_overrides_file(monkeypatch, tmp_path: Path):
    yml = tmp_path / "j.yml"
    yml.write_text("jellyfin:\n  url: http://from-yaml\n")
    monkeypatch.setenv("JELLYFIN_URL", "http://from-env")
    cfg = load_config(yml)
    assert cfg.jellyfin.url == "http://from-env"
