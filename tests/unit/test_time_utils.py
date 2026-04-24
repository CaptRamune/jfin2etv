"""Tests for time_utils."""

from __future__ import annotations

from datetime import datetime

from jfin2etv.time_utils import (
    Duration,
    add_nanos,
    ceil_to_next,
    diff_nanos,
    floor_to_midnight,
    format_iso_compact,
    format_iso_nanos,
    load_tz,
)

NY = load_tz("America/New_York")


def test_duration_arithmetic():
    a = Duration.from_seconds(1)
    b = Duration.from_ms(500)
    assert (a + b).total_ms == 1500
    assert Duration.from_jellyfin_ticks(10_000_000).total_seconds == 1.0


def test_floor_to_midnight():
    instant = datetime(2026, 4, 24, 13, 30, 0, tzinfo=NY)
    m = floor_to_midnight(instant, NY)
    assert m.year == 2026 and m.month == 4 and m.day == 24
    assert m.hour == 0 and m.minute == 0


def test_ceil_to_next_half_hour():
    # 20:05 → 20:30; 20:30 → 20:30 (already on grid); 20:31 → 21:00
    a = datetime(2026, 4, 24, 20, 5, 0, tzinfo=NY)
    assert ceil_to_next(a, 1800, NY).minute == 30
    b = datetime(2026, 4, 24, 20, 30, 0, tzinfo=NY)
    assert ceil_to_next(b, 1800, NY) == b
    c = datetime(2026, 4, 24, 20, 31, 0, tzinfo=NY)
    res = ceil_to_next(c, 1800, NY)
    assert res.hour == 21 and res.minute == 0


def test_format_iso_nanos_round_trip_micro():
    instant = datetime(2026, 4, 24, 20, 0, 0, 123456, tzinfo=NY)
    out = format_iso_nanos(instant)
    assert "2026-04-24T20:00:00.123456000" in out
    assert out.endswith(("-04:00", "-05:00"))  # DST-sensitive


def test_format_iso_compact():
    instant = datetime(2026, 4, 24, 0, 0, 0, tzinfo=NY)
    out = format_iso_compact(instant)
    assert out.startswith("20260424T000000.000000000")


def test_add_nanos_and_diff_nanos_preserves_sub_microsecond():
    instant = datetime(2026, 4, 24, 20, 0, 0, tzinfo=NY)
    plus = add_nanos(instant, 1_234_567_890)  # 1.23s + 567,890 ns
    d = diff_nanos(plus, instant)
    assert d == 1_234_567_890
