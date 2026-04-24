"""Smoke tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from jfin2etv.cli import main


def test_version():
    r = CliRunner().invoke(main, ["--version"])
    assert r.exit_code == 0
    assert "version" in r.output.lower()


def test_validate_missing_scripts_dir(tmp_path: Path):
    cfg = tmp_path / "jfin2etv.yml"
    cfg.write_text(
        f"scripts_dir: {tmp_path / 'scripts'!s}\n"
        f"state_dir: {tmp_path / 'state'!s}\n",
        encoding="utf-8",
    )
    r = CliRunner().invoke(main, ["--config", str(cfg), "validate"])
    assert r.exit_code == 0


def test_validate_good_script(tmp_path: Path):
    scripts = tmp_path / "scripts" / "01"
    scripts.mkdir(parents=True)
    (scripts / "main.rb").write_text(
        """
channel number: "01", name: "Test"
collection :c, 'library:"X" AND type:movie', mode: :shuffle
filler :fallback, local: "/media/x.mkv"
layout :l do
  main
  fill with: :fallback
end
schedule do
  block at: "00:00", collection: :c, layout: :l
end
""".strip(),
        encoding="utf-8",
    )
    cfg = tmp_path / "jfin2etv.yml"
    cfg.write_text(
        f"scripts_dir: {tmp_path / 'scripts'!s}\n"
        f"state_dir: {tmp_path / 'state'!s}\n",
        encoding="utf-8",
    )
    r = CliRunner().invoke(main, ["--config", str(cfg), "validate"])
    assert r.exit_code == 0, r.output
    assert "ok: 01" in r.output


def test_plan_emits_ast(tmp_path: Path):
    scripts = tmp_path / "scripts" / "01"
    scripts.mkdir(parents=True)
    (scripts / "main.rb").write_text(
        """
channel number: "01", name: "Test"
collection :c, 'library:"X" AND type:movie', mode: :shuffle
filler :fallback, local: "/media/x.mkv"
layout :l do
  main
  fill with: :fallback
end
schedule do
  block at: "00:00", collection: :c, layout: :l
end
""".strip(),
        encoding="utf-8",
    )
    cfg = tmp_path / "jfin2etv.yml"
    cfg.write_text(
        f"scripts_dir: {tmp_path / 'scripts'!s}\n"
        f"state_dir: {tmp_path / 'state'!s}\n",
        encoding="utf-8",
    )
    r = CliRunner().invoke(main, ["--config", str(cfg), "plan", "--channel", "01"])
    assert r.exit_code == 0, r.output
    assert '"schema_version"' in r.output
