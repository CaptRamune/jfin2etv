"""channel.json writer mapping the DSL transcode hash to ErsatzTV-Next's
ChannelConfig schema (DESIGN.md §4.2, §5.1, §6.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..planner.model import ChannelSpec


def render_channel_config(channel: ChannelSpec, playout_folder: str) -> dict[str, Any]:
    t = channel.transcode
    video = t.video.model_dump(exclude_none=False)
    audio = t.audio.model_dump(exclude_none=False)
    playout = t.playout.model_dump(exclude_none=False)

    ffmpeg = t.ffmpeg.model_dump()
    # Remove `null` for string optionals to keep the document tidy.
    if ffmpeg.get("ffmpeg_path") is None:
        ffmpeg.pop("ffmpeg_path", None)
    if ffmpeg.get("ffprobe_path") is None:
        ffmpeg.pop("ffprobe_path", None)

    return {
        "ffmpeg": ffmpeg,
        "normalization": {
            "video": {k: v for k, v in video.items() if v is not None},
            "audio": {k: v for k, v in audio.items() if v is not None},
        },
        "playout": {
            "folder": playout_folder,
            **{k: v for k, v in playout.items() if v is not None},
        },
    }


def write_channel_config(channel: ChannelSpec, out_path: str | Path, playout_folder: str) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = render_channel_config(channel, playout_folder)
    with p.open("w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return p


__all__ = ["render_channel_config", "write_channel_config"]
