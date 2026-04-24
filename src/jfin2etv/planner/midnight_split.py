"""Item splitting across the day boundary (DESIGN.md §10.2.1)."""

from __future__ import annotations

from datetime import datetime, tzinfo

from ..time_utils import NANOS_PER_MS, add_nanos, diff_nanos, floor_to_midnight
from .fillers import PlayableItem


def split_at_midnight(
    item: PlayableItem,
    start: datetime,
    tz: tzinfo,
) -> tuple[PlayableItem, PlayableItem, datetime] | None:
    """If `item` starting at `start` crosses midnight in `tz`, return
    ``(pre_half, post_half, split_point)``. Otherwise return None.

    Both halves preserve the original source (local path or http URI); the
    post-half carries correct ``in_point_ms`` so the decoder seeks.
    """
    if item.source_type not in ("local", "http"):
        return None
    next_midnight = floor_to_midnight(start, tz).replace(hour=0) + _one_day()
    split_ns = diff_nanos(next_midnight, start)
    if split_ns <= 0 or split_ns >= item.duration_nanos:
        return None

    in_point_ms = (item.in_point_ms or 0)
    pre_out_ms = int((in_point_ms * NANOS_PER_MS + split_ns) // NANOS_PER_MS)
    post_in_ms = pre_out_ms
    post_out_ms = item.out_point_ms if item.out_point_ms is not None else int(
        (in_point_ms * NANOS_PER_MS + item.duration_nanos) // NANOS_PER_MS
    )
    pre = PlayableItem(
        source_type=item.source_type,
        path=item.path,
        uri=item.uri,
        duration_nanos=split_ns,
        in_point_ms=in_point_ms,
        out_point_ms=pre_out_ms,
        meta={**(item.meta or {}), "midnight_half": "pre"},
    )
    post = PlayableItem(
        source_type=item.source_type,
        path=item.path,
        uri=item.uri,
        duration_nanos=item.duration_nanos - split_ns,
        in_point_ms=post_in_ms,
        out_point_ms=post_out_ms,
        meta={**(item.meta or {}), "midnight_half": "post"},
    )
    split_point = add_nanos(start, split_ns).dt
    return pre, post, split_point


def _one_day():
    from datetime import timedelta
    return timedelta(days=1)


__all__ = ["split_at_midnight"]
