"""Time utilities.

All internal durations are nanosecond-precision integers (DESIGN.md §7.3).
All instants are timezone-aware `datetime` objects carrying UTC offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Final
from zoneinfo import ZoneInfo

NANOS_PER_SECOND: Final[int] = 1_000_000_000
NANOS_PER_MS: Final[int] = 1_000_000
JELLYFIN_TICKS_PER_SECOND: Final[int] = 10_000_000  # 1 tick = 100 ns


@dataclass(frozen=True, slots=True)
class Duration:
    """A duration stored as an integer number of nanoseconds."""

    nanos: int

    @classmethod
    def from_seconds(cls, seconds: float | int) -> "Duration":
        return cls(int(round(float(seconds) * NANOS_PER_SECOND)))

    @classmethod
    def from_ms(cls, ms: float | int) -> "Duration":
        return cls(int(round(float(ms) * NANOS_PER_MS)))

    @classmethod
    def from_jellyfin_ticks(cls, ticks: int) -> "Duration":
        return cls(int(ticks) * 100)

    @property
    def total_seconds(self) -> float:
        return self.nanos / NANOS_PER_SECOND

    @property
    def total_ms(self) -> int:
        return self.nanos // NANOS_PER_MS

    def __add__(self, other: "Duration") -> "Duration":
        return Duration(self.nanos + other.nanos)

    def __sub__(self, other: "Duration") -> "Duration":
        return Duration(self.nanos - other.nanos)

    def __lt__(self, other: "Duration") -> bool:
        return self.nanos < other.nanos

    def __le__(self, other: "Duration") -> bool:
        return self.nanos <= other.nanos


def load_tz(name: str) -> tzinfo:
    """Load an IANA timezone by name."""
    return ZoneInfo(name)


def floor_to_midnight(instant: datetime, tz: tzinfo) -> datetime:
    """Return the start of the instant's calendar day in `tz`."""
    local = instant.astimezone(tz)
    return datetime.combine(local.date(), time.min, tzinfo=tz)


def ceil_to_next(instant: datetime, align_seconds: int, tz: tzinfo) -> datetime:
    """Round `instant` up to the next multiple of `align_seconds`, anchored
    to the top of the current hour in `tz` (DESIGN.md §5.5).

    A value that already lands on the grid is returned unchanged.
    """
    if align_seconds <= 0:
        return instant
    local = instant.astimezone(tz)
    hour_start = local.replace(minute=0, second=0, microsecond=0)
    delta = int((local - hour_start).total_seconds())
    if delta % align_seconds == 0 and local.microsecond == 0:
        return local
    n = (delta // align_seconds) + 1
    return hour_start + timedelta(seconds=n * align_seconds)


_ISO_NS_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d{1,9}))?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})$",
)


class NanoInstant:
    """Timezone-aware instant carrying nanosecond precision.

    Python's `datetime` only tracks microseconds, so we compose one with an
    integer `extra_nanos` in 0..999 to get the full nanosecond resolution
    ErsatzTV-Next uses in its playout timestamps (DESIGN.md §7.3).
    """

    __slots__ = ("dt", "extra_nanos")

    def __init__(self, dt: datetime, extra_nanos: int = 0) -> None:
        if dt.tzinfo is None:
            raise ValueError("NanoInstant requires a timezone-aware datetime")
        if not 0 <= extra_nanos < 1000:
            raise ValueError(f"extra_nanos must be in [0, 1000), got {extra_nanos}")
        self.dt = dt
        self.extra_nanos = int(extra_nanos)

    @classmethod
    def from_datetime(cls, dt: datetime) -> "NanoInstant":
        return cls(dt, 0)

    def plus_nanos(self, nanos: int) -> "NanoInstant":
        total_nanos = self.dt.microsecond * 1000 + self.extra_nanos + int(nanos)
        micros, extra = divmod(total_nanos, 1000)
        if extra < 0:
            micros -= 1
            extra += 1000
        base = self.dt.replace(microsecond=0) + timedelta(microseconds=micros)
        return NanoInstant(base, extra)

    def diff_nanos(self, other: "NanoInstant") -> int:
        dt_diff = self.dt - other.dt
        micro_part = int(dt_diff / timedelta(microseconds=1))
        return micro_part * 1000 + (self.extra_nanos - other.extra_nanos)

    def astimezone(self, tz: tzinfo) -> "NanoInstant":
        return NanoInstant(self.dt.astimezone(tz), self.extra_nanos)

    def __lt__(self, other: "NanoInstant") -> bool:
        return (self.dt, self.extra_nanos) < (other.dt, other.extra_nanos)

    def __le__(self, other: "NanoInstant") -> bool:
        return (self.dt, self.extra_nanos) <= (other.dt, other.extra_nanos)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NanoInstant) and self.dt == other.dt and self.extra_nanos == other.extra_nanos

    def __hash__(self) -> int:
        return hash((self.dt, self.extra_nanos))

    def __repr__(self) -> str:
        return f"NanoInstant({self.dt!r}, extra_nanos={self.extra_nanos})"


def format_iso_nanos(instant: datetime | NanoInstant) -> str:
    """Render an instant as RFC3339 with nanosecond precision.

    Output format: ``YYYY-MM-DDTHH:MM:SS.nnnnnnnnn±HH:MM``.
    Accepts either a plain tz-aware `datetime` (treated as 0 extra nanos) or
    a `NanoInstant`.
    """
    if isinstance(instant, NanoInstant):
        dt = instant.dt
        extra_nanos = instant.extra_nanos
    else:
        dt = instant
        extra_nanos = 0
    if dt.tzinfo is None:
        raise ValueError("format_iso_nanos requires a timezone-aware datetime")

    frac_ns = dt.microsecond * 1000 + extra_nanos

    offset = dt.utcoffset() or timedelta()
    total_min = int(offset.total_seconds() // 60)
    sign = "-" if total_min < 0 else "+"
    abs_min = abs(total_min)
    off_h, off_m = divmod(abs_min, 60)

    main = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{main}.{frac_ns:09d}{sign}{off_h:02d}:{off_m:02d}"


def format_iso_compact(instant: datetime | NanoInstant) -> str:
    """Compact ISO 8601 used for playout filenames (DESIGN.md §4).

    Example: ``20260424T000000.000000000-0500``.
    """
    iso = format_iso_nanos(instant)
    date_part, time_part = iso.split("T", 1)
    compact_date = date_part.replace("-", "")
    before_tz_match = re.match(r"^(\d{2}:\d{2}:\d{2}\.\d{9})([+-]\d{2}):(\d{2})$", time_part)
    if not before_tz_match:
        raise ValueError(f"cannot compact ISO {iso!r}")
    tme, sign_h, mm = before_tz_match.groups()
    compact_time = tme.replace(":", "")
    return f"{compact_date}T{compact_time}{sign_h}{mm}"


def add_nanos(instant: datetime | NanoInstant, nanos: int) -> NanoInstant:
    """Add a nanosecond offset to an instant, returning a `NanoInstant`."""
    base = instant if isinstance(instant, NanoInstant) else NanoInstant.from_datetime(instant)
    return base.plus_nanos(nanos)


def diff_nanos(a: datetime | NanoInstant, b: datetime | NanoInstant) -> int:
    """Return ``a - b`` in nanoseconds, using `NanoInstant` where present."""
    na = a if isinstance(a, NanoInstant) else NanoInstant.from_datetime(a)
    nb = b if isinstance(b, NanoInstant) else NanoInstant.from_datetime(b)
    return na.diff_nanos(nb)


def at_seconds_to_datetime(day: date, seconds_since_midnight: int, tz: tzinfo) -> datetime:
    """Combine a calendar day and a seconds-since-midnight offset into a
    timezone-aware datetime."""
    h, rem = divmod(seconds_since_midnight, 3600)
    m, s = divmod(rem, 60)
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=tz)


__all__ = [
    "Duration",
    "JELLYFIN_TICKS_PER_SECOND",
    "NANOS_PER_MS",
    "NANOS_PER_SECOND",
    "NanoInstant",
    "add_nanos",
    "at_seconds_to_datetime",
    "ceil_to_next",
    "diff_nanos",
    "floor_to_midnight",
    "format_iso_compact",
    "format_iso_nanos",
    "load_tz",
]
