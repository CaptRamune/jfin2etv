"""Unit tests for orchestrator helpers (channel discovery)."""

from __future__ import annotations

from pathlib import Path

from jfin2etv.orchestrator import discover_channels


def test_discover_channels_sorts_by_name(tmp_path: Path):
    (tmp_path / "02").mkdir()
    (tmp_path / "02" / "main.rb").write_text("# empty", encoding="utf-8")
    (tmp_path / "01").mkdir()
    (tmp_path / "01" / "main.rb").write_text("# empty", encoding="utf-8")
    (tmp_path / "no-scripts").mkdir()  # ignored
    entries = discover_channels(tmp_path)
    names = [e[0] for e in entries]
    assert names == ["01", "02"]
    assert all(len(e[1]) == 1 for e in entries)


def test_discover_channels_ignores_missing_dir():
    assert discover_channels("/nonexistent-path-xyz") == []
