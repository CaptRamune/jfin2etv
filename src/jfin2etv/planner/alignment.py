"""Block-end alignment math (DESIGN.md §5.5, §8.3)."""

from __future__ import annotations

from datetime import datetime, tzinfo

from ..time_utils import ceil_to_next


def target_end(
    natural_end: datetime,
    next_anchor: datetime | None,
    align_seconds: int | None,
    tz: tzinfo,
) -> datetime:
    """Compute the intended end-time for a block.

    * If the block defines `align`, round the natural end up to the next
      multiple of `align` (§5.5).
    * Clip to `next_anchor` so the following block can start on time.
    * If no `align` and no next anchor, use the natural end verbatim.
    """
    if align_seconds and align_seconds > 0:
        aligned = ceil_to_next(natural_end, align_seconds, tz)
    else:
        aligned = natural_end
    if next_anchor is not None and aligned > next_anchor:
        return next_anchor
    return aligned


__all__ = ["target_end"]
