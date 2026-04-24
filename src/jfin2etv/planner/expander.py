"""Day-expansion state machine (DESIGN.md §7.2).

Given a plan AST, resolved item pools, and a target calendar day, produce an
ordered list of playout items and an EPG programme projection for the day.

The algorithm:
  1. Walk the schedule's `blocks` list (plus a default block that fills gaps).
  2. For each block, expand its layout steps into playable items:
     - `pre_roll`: emit N items from the ``pre_roll`` filler pool.
     - `main`: emit the block's main item (applying mid-roll insertion if
       the layout has a ``mid_roll`` step).
     - `post_roll`: emit N items from the ``post_roll`` filler pool.
     - `slug`: insert between-items beats if configured.
     - `fill`: at the end, use the ``fill with:`` pool to stretch the block
       to its aligned end-time.
  3. Run alignment logic to clip to the next block's anchor / align grid.
  4. If the last item spans midnight, split it at the day boundary.
  5. Return playable items + a list of EPG programme dicts.

This module intentionally uses its own Python types; output writers convert
to ErsatzTV-Next JSON shapes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

from ..logging import get_logger
from ..state import (
    pick_chronological,
    pick_random_with_memory,
    pick_sequential,
    pick_shuffle,
    pick_weighted_random,
)
from ..time_utils import (
    NANOS_PER_SECOND,
    add_nanos,
    at_seconds_to_datetime,
    diff_nanos,
)
from .alignment import target_end
from .fillers import (
    PlayableItem,
    auto_break_budgets,
    fill_budget_draining,
    fill_budget_looped,
)
from .midnight_split import split_at_midnight
from .model import (
    Collection,
    Layout,
    LayoutStep,
    PlanAST,
    ScheduleBlock,
)
from .variants import apply_variant, resolve_variant

logger = get_logger(__name__)


class ExpansionError(RuntimeError):
    pass


@dataclass(slots=True)
class ScheduledItem:
    """A positioned playable item on the day's timeline."""

    start: datetime
    finish: datetime
    item: PlayableItem
    block_anchor: str
    collection: str | None = None
    layout: str | None = None
    is_filler: bool = False
    filler_kind: str | None = None
    # Bookkeeping for EPG projection.
    programme_group: str | None = None


@dataclass(slots=True)
class EpgProgramme:
    start: datetime
    finish: datetime
    title: str
    description: str | None
    category: str | None
    block_anchor: str


@dataclass(slots=True)
class DayExpansion:
    day: date
    items: list[ScheduledItem] = field(default_factory=list)
    programmes: list[EpgProgramme] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Item-pool adapters: Jellyfin item dicts -> PlayableItem.
# ---------------------------------------------------------------------------


def jellyfin_duration_nanos(item: dict) -> int:
    ticks = item.get("RunTimeTicks")
    if ticks is None:
        return 0
    return int(ticks) * 100  # 1 tick = 100 ns


def to_playable(item: dict, *, is_filler: bool = False) -> PlayableItem:
    path = item.get("Path") or item.get("path")
    duration_ns = jellyfin_duration_nanos(item)
    if duration_ns <= 0:
        # Caller may ffprobe later; meanwhile stub at 1s to avoid divide by zero.
        duration_ns = 1 * NANOS_PER_SECOND
    return PlayableItem(
        source_type="local",
        path=str(path) if path else None,
        duration_nanos=duration_ns,
        meta={**item, "__is_filler": is_filler},
    )


# ---------------------------------------------------------------------------
# Pool selection delegating to state.py helpers.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PoolPicker:
    """Per-collection selector with sticky cursor state."""

    cursor: int = 0
    recent_ids: set[str] = field(default_factory=set)
    seed: int = 0

    def pick(
        self,
        items: list[dict],
        collection: Collection,
    ) -> tuple[dict, PoolPicker]:
        if not items:
            raise ExpansionError("empty pool")
        mode = collection.mode
        if mode == "shuffle":
            item = pick_shuffle(items, seed=self.seed)
            self.seed += 1
            return item, self
        if mode == "sequential":
            item, nxt = pick_sequential(items, self.cursor)
            self.cursor = nxt
            return item, self
        if mode == "chronological":
            item, nxt = pick_chronological(items, self.cursor, sort_field=collection.sort or "PremiereDate")
            self.cursor = nxt
            return item, self
        if mode == "random_with_memory":
            item = pick_random_with_memory(items, self.recent_ids, seed=self.seed)
            self.seed += 1
            self.recent_ids.add(item.get("Id"))
            return item, self
        if mode == "weighted_random":
            item = pick_weighted_random(items, weight_field=collection.weight_field or "CommunityRating", seed=self.seed)
            self.seed += 1
            return item, self
        raise ExpansionError(f"unknown mode {mode!r}")


# ---------------------------------------------------------------------------
# Per-block expansion.
# ---------------------------------------------------------------------------


def _find_mid_roll_step(layout: Layout) -> LayoutStep | None:
    for s in layout.steps:
        if s.op == "mid_roll":
            return s
    return None


def _find_fill_step(layout: Layout) -> LayoutStep | None:
    for s in layout.steps:
        if s.op == "fill":
            return s
    return None


def _find_slug_step(layout: Layout) -> LayoutStep | None:
    for s in layout.steps:
        if s.op == "slug":
            return s
    return None


def _find_count_step(layout: Layout, op: str) -> int:
    for s in layout.steps:
        if s.op == op and isinstance(s.count, int):
            return int(s.count)
    return 0


def _split_main_for_mid_rolls(
    main: PlayableItem,
    mid_roll: LayoutStep,
) -> list[PlayableItem]:
    """Split `main` into N chunks based on the mid_roll step.

    Returns a list of chunked `PlayableItem`s with appropriate in/out points.
    For `every: :chapter`, chunks are equal-sized (one per break + 1 remainder).
    For `every: {minutes: N}`, chunks are ~N minutes each.
    """
    if mid_roll.every in ("chapter", None):
        # Without real chapter info, simulate a single chapter break in the middle.
        break_points_ns = [main.duration_nanos // 2]
    elif mid_roll.every == "never":
        return [main]
    elif isinstance(mid_roll.every, dict) and "minutes" in mid_roll.every:
        interval_ns = int(mid_roll.every["minutes"]) * 60 * NANOS_PER_SECOND
        n_breaks = max(0, main.duration_nanos // interval_ns - 1)
        if n_breaks == 0:
            return [main]
        break_points_ns = [int(interval_ns * (i + 1)) for i in range(n_breaks)]
    else:
        return [main]

    chunks: list[PlayableItem] = []
    prev_ns = 0
    for bp in [*break_points_ns, main.duration_nanos]:
        chunk_duration = bp - prev_ns
        if chunk_duration <= 0:
            continue
        chunk = PlayableItem(
            source_type=main.source_type,
            path=main.path,
            uri=main.uri,
            duration_nanos=chunk_duration,
            in_point_ms=(prev_ns // 1_000_000),
            out_point_ms=(bp // 1_000_000),
            meta=main.meta,
        )
        chunks.append(chunk)
        prev_ns = bp
    return chunks


# ---------------------------------------------------------------------------
# Top-level expander.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResolvedPools:
    collections: dict[str, list[dict]]  # collection name -> items
    filler_local: dict[str, PlayableItem]  # filler kind -> single PlayableItem
    filler_collections: dict[str, list[dict]]  # filler kind -> items list


def build_resolved_pools(
    collections: dict[str, list[dict]],
    filler_local: dict[str, PlayableItem] | None = None,
    filler_collections: dict[str, list[dict]] | None = None,
) -> ResolvedPools:
    return ResolvedPools(
        collections=dict(collections),
        filler_local=dict(filler_local or {}),
        filler_collections=dict(filler_collections or {}),
    )


def _filler_pick(
    pools: ResolvedPools,
    kind: str,
) -> PlayableItem | None:
    if kind in pools.filler_local:
        return pools.filler_local[kind]
    items = pools.filler_collections.get(kind) or []
    if not items:
        return None
    return to_playable(items[0], is_filler=True)


def _filler_drain_pool(pools: ResolvedPools, kind: str, count_hint: int) -> list[PlayableItem]:
    items = pools.filler_collections.get(kind)
    if items is None and kind in pools.filler_local:
        return [pools.filler_local[kind]] * max(1, count_hint)
    if not items:
        return []
    return [to_playable(i, is_filler=True) for i in items]


def _effective_title(item: PlayableItem, layout: Layout) -> str:
    m = item.meta or {}
    title = layout.epg.title if isinstance(layout.epg.title, str) else None
    if title == "from_main" or title is None:
        return str(m.get("Name") or "Unknown")
    if title == "from_series":
        return str(m.get("SeriesName") or m.get("Name") or "Unknown")
    if title == "from_block":
        return "Block"
    if isinstance(title, str):
        return title
    return str(m.get("Name") or "Unknown")


def _effective_description(item: PlayableItem, layout: Layout) -> str | None:
    m = item.meta or {}
    desc = layout.epg.description
    if isinstance(desc, str):
        if desc == "from_main":
            return m.get("Overview")
        if desc == "from_series":
            return m.get("SeriesOverview") or m.get("Overview")
        return desc
    return m.get("Overview")


def expand_day(
    plan: PlanAST,
    day: date,
    pools: ResolvedPools,
    tz: tzinfo,
    *,
    picker_state: dict[str, PoolPicker] | None = None,
    proc_caller: Callable[[str, date], str] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> DayExpansion:
    """Expand a single 24-hour day into scheduled items + programmes.

    `start_at` defaults to midnight in `tz`; `end_at` defaults to the next
    midnight.
    """
    if start_at is None:
        start_at = datetime.combine(day, time.min, tzinfo=tz)
    if end_at is None:
        end_at = start_at + timedelta(days=1)

    pickers = picker_state or {}
    exp = DayExpansion(day=day)

    # Resolve which blocks apply today (on: filter), honoring variants.
    active_blocks: list[tuple[datetime, ScheduleBlock, str, str]] = []
    for b in plan.schedule.blocks:
        if not _applies_today(b, day):
            continue
        coll, layout_name = _resolve_block_variant(b, day, proc_caller)
        anchor = at_seconds_to_datetime(day, b.at_seconds, tz)
        active_blocks.append((anchor, b, coll, layout_name))
    active_blocks.sort(key=lambda x: x[0])

    if not active_blocks and plan.schedule.default_block is None:
        raise ExpansionError("no active blocks and no default_block for " + day.isoformat())

    # Walk through the day, filling gaps with default_block before each active block.
    cursor = start_at
    idx = 0
    while cursor < end_at:
        # Determine next anchor after `cursor`
        next_anchor = end_at
        if idx < len(active_blocks) and active_blocks[idx][0] > cursor:
            next_anchor = active_blocks[idx][0]
            # Emit default-block fill up to the next anchor.
            if plan.schedule.default_block is not None:
                filled = _expand_default_block(
                    plan, cursor, next_anchor, pools, pickers, tz,
                )
                exp.items.extend(filled)
                cursor = filled[-1].finish if filled else next_anchor
            else:
                cursor = next_anchor
            continue

        if idx < len(active_blocks):
            anchor, b, coll, layout_name = active_blocks[idx]
            # The next anchor after this one (or end_at).
            following_anchor = active_blocks[idx + 1][0] if idx + 1 < len(active_blocks) else end_at
            produced = _expand_block(
                plan, anchor, following_anchor, b, coll, layout_name,
                pools, pickers, tz,
            )
            exp.items.extend(produced)
            if produced:
                cursor = produced[-1].finish
            idx += 1
        else:
            # No more anchors — fill to end_at with default block.
            if plan.schedule.default_block is not None:
                filled = _expand_default_block(
                    plan, cursor, end_at, pools, pickers, tz,
                )
                exp.items.extend(filled)
                if filled:
                    cursor = filled[-1].finish
                else:
                    break
            else:
                break

    _apply_midnight_split(exp, day, tz)
    _project_epg(exp, plan)
    return exp


def _applies_today(block: ScheduleBlock, day: date) -> bool:
    on = block.on
    if on is None:
        return True
    if isinstance(on, dict):
        kind = on.get("type")
        val = on.get("value")
        if kind == "symbol":
            if val == "weekdays":
                return day.weekday() < 5
            if val == "weekends":
                return day.weekday() >= 5
            return True
        if kind == "list":
            names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            wd = names[day.weekday()]
            return wd in (val or [])
    return True


def _resolve_block_variant(
    block: ScheduleBlock,
    day: date,
    proc_caller: Callable[[str, date], str] | None,
) -> tuple[str, str]:
    if not block.variants or not block.variant_selector:
        return block.collection, block.layout
    key = resolve_variant(block.variant_selector, day, proc_caller=proc_caller)
    variant = block.variants.get(key) if block.variants else None
    return apply_variant(block.collection, block.layout, variant)


def _picker_for(pickers: dict[str, PoolPicker], collection: str) -> PoolPicker:
    return pickers.setdefault(collection, PoolPicker(seed=abs(hash(collection)) % 1_000_000))


def _expand_block(
    plan: PlanAST,
    anchor: datetime,
    next_anchor: datetime,
    block: ScheduleBlock,
    collection: str,
    layout_name: str,
    pools: ResolvedPools,
    pickers: dict[str, PoolPicker],
    tz: tzinfo,
) -> list[ScheduledItem]:
    layout = plan.layouts.get(layout_name)
    if layout is None:
        raise ExpansionError(f"unknown layout {layout_name!r}")
    coll = plan.collections.get(collection)
    if coll is None:
        raise ExpansionError(f"unknown collection {collection!r}")
    items_pool = pools.collections.get(collection, [])
    if not items_pool:
        raise ExpansionError(f"collection {collection!r} is empty")

    picker = _picker_for(pickers, collection)
    out: list[ScheduledItem] = []
    cursor = anchor

    # pre_roll
    pre_count = _find_count_step(layout, "pre_roll")
    if pre_count:
        pre_pool = _filler_drain_pool(pools, "pre_roll", pre_count)
        for _ in range(pre_count):
            if not pre_pool:
                break
            item = pre_pool[_ % len(pre_pool)]
            out.append(_place(item, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind="pre_roll"))
            cursor = out[-1].finish

    # Determine repeat count: block.count (int|"auto"|None). None -> 1.
    count_value = block.count
    n_mains = 1 if count_value in (None, "auto") else int(count_value)

    for _main_idx in range(n_mains):
        if cursor >= next_anchor:
            break
        main_dict, picker = picker.pick(items_pool, coll)
        pickers[collection] = picker
        main_item = to_playable(main_dict)

        mid_roll = _find_mid_roll_step(layout)
        slug_step = _find_slug_step(layout)
        if mid_roll is not None:
            chunks = _split_main_for_mid_rolls(main_item, mid_roll)
            n_breaks = max(0, len(chunks) - 1)
            # Determine the mid-roll pool & budgets.
            if mid_roll.count == "auto":
                # Budget = space_to_next_anchor - total_main_duration (rough).
                remaining_ns = diff_nanos(next_anchor, cursor) - sum(c.duration_nanos for c in chunks)
                budgets = auto_break_budgets(max(0, remaining_ns), n_breaks, mid_roll.per_break_target or 120)
            else:
                int(mid_roll.count or 1)
                # A fixed count per break of ~per_break_target seconds; cap by remaining budget.
                remaining_ns = diff_nanos(next_anchor, cursor) - sum(c.duration_nanos for c in chunks)
                per_break = max(0, remaining_ns // max(1, n_breaks))
                budgets = [per_break] * n_breaks

            for i, chunk in enumerate(chunks):
                out.append(_place(chunk, cursor, block.at, collection, layout_name, tz))
                cursor = out[-1].finish
                if i < n_breaks:
                    for wrap in (mid_roll.wrap_with or []):
                        w_item = _filler_pick(pools, wrap)
                        if w_item:
                            out.append(_place(w_item, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind=wrap))
                            cursor = out[-1].finish
                    # Fill the break with `mid_roll`-pool items up to the slot budget.
                    pool_items = _filler_drain_pool(pools, "mid_roll", 10)
                    slot = fill_budget_draining(pool_items, budgets[i])
                    for it in slot:
                        out.append(_place(it, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind="mid_roll"))
                        cursor = out[-1].finish
        else:
            out.append(_place(main_item, cursor, block.at, collection, layout_name, tz))
            cursor = out[-1].finish

        if slug_step and slug_step.between_items:
            sl = _filler_pick(pools, "slug")
            if sl is not None:
                dur = (slug_step.duration or 1.0)
                sl_copy = PlayableItem(
                    source_type=sl.source_type,
                    path=sl.path,
                    uri=sl.uri,
                    params=sl.params,
                    duration_nanos=int(dur * NANOS_PER_SECOND),
                    meta=sl.meta,
                )
                out.append(_place(sl_copy, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind="slug"))
                cursor = out[-1].finish

    # post_roll
    post_count = _find_count_step(layout, "post_roll")
    if post_count:
        post_pool = _filler_drain_pool(pools, "post_roll", post_count)
        for _ in range(post_count):
            if not post_pool:
                break
            item = post_pool[_ % len(post_pool)]
            out.append(_place(item, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind="post_roll"))
            cursor = out[-1].finish

    # fill to aligned/next-anchor end
    aligned_end = target_end(cursor, next_anchor, block.align_seconds, tz)
    fill_step = _find_fill_step(layout)
    if fill_step and aligned_end > cursor:
        pool_names = fill_step.with_ or []
        remaining_ns = diff_nanos(aligned_end, cursor)
        for pn in pool_names:
            if remaining_ns <= 0:
                break
            items = _filler_drain_pool(pools, pn, 20)
            if not items:
                continue
            placed = fill_budget_looped(items[0], remaining_ns) if len(items) == 1 else fill_budget_draining(items, remaining_ns)
            for it in placed:
                out.append(_place(it, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind=pn))
                cursor = out[-1].finish
            remaining_ns = diff_nanos(aligned_end, cursor)
        if remaining_ns > 0:
            # Safety-net lavfi black frame (§15).
            from .fillers import emit_lavfi
            lav = emit_lavfi(
                "color=c=black:s=320x240:r=24,format=yuv420p",
                remaining_ns,
            )
            out.append(_place(lav, cursor, block.at, collection, layout_name, tz, is_filler=True, filler_kind="lavfi"))
            cursor = out[-1].finish
    return out


def _expand_default_block(
    plan: PlanAST,
    start: datetime,
    end: datetime,
    pools: ResolvedPools,
    pickers: dict[str, PoolPicker],
    tz: tzinfo,
) -> list[ScheduledItem]:
    db = plan.schedule.default_block
    if db is None:
        return []
    layout = plan.layouts.get(db.layout)
    if layout is None:
        raise ExpansionError(f"unknown default layout {db.layout!r}")
    coll = plan.collections.get(db.collection)
    if coll is None:
        raise ExpansionError(f"unknown default collection {db.collection!r}")
    items_pool = pools.collections.get(db.collection, [])
    picker = _picker_for(pickers, db.collection)
    cursor = start
    out: list[ScheduledItem] = []
    while cursor < end and items_pool:
        main_dict, picker = picker.pick(items_pool, coll)
        pickers[db.collection] = picker
        item = to_playable(main_dict)
        # Don't overrun the end boundary — stop if the next item would cross.
        if diff_nanos(end, cursor) < item.duration_nanos:
            break
        out.append(_place(item, cursor, "default", db.collection, db.layout, tz))
        cursor = out[-1].finish
    return out


def _place(
    item: PlayableItem,
    start: datetime,
    block_anchor: str,
    collection: str,
    layout_name: str,
    tz: tzinfo,
    *,
    is_filler: bool = False,
    filler_kind: str | None = None,
) -> ScheduledItem:
    finish_nano_instant = add_nanos(start, item.duration_nanos)
    return ScheduledItem(
        start=start,
        finish=finish_nano_instant.dt,
        item=item,
        block_anchor=block_anchor,
        collection=collection,
        layout=layout_name,
        is_filler=is_filler,
        filler_kind=filler_kind,
    )


def _apply_midnight_split(exp: DayExpansion, day: date, tz: tzinfo) -> None:
    next_midnight = datetime.combine(day, time.min, tzinfo=tz) + timedelta(days=1)
    patched: list[ScheduledItem] = []
    for s in exp.items:
        if s.finish > next_midnight and s.item.source_type in ("local", "http"):
            res = split_at_midnight(s.item, s.start, tz)
            if res is not None:
                pre, post, split_point = res
                patched.append(
                    ScheduledItem(
                        start=s.start,
                        finish=split_point,
                        item=pre,
                        block_anchor=s.block_anchor + "-pre",
                        collection=s.collection,
                        layout=s.layout,
                        is_filler=s.is_filler,
                        filler_kind=s.filler_kind,
                    )
                )
                patched.append(
                    ScheduledItem(
                        start=split_point,
                        finish=s.finish,
                        item=post,
                        block_anchor=s.block_anchor + "-post",
                        collection=s.collection,
                        layout=s.layout,
                        is_filler=s.is_filler,
                        filler_kind=s.filler_kind,
                    )
                )
                continue
        patched.append(s)
    exp.items = patched


def _project_epg(exp: DayExpansion, plan: PlanAST) -> None:
    """Absorb filler-adjacent items into surrounding programme entries (§9.2)."""
    if not exp.items:
        return
    current: EpgProgramme | None = None
    for s in exp.items:
        if s.is_filler:
            if current is not None:
                current.finish = s.finish
            continue
        layout = plan.layouts.get(s.layout or "")
        if layout is None:
            continue
        title = _effective_title(s.item, layout)
        descr = _effective_description(s.item, layout)
        category = layout.epg.category
        gran = layout.epg.granularity
        if gran == "per_block" and current is not None and current.block_anchor == s.block_anchor:
            current.finish = s.finish
            continue
        if current is not None:
            exp.programmes.append(current)
        current = EpgProgramme(
            start=s.start, finish=s.finish, title=title,
            description=descr, category=category, block_anchor=s.block_anchor,
        )
    if current is not None:
        exp.programmes.append(current)


__all__ = [
    "DayExpansion",
    "EpgProgramme",
    "ExpansionError",
    "PoolPicker",
    "ResolvedPools",
    "ScheduledItem",
    "build_resolved_pools",
    "expand_day",
    "jellyfin_duration_nanos",
    "to_playable",
]
