"""Variant resolution (DESIGN.md §5.5.1)."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ..ruby_bridge import invoke_variant_selector
from .model import Variant, VariantSelector

DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

ProcCaller = Callable[[str, date], str]
"""A callable that resolves a Proc selector's source to a variant name for a
given date. Tests stub this; production passes `invoke_variant_selector`.
"""


def resolve_variant(
    selector: VariantSelector,
    target_date: date,
    *,
    proc_caller: ProcCaller | None = None,
) -> str:
    """Return the variant key selected for `target_date`."""
    if selector.type == "dow":
        if not selector.table:
            raise ValueError("dow selector missing table")
        wd_name = DOW_NAMES[target_date.weekday()]
        if wd_name in selector.table:
            return selector.table[wd_name]
        if 0 <= target_date.weekday() <= 4 and "weekdays" in selector.table:
            return selector.table["weekdays"]
        if 5 <= target_date.weekday() <= 6 and "weekends" in selector.table:
            return selector.table["weekends"]
        if "default" in selector.table:
            return selector.table["default"]
        raise ValueError(f"dow selector has no match for {target_date.isoformat()}")
    if selector.type == "proc":
        if not selector.source:
            raise ValueError("proc selector missing source")
        caller = proc_caller or invoke_variant_selector
        return caller(selector.source, target_date)
    raise ValueError(f"unknown selector type {selector.type!r}")


def apply_variant(
    block_collection: str,
    block_layout: str,
    variant: Variant | None,
) -> tuple[str, str]:
    coll = variant.collection if variant and variant.collection else block_collection
    layout = variant.layout if variant and variant.layout else block_layout
    return coll, layout


__all__ = ["DOW_NAMES", "apply_variant", "resolve_variant"]
