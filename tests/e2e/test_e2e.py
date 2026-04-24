"""End-to-end tests against real Jellyfin + ErsatzTV-Next containers.

These tests are slow by design. Enable with:
    JFIN2ETV_E2E=1 JELLYFIN_API_KEY=... pytest -m slow tests/e2e
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from lxml import etree

from jfin2etv.schemas import load_vendored_schema

pytestmark = pytest.mark.slow


def _iter_playout_jsons(root: Path):
    yield from root.rglob("*.json")


def test_playout_validates_against_schema(docker_stack, tmp_path):
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        pytest.skip("set JELLYFIN_API_KEY to run e2e tests")

    from jfin2etv.cli import main as cli_main
    from click.testing import CliRunner

    scripts = tmp_path / "scripts" / "01"
    scripts.mkdir(parents=True)
    (scripts / "main.rb").write_text(
        'channel number: "01", name: "E2E", tuning: "01.1"\n'
        'collection :all, "type:movie", mode: :shuffle\n'
        "layout :default do\n"
        "  main\n"
        "end\n"
        "schedule do\n"
        "  default_block layout: :default, collection: :all\n"
        "end\n"
    )

    env_vars = {
        "JELLYFIN_URL": docker_stack["jellyfin_url"],
        "JELLYFIN_API_KEY": api_key,
        "JFIN2ETV_CONFIG": str(tmp_path / "jfin2etv.yml"),
    }
    (tmp_path / "jfin2etv.yml").write_text(
        f"scripts_dir: {scripts.parent}\n"
        f"state_dir: {tmp_path / 'state'}\n"
        f"ersatztv:\n  config_dir: {tmp_path / 'etv'}\n"
        f"epg:\n  merged_output: {tmp_path / 'epg.xml'}\n"
        f"  per_channel_output_dir: {tmp_path / 'epg-per'}\n"
    )

    runner = CliRunner(env=env_vars)
    result = runner.invoke(cli_main, ["once", "--force"])
    assert result.exit_code == 0, result.output

    schema = load_vendored_schema("playout.json")
    validator = Draft202012Validator(schema)
    found = False
    for path in _iter_playout_jsons(tmp_path / "etv"):
        if path.name.endswith("playout.json") or "playout" in str(path):
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
            assert not errors, f"{path}: {[e.message for e in errors]}"
            found = True
    assert found, "no playout JSON produced"


def test_xmltv_validates_against_dtd(tmp_path):
    xmltv_path = tmp_path / "epg.xml"
    if not xmltv_path.exists():
        pytest.skip("previous test did not produce xmltv")

    dtd_path = Path(__file__).parent / "fixture" / "xmltv.dtd"
    if not dtd_path.exists():
        pytest.skip("xmltv.dtd fixture not available")
    dtd = etree.DTD(str(dtd_path))
    tree = etree.parse(str(xmltv_path))
    assert dtd.validate(tree), dtd.error_log.filter_from_errors()
