"""Planner unit tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from jfin2etv.planner import PlanAST, expand_day
from jfin2etv.planner.alignment import target_end
from jfin2etv.planner.expander import build_resolved_pools
from jfin2etv.planner.fillers import (
    PlayableItem,
    auto_break_budgets,
    fill_budget_draining,
    fill_budget_looped,
)
from jfin2etv.time_utils import NANOS_PER_SECOND, load_tz

NY = load_tz("America/New_York")


# ----- alignment -------------------------------------------------------------


def test_target_end_rounds_up_to_align():
    datetime(2026, 4, 24, 20, 0, tzinfo=NY)
    natural = datetime(2026, 4, 24, 20, 35, tzinfo=NY)
    end = target_end(natural, None, 1800, NY)
    assert end.hour == 21 and end.minute == 0


def test_target_end_clips_to_next_anchor():
    natural = datetime(2026, 4, 24, 21, 5, tzinfo=NY)
    anchor = datetime(2026, 4, 24, 21, 0, tzinfo=NY)
    end = target_end(natural, anchor, 1800, NY)
    assert end == anchor


# ----- fillers ---------------------------------------------------------------


def test_fill_budget_looped_trims_last():
    item = PlayableItem(source_type="local", path="/x.mkv", duration_nanos=3 * NANOS_PER_SECOND)
    out = fill_budget_looped(item, budget_nanos=7 * NANOS_PER_SECOND)
    total = sum(i.duration_nanos for i in out)
    assert total == 7 * NANOS_PER_SECOND
    assert out[-1].out_point_ms == 1000  # trimmed to 1s


def test_fill_budget_looped_no_trim_leaves_residual():
    # Non-last pools in a `fill with: [...]` list must not trim — they emit
    # whole copies and hand any residual to the next pool.
    item = PlayableItem(source_type="local", path="/x.mkv", duration_nanos=3 * NANOS_PER_SECOND)
    out = fill_budget_looped(item, budget_nanos=7 * NANOS_PER_SECOND, allow_trim_last=False)
    total = sum(i.duration_nanos for i in out)
    assert total == 6 * NANOS_PER_SECOND  # 2 whole copies, 1s residual unfilled
    assert all(i.out_point_ms is None for i in out)


def test_fill_budget_draining_stops_when_out():
    pool = [
        PlayableItem(source_type="local", path="/a.mkv", duration_nanos=3 * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/b.mkv", duration_nanos=5 * NANOS_PER_SECOND),
    ]
    out = fill_budget_draining(pool, budget_nanos=4 * NANOS_PER_SECOND)
    # First item consumed whole (3s), second truncated to 1s.
    assert len(out) == 2
    assert out[1].duration_nanos == 1 * NANOS_PER_SECOND


def test_fill_budget_draining_no_trim_leaves_residual():
    pool = [
        PlayableItem(source_type="local", path="/a.mkv", duration_nanos=3 * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/b.mkv", duration_nanos=5 * NANOS_PER_SECOND),
    ]
    out = fill_budget_draining(pool, budget_nanos=4 * NANOS_PER_SECOND, allow_trim_last=False)
    # First item consumed whole (3s); second wouldn't fit, so we stop without
    # trimming — the 1s residual is left for a downstream pool.
    assert len(out) == 1
    assert out[0].duration_nanos == 3 * NANOS_PER_SECOND
    assert out[0].out_point_ms is None


def test_fill_budget_draining_skips_oversized_to_pack_more():
    # An oversized item early in the pool must NOT short-circuit the scan —
    # smaller items later in the pool should still be considered.
    pool = [
        PlayableItem(source_type="local", path="/big.mkv",    duration_nanos=10 * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/small1.mkv", duration_nanos=2  * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/small2.mkv", duration_nanos=3  * NANOS_PER_SECOND),
    ]
    out = fill_budget_draining(pool, budget_nanos=5 * NANOS_PER_SECOND, allow_trim_last=False)
    assert [i.path for i in out] == ["/small1.mkv", "/small2.mkv"]
    assert sum(i.duration_nanos for i in out) == 5 * NANOS_PER_SECOND
    assert all(i.out_point_ms is None for i in out)


def test_fill_budget_draining_trims_first_oversized_after_packing():
    # With trimming enabled, the scan still skips oversized items to pack
    # the budget, then trims the first oversized item to take any residual.
    pool = [
        PlayableItem(source_type="local", path="/big.mkv",    duration_nanos=10 * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/small1.mkv", duration_nanos=2  * NANOS_PER_SECOND),
        PlayableItem(source_type="local", path="/small2.mkv", duration_nanos=3  * NANOS_PER_SECOND),
    ]
    out = fill_budget_draining(pool, budget_nanos=4 * NANOS_PER_SECOND, allow_trim_last=True)
    # /small1 fits (2s), /small2 doesn't (3 > 2 remaining), /big was the first
    # oversized item — it's trimmed to the 2s residual.
    assert [i.path for i in out] == ["/small1.mkv", "/big.mkv"]
    assert out[-1].duration_nanos == 2 * NANOS_PER_SECOND
    assert out[-1].out_point_ms == 2000


def test_auto_break_budgets_distributes_evenly():
    out = auto_break_budgets(10 * NANOS_PER_SECOND, 2, per_break_target_s=10)
    assert sum(out) == 10 * NANOS_PER_SECOND
    assert out[0] == out[1] == 5 * NANOS_PER_SECOND


# ----- end-to-end day expansion ---------------------------------------------


PLAN_JSON = {
    "schema_version": "jfin2etv-plan/1",
    "channel": {
        "number": "01",
        "name": "Test",
        "tuning": "01",
        "icon": None,
        "language": "en",
        "transcode": {
            "ffmpeg": {"ffmpeg_path": "ffmpeg", "ffprobe_path": "ffprobe", "disabled_filters": [], "preferred_filters": []},
            "video": {"format": "h264", "width": 1920, "height": 1080, "bitrate_kbps": 4000, "buffer_kbps": 8000, "bit_depth": 8, "accel": None, "deinterlace": False, "tonemap_algorithm": None, "vaapi_device": None, "vaapi_driver": None},
            "audio": {"format": "aac", "bitrate_kbps": 160, "buffer_kbps": 320, "channels": 2, "sample_rate_hz": 48000, "normalize_loudness": False, "loudness": None},
            "playout": {"virtual_start": None},
        },
    },
    "collections": {
        "rock": {"expression": 'library:"X" AND type:music_video', "mode": "shuffle", "sort": None, "memory_window": None, "weight_field": None}
    },
    "fillers": {
        "fallback": {"kind": "local", "path": "/media/slug.mkv"},
    },
    "layouts": {
        "video_block": {
            "steps": [
                {"op": "main"},
                {"op": "fill", "with": ["fallback"]},
            ],
            "epg": {"granularity": "per_item", "title": "from_main", "description": None, "category": None},
        },
    },
    "schedule": {
        "blocks": [
            {"at": "00:00", "collection": "rock", "layout": "video_block",
             "count": None, "on": None, "align_seconds": 1800, "epg_overrides": None,
             "variants": None, "variant_selector": None},
        ],
        "default_block": {"collection": "rock", "layout": "video_block", "align_seconds": None},
    },
}


def _make_items(n: int, seconds: int) -> list[dict]:
    return [
        {"Id": f"rock-{i}", "Name": f"Video {i}", "Type": "MusicVideo",
         "Path": f"/media/rock/{i}.mkv",
         "RunTimeTicks": seconds * 10_000_000}
        for i in range(n)
    ]


def test_expand_day_produces_contiguous_timeline():
    plan = PlanAST.model_validate(PLAN_JSON)
    d = date(2026, 4, 24)
    pools = build_resolved_pools(
        collections={"rock": _make_items(100, 180)},  # 3-minute videos
        filler_local={"fallback": PlayableItem(source_type="local", path="/media/slug.mkv", duration_nanos=1 * NANOS_PER_SECOND)},
    )
    exp = expand_day(plan, d, pools, NY)
    assert exp.items, "expected non-empty expansion"
    # Contiguity: each item's start == previous item's finish.
    for prev, cur in zip(exp.items, exp.items[1:], strict=False):
        assert cur.start == prev.finish, (prev.finish, cur.start)
    # Covers 24h
    first = exp.items[0].start
    last = exp.items[-1].finish
    assert last - first == timedelta(hours=24)


def test_fill_with_ordered_pools_only_last_pool_trims():
    # Regression for `fill with: [:post_roll, :fallback]` where, per
    # DESIGN §8.4, the first pool drains whole items and the *last* pool
    # takes the sub-item trim. A 4-min main + a 2-min looping post_roll
    # in a 30-min slot should leave 24 min of post_roll (12 whole copies)
    # plus a tiny fallback trim — no truncated music videos.
    plan_json = {
        **PLAN_JSON,
        "fillers": {
            "post_roll": {"kind": "local", "path": "/media/mv.mkv"},
            "fallback":  {"kind": "local", "path": "/media/slug.mkv"},
        },
        "layouts": {
            "video_block": {
                "steps": [
                    {"op": "main"},
                    {"op": "fill", "with": ["post_roll", "fallback"]},
                ],
                "epg": {"granularity": "per_item", "title": "from_main", "description": None, "category": None},
            },
        },
        "schedule": {
            "blocks": [
                {"at": "00:00", "collection": "rock", "layout": "video_block",
                 "count": 1, "on": None, "align_seconds": 1800, "epg_overrides": None,
                 "variants": None, "variant_selector": None},
            ],
            "default_block": {"collection": "rock", "layout": "video_block", "align_seconds": 1800},
        },
    }
    plan = PlanAST.model_validate(plan_json)
    d = date(2026, 4, 24)
    # Main 230s + post_roll 120s into a 1800s slot leaves a 1570s gap →
    # 13 whole post_roll copies (1560s) and a 10s fallback trim.
    pools = build_resolved_pools(
        collections={"rock": _make_items(50, 230)},
        filler_local={
            "post_roll": PlayableItem(source_type="local", path="/media/mv.mkv", duration_nanos=120 * NANOS_PER_SECOND),
            "fallback":  PlayableItem(source_type="local", path="/media/slug.mkv", duration_nanos=30 * NANOS_PER_SECOND),
        },
    )
    exp = expand_day(plan, d, pools, NY)
    # The 00:00 anchor's slot is the only one routed through `_expand_block`
    # (and thus the `fill` step). Default-block slots emit raw mains only.
    slot = [s for s in exp.items if s.block_anchor == "00:00"]
    post_roll = [s for s in slot if s.filler_kind == "post_roll"]
    fallbacks = [s for s in slot if s.filler_kind == "fallback"]
    # Every post_roll plays a full 120s — none are trimmed.
    assert post_roll, "expected post_roll items to be emitted"
    for s in post_roll:
        assert (s.finish - s.start).total_seconds() == 120, "post_roll must not be trimmed"
    # Fallback is the trim pool; at least one fallback item lands the boundary.
    assert fallbacks, "expected fallback to take the sub-item trim"


def test_midnight_split_produces_pre_post_halves():
    # Small plan: one item at 23:00 that runs 2 hours (crosses midnight).
    plan_json = dict(PLAN_JSON)
    plan_json = {
        **PLAN_JSON,
        "schedule": {
            "blocks": [
                {"at": "23:00", "collection": "rock", "layout": "video_block",
                 "count": 1, "on": None, "align_seconds": None, "epg_overrides": None,
                 "variants": None, "variant_selector": None},
            ],
            "default_block": {"collection": "rock", "layout": "video_block", "align_seconds": None},
        },
    }
    plan = PlanAST.model_validate(plan_json)
    d = date(2026, 4, 24)
    pools = build_resolved_pools(
        collections={"rock": _make_items(3, 7200)},  # 2h each
        filler_local={"fallback": PlayableItem(source_type="local", path="/media/slug.mkv", duration_nanos=1 * NANOS_PER_SECOND)},
    )
    exp = expand_day(plan, d, pools, NY)
    halves = [s for s in exp.items if s.block_anchor.startswith("23:00")]
    assert any(s.block_anchor.endswith("-pre") for s in halves)
    assert any(s.block_anchor.endswith("-post") for s in halves)
