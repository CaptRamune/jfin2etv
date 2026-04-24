"""Integration-style tests for the Ruby bridge.

Requires `ruby` on PATH; skipped otherwise.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from jfin2etv.ruby_bridge import (
    RubyDslError,
    RubyRuntimeError,
    invoke_plan,
    invoke_variant_selector,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ruby") is None, reason="Ruby not installed on PATH"
)


def _write_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "main.rb"
    script.write_text(body, encoding="utf-8")
    return script


def test_invoke_plan_returns_ast(tmp_path: Path):
    script = _write_script(
        tmp_path,
        """
channel number: "01", name: "Classic Rock"
collection :rock, 'library:"Music" AND type:music_video', mode: :shuffle
filler :fallback, local: "/media/x.mkv"
layout :l do
  main
  fill with: :fallback
end
schedule do
  block at: "00:00", collection: :rock, layout: :l
end
""".strip(),
    )
    ast = invoke_plan("01", [script])
    assert ast["channel"]["number"] == "01"
    assert "rock" in ast["collections"]


def test_dsl_error_exit_code(tmp_path: Path):
    script = _write_script(
        tmp_path,
        """
channel number: "01", name: "X"
schedule do
  block at: "99:99", collection: :c, layout: :l
end
""".strip(),
    )
    with pytest.raises(RubyDslError):
        invoke_plan("01", [script])


def test_runtime_error_exit_code(tmp_path: Path):
    script = _write_script(tmp_path, "raise 'boom'")
    with pytest.raises(RubyRuntimeError):
        invoke_plan("01", [script])


def test_variant_selector_dow():
    src = "->(d) { d.wday == 6 || d.wday == 0 ? :weekends : :weekdays }"
    assert invoke_variant_selector(src, date(2026, 4, 25)) == "weekends"  # Sat
    assert invoke_variant_selector(src, date(2026, 4, 27)) == "weekdays"  # Mon
