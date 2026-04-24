"""Tests for output writers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import jsonschema
from lxml import etree

from jfin2etv.output import (
    merge_xmltv_files,
    render_channel_config,
    render_channel_xmltv,
    render_lineup_config,
    render_playout,
    write_playout,
)
from jfin2etv.output.lineup import LineupEntry
from jfin2etv.planner import PlanAST, expand_day
from jfin2etv.planner.expander import EpgProgramme, build_resolved_pools
from jfin2etv.planner.fillers import PlayableItem
from jfin2etv.schemas import load_vendored_schema
from jfin2etv.time_utils import NANOS_PER_SECOND, load_tz

NY = load_tz("America/New_York")


PLAN_JSON = {
    "schema_version": "jfin2etv-plan/1",
    "channel": {
        "number": "01", "name": "Test", "tuning": "01", "icon": None, "language": "en",
        "transcode": {
            "ffmpeg": {"ffmpeg_path": "ffmpeg", "ffprobe_path": "ffprobe", "disabled_filters": [], "preferred_filters": []},
            "video": {"format": "h264", "width": 1920, "height": 1080, "bitrate_kbps": 4000, "buffer_kbps": 8000, "bit_depth": 8, "accel": None, "deinterlace": False, "tonemap_algorithm": None, "vaapi_device": None, "vaapi_driver": None},
            "audio": {"format": "aac", "bitrate_kbps": 160, "buffer_kbps": 320, "channels": 2, "sample_rate_hz": 48000, "normalize_loudness": False, "loudness": None},
            "playout": {"virtual_start": None},
        },
    },
    "collections": {
        "rock": {"expression": 'library:"X" AND type:music_video', "mode": "shuffle", "sort": None, "memory_window": None, "weight_field": None},
    },
    "fillers": {"fallback": {"kind": "local", "path": "/media/slug.mkv"}},
    "layouts": {
        "video_block": {
            "steps": [{"op": "main"}, {"op": "fill", "with": ["fallback"]}],
            "epg": {"granularity": "per_item", "title": "from_main", "description": None, "category": None},
        },
    },
    "schedule": {
        "blocks": [{
            "at": "00:00", "collection": "rock", "layout": "video_block",
            "count": None, "on": None, "align_seconds": 1800, "epg_overrides": None,
            "variants": None, "variant_selector": None,
        }],
        "default_block": {"collection": "rock", "layout": "video_block", "align_seconds": None},
    },
}


def _items(n: int, seconds: int) -> list[dict]:
    return [
        {"Id": f"r-{i}", "Name": f"Video {i}", "Type": "MusicVideo",
         "Path": f"/m/{i}.mkv", "RunTimeTicks": seconds * 10_000_000,
         "Overview": "Some description."}
        for i in range(n)
    ]


def test_playout_json_validates_against_vendored_schema(tmp_path: Path):
    plan = PlanAST.model_validate(PLAN_JSON)
    pools = build_resolved_pools(
        collections={"rock": _items(100, 180)},
        filler_local={"fallback": PlayableItem(source_type="local", path="/media/slug.mkv", duration_nanos=1 * NANOS_PER_SECOND)},
    )
    exp = expand_day(plan, date(2026, 4, 24), pools, NY)
    doc = render_playout(exp.items)
    schema = load_vendored_schema("playout.json")
    jsonschema.validate(doc, schema)
    out = write_playout(exp.items, tmp_path / "channels" / "01" / "playout")
    assert out.exists() and out.name.endswith(".json")
    parsed = json.loads(out.read_text())
    assert parsed["version"].endswith("0.0.1")


def test_channel_config_validates(tmp_path: Path):
    plan = PlanAST.model_validate(PLAN_JSON)
    doc = render_channel_config(plan.channel, "/config/channels/01/playout/")
    schema = load_vendored_schema("channel_config.json")
    jsonschema.validate(doc, schema)


def test_lineup_config_validates():
    doc = render_lineup_config(
        [LineupEntry(number="01", name="Test", config="/config/channels/01/channel.json")],
        output_folder="/tmp/hls",
    )
    schema = load_vendored_schema("lineup_config.json")
    jsonschema.validate(doc, schema)


def test_xmltv_renders_and_parses(tmp_path: Path):
    plan = PlanAST.model_validate(PLAN_JSON)
    from datetime import datetime
    progs = [
        EpgProgramme(
            start=datetime(2026, 4, 24, 20, 0, tzinfo=NY),
            finish=datetime(2026, 4, 24, 20, 30, tzinfo=NY),
            title="Video 0",
            description="hello",
            category=None,
            block_anchor="20:00",
        ),
    ]
    data = render_channel_xmltv(plan.channel, progs)
    path = tmp_path / "01.xml"
    path.write_bytes(data)
    doc = etree.parse(str(path))
    assert doc.getroot().tag == "tv"
    titles = doc.getroot().xpath("//title/text()")
    assert titles == ["Video 0"]


def test_merge_xmltv_files(tmp_path: Path):
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    plan = PlanAST.model_validate(PLAN_JSON)
    from datetime import datetime
    p = EpgProgramme(
        start=datetime(2026, 4, 24, 10, 0, tzinfo=NY),
        finish=datetime(2026, 4, 24, 10, 30, tzinfo=NY),
        title="X", description=None, category=None, block_anchor="10:00",
    )
    a.write_bytes(render_channel_xmltv(plan.channel, [p]))
    b.write_bytes(render_channel_xmltv(plan.channel, [p]))
    out = merge_xmltv_files([a, b], tmp_path / "merged.xml")
    doc = etree.parse(str(out))
    assert len(doc.getroot().findall("programme")) == 2
