"""Filler expansion helpers (DESIGN.md §8).

A filler "plays" by emitting a sequence of playout items whose total duration
is close to (but does not exceed) a budget expressed in nanoseconds. Items
returned here are abstract `PlayableItem`s — the caller positions them on the
timeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..logging import get_logger
from ..time_utils import NANOS_PER_MS, NANOS_PER_SECOND
from .model import Filler

logger = get_logger(__name__)


@dataclass(slots=True)
class PlayableItem:
    """A single emit-able unit with nanosecond-precision duration."""

    source_type: str  # "local", "http", or "lavfi"
    path: str | None = None
    uri: str | None = None
    params: str | None = None
    duration_nanos: int = 0
    in_point_ms: int | None = None
    out_point_ms: int | None = None
    # Original Jellyfin / filler metadata for EPG projection.
    meta: dict | None = None


def emit_local(path: str, duration_nanos: int) -> PlayableItem:
    return PlayableItem(source_type="local", path=path, duration_nanos=duration_nanos)


def emit_lavfi(params: str, duration_nanos: int) -> PlayableItem:
    return PlayableItem(source_type="lavfi", params=params, duration_nanos=duration_nanos)


def fill_budget_looped(
    filler_item: PlayableItem,
    budget_nanos: int,
    allow_trim_last: bool = True,
) -> list[PlayableItem]:
    """Slug strategy: loop the filler item, optionally trimming the last copy (§8.1).

    When ``allow_trim_last`` is False, sub-item residual is left unfilled so
    a later pool in a `fill with: [...]` priority list can take the trim.
    """
    if budget_nanos <= 0 or filler_item.duration_nanos <= 0:
        return []
    out: list[PlayableItem] = []
    remaining = budget_nanos
    while remaining >= filler_item.duration_nanos:
        out.append(
            PlayableItem(
                source_type=filler_item.source_type,
                path=filler_item.path,
                uri=filler_item.uri,
                params=filler_item.params,
                duration_nanos=filler_item.duration_nanos,
                meta=filler_item.meta,
            )
        )
        remaining -= filler_item.duration_nanos
    if remaining > 0 and allow_trim_last:
        out.append(
            PlayableItem(
                source_type=filler_item.source_type,
                path=filler_item.path,
                uri=filler_item.uri,
                params=filler_item.params,
                duration_nanos=remaining,
                in_point_ms=0,
                out_point_ms=int(remaining // NANOS_PER_MS),
                meta=filler_item.meta,
            )
        )
    return out


def fill_budget_draining(
    pool: list[PlayableItem],
    budget_nanos: int,
    allow_trim_last: bool = True,
) -> list[PlayableItem]:
    """Pre/post-roll & mid-roll: drain `pool` in `mode:` order, emitting each
    item whole if it fits and *skipping* items that don't so a shorter item
    later in the pool can still play (§8.2, §8.3, §8.4).

    When ``allow_trim_last`` is True (the default), the first oversized item
    the scan encountered is then trimmed with ``out_point_ms`` to consume the
    residual exactly. When False, sub-item residual is left unfilled so a
    downstream pool in a ``fill with: [...]`` priority list can take the trim.
    """
    if budget_nanos <= 0 or not pool:
        return []
    out: list[PlayableItem] = []
    remaining = budget_nanos
    first_oversized: PlayableItem | None = None
    for item in pool:
        if remaining <= 0:
            break
        if item.duration_nanos <= remaining:
            out.append(item)
            remaining -= item.duration_nanos
        elif first_oversized is None:
            first_oversized = item
        # else: oversized but we already have a trim candidate — keep scanning
        #       in case a later item still fits the remaining gap.
    if allow_trim_last and remaining > 0 and first_oversized is not None:
        logger.warning(
            "filler truncated to fit budget",
            extra={
                "event": "planner.filler_truncated",
                "file": first_oversized.path or first_oversized.uri or "lavfi",
            },
        )
        out.append(
            PlayableItem(
                source_type=first_oversized.source_type,
                path=first_oversized.path,
                uri=first_oversized.uri,
                params=first_oversized.params,
                duration_nanos=remaining,
                in_point_ms=0,
                out_point_ms=int(remaining // NANOS_PER_MS),
                meta=first_oversized.meta,
            )
        )
    return out


def auto_break_budgets(
    total_budget_nanos: int,
    break_count: int,
    per_break_target_s: int = 120,
) -> list[int]:
    """Distribute `total_budget_nanos` across `break_count` breaks using
    `per_break_target_s` as the packing heuristic (§8.3 `count: :auto`)."""
    if break_count <= 0:
        return []
    target = per_break_target_s * NANOS_PER_SECOND
    if total_budget_nanos <= 0:
        return [0] * break_count

    # Base: one target-size break per slot, clamped by total.
    budgets = [target] * break_count
    # If target * count > total, shrink evenly.
    over = sum(budgets) - total_budget_nanos
    if over > 0:
        per_slot_shave = over // break_count
        remainder = over - per_slot_shave * break_count
        budgets = [b - per_slot_shave for b in budgets]
        for i in range(remainder):
            budgets[i] -= 1
    # If target * count < total, enlarge evenly to use the budget.
    under = total_budget_nanos - sum(budgets)
    if under > 0:
        per_slot_add = under // break_count
        remainder = under - per_slot_add * break_count
        budgets = [b + per_slot_add for b in budgets]
        for i in range(remainder):
            budgets[i] += 1
    return budgets


def is_local_filler(filler: Filler) -> bool:
    return filler.kind == "local"


__all__ = [
    "PlayableItem",
    "auto_break_budgets",
    "emit_lavfi",
    "emit_local",
    "fill_budget_draining",
    "fill_budget_looped",
    "is_local_filler",
]
