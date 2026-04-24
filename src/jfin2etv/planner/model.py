"""Pydantic dataclasses mirroring the plan AST JSON from Ruby (DESIGN.md §6.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EpgField(BaseModel):
    kind: Literal["literal", "proc"]
    value: str | None = None
    source: str | None = None


class EpgSpec(BaseModel):
    granularity: Literal["per_item", "per_block", "per_chapter"] = "per_item"
    title: str | EpgField | None = None
    description: str | EpgField | None = None
    category: str | None = None


class LayoutStep(BaseModel):
    op: Literal["pre_roll", "main", "slug", "mid_roll", "post_roll", "fill"]
    count: int | str | None = None
    every: Any = None  # "chapter" | "never" | {"minutes": N}
    wrap_with: list[str] | None = None
    per_break_target: int | None = None
    between_items: bool | None = None
    duration: float | None = None
    with_: list[str] | None = Field(default=None, alias="with")

    model_config = {"populate_by_name": True}


class Layout(BaseModel):
    steps: list[LayoutStep]
    epg: EpgSpec = Field(default_factory=EpgSpec)


class Collection(BaseModel):
    expression: str
    mode: Literal["shuffle", "sequential", "chronological", "random_with_memory", "weighted_random"] = "shuffle"
    sort: str | None = None
    memory_window: int | None = None
    weight_field: str | None = None


class Filler(BaseModel):
    kind: Literal["local", "collection"]
    path: str | None = None
    expression: str | None = None
    mode: str | None = None
    sort: str | None = None
    memory_window: int | None = None
    weight_field: str | None = None


class ChannelTranscodeFfmpeg(BaseModel):
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    disabled_filters: list[str] = Field(default_factory=list)
    preferred_filters: list[str] = Field(default_factory=list)


class ChannelTranscodeVideo(BaseModel):
    format: str | None = None
    width: int | None = None
    height: int | None = None
    bitrate_kbps: int | None = None
    buffer_kbps: int | None = None
    bit_depth: int | None = None
    accel: str | None = None
    deinterlace: bool = False
    tonemap_algorithm: str | None = None
    vaapi_device: str | None = None
    vaapi_driver: str | None = None


class ChannelTranscodeAudio(BaseModel):
    format: str | None = None
    bitrate_kbps: int | None = None
    buffer_kbps: int | None = None
    channels: int | None = None
    sample_rate_hz: int | None = None
    normalize_loudness: bool = False
    loudness: dict[str, Any] | None = None


class ChannelTranscodePlayout(BaseModel):
    virtual_start: str | None = None


class ChannelTranscode(BaseModel):
    ffmpeg: ChannelTranscodeFfmpeg
    video: ChannelTranscodeVideo
    audio: ChannelTranscodeAudio
    playout: ChannelTranscodePlayout


class ChannelSpec(BaseModel):
    number: str
    name: str
    tuning: str
    icon: str | None = None
    language: str = "en"
    transcode: ChannelTranscode


class BlockEpgOverrides(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None


class Variant(BaseModel):
    collection: str | None = None
    layout: str | None = None


class VariantSelector(BaseModel):
    type: Literal["dow", "proc"]
    table: dict[str, str] | None = None
    source: str | None = None


class ScheduleBlock(BaseModel):
    at: str
    collection: str
    layout: str
    count: int | str | None = None
    on: Any = None
    align_seconds: int | None = None
    epg_overrides: BlockEpgOverrides | None = None
    variants: dict[str, Variant] | None = None
    variant_selector: VariantSelector | None = None

    @property
    def at_seconds(self) -> int:
        parts = self.at.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s


class DefaultBlock(BaseModel):
    collection: str
    layout: str
    align_seconds: int | None = None


class Schedule(BaseModel):
    blocks: list[ScheduleBlock]
    default_block: DefaultBlock | None = None


class PlanAST(BaseModel):
    schema_version: str
    channel: ChannelSpec
    collections: dict[str, Collection]
    fillers: dict[str, Filler]
    layouts: dict[str, Layout]
    schedule: Schedule


__all__ = [
    "BlockEpgOverrides",
    "ChannelSpec",
    "ChannelTranscode",
    "ChannelTranscodeAudio",
    "ChannelTranscodeFfmpeg",
    "ChannelTranscodePlayout",
    "ChannelTranscodeVideo",
    "Collection",
    "DefaultBlock",
    "EpgField",
    "EpgSpec",
    "Filler",
    "Layout",
    "LayoutStep",
    "PlanAST",
    "Schedule",
    "ScheduleBlock",
    "Variant",
    "VariantSelector",
]
