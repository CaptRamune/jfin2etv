"""The planner: compiles a Plan AST + resolved item pools into a day's
playout and EPG projection (DESIGN.md §7, §8)."""

from .expander import DayExpansion, ExpansionError, expand_day
from .model import (
    BlockEpgOverrides,
    ChannelSpec,
    Collection,
    DefaultBlock,
    EpgField,
    EpgSpec,
    Filler,
    Layout,
    LayoutStep,
    PlanAST,
    Schedule,
    ScheduleBlock,
    Variant,
    VariantSelector,
)

__all__ = [
    "BlockEpgOverrides",
    "ChannelSpec",
    "Collection",
    "DayExpansion",
    "DefaultBlock",
    "EpgField",
    "EpgSpec",
    "ExpansionError",
    "Filler",
    "Layout",
    "LayoutStep",
    "PlanAST",
    "Schedule",
    "ScheduleBlock",
    "Variant",
    "VariantSelector",
    "expand_day",
]
