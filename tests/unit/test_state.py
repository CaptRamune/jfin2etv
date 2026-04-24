"""Tests for the per-channel SQLite state store."""

from __future__ import annotations

from pathlib import Path

from jfin2etv.state import (
    StateStore,
    expression_sha,
    pick_random_with_memory,
    pick_sequential,
    pick_weighted_random,
)


def test_creates_schema(tmp_path: Path):
    db = tmp_path / "channel-01.sqlite"
    with StateStore(db):
        pass
    assert db.exists()


def test_cursor_auto_reset_on_expression_change(tmp_path: Path):
    db = tmp_path / "channel-02.sqlite"
    h1 = expression_sha("type:movie")
    h2 = expression_sha("type:episode")
    with StateStore(db) as s:
        s.get_or_init_cursor("rock", h1)
        s.set_cursor("rock", 7)
    with StateStore(db) as s:
        assert s.get_or_init_cursor("rock", h1) == 7  # same hash → kept
    with StateStore(db) as s:
        assert s.get_or_init_cursor("rock", h2) == 0  # different → reset


def test_recent_plays_pruning_and_last_n(tmp_path: Path):
    db = tmp_path / "channel-03.sqlite"
    from datetime import datetime, timedelta

    with StateStore(db) as s:
        s.record_play("c", "a", datetime.now() - timedelta(days=40))
        s.record_play("c", "b", datetime.now() - timedelta(days=1))
        s.record_play("c", "c", datetime.now())
        assert s.last_n_ids("c", 5) == {"a", "b", "c"}
        deleted = s.prune_recent_plays(older_than_days=30)
        assert deleted == 1
        assert s.last_n_ids("c", 5) == {"b", "c"}


def test_run_markers(tmp_path: Path):
    db = tmp_path / "channel-04.sqlite"
    with StateStore(db) as s:
        s.start_run("R1", notes="first")
        s.finish_run("R1", outcome="ok", items_written=100, notes="done")
    with StateStore(db) as s:
        last = s.last_run()
    assert last is not None
    assert last["run_id"] == "R1"
    assert last["outcome"] == "ok"
    assert last["items_written"] == 100


def test_pick_sequential_wraps():
    items = [{"Id": "a"}, {"Id": "b"}, {"Id": "c"}]
    item, cur = pick_sequential(items, cursor=5)
    assert item["Id"] == "c"
    assert cur == 0  # (2+1) % 3 = 0 (wraps)
    item2, cur2 = pick_sequential(items, cursor=cur)
    assert item2["Id"] == "a"
    assert cur2 == 1


def test_pick_random_with_memory_excludes_recent():
    items = [{"Id": "a"}, {"Id": "b"}, {"Id": "c"}]
    picked = pick_random_with_memory(items, recent_ids={"a", "b"}, seed=0)
    assert picked["Id"] == "c"


def test_pick_weighted_random_deterministic_with_seed():
    items = [{"Id": "a", "w": 1.0}, {"Id": "b", "w": 1000.0}]
    # With massively lopsided weights and a fixed seed the heavy one is
    # overwhelmingly likely to be picked; assert via repeated draws.
    counts = {"a": 0, "b": 0}
    for seed in range(100):
        picked = pick_weighted_random(items, weight_field="w", seed=seed)
        counts[picked["Id"]] += 1
    assert counts["b"] > counts["a"] * 10
