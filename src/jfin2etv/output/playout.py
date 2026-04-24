"""playout.json writer (DESIGN.md §4, §10.5, §18.4).

Atomic write: tmp → fsync → rename.
Filename: ``{startISO}_{finishISO}.json`` with compact (no-separator) ISO 8601.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..planner.expander import ScheduledItem
from ..schemas import ERSATZTV_PLAYOUT_SCHEMA_URI
from ..time_utils import format_iso_compact, format_iso_nanos


def render_playout(items: list[ScheduledItem]) -> dict:
    """Render a list of ScheduledItem into an ErsatzTV-Next playout JSON dict."""
    out_items = []
    for idx, s in enumerate(items):
        src = _render_source(s.item)
        out_items.append({
            "id": f"{s.block_anchor}:{idx:05d}",
            "start": format_iso_nanos(s.start),
            "finish": format_iso_nanos(s.finish),
            "source": src,
        })
    return {
        "version": ERSATZTV_PLAYOUT_SCHEMA_URI,
        "items": out_items,
    }


def _render_source(item) -> dict:
    if item.source_type == "local":
        out: dict = {"source_type": "local", "path": item.path}
        if item.in_point_ms is not None:
            out["in_point_ms"] = int(item.in_point_ms)
        if item.out_point_ms is not None:
            out["out_point_ms"] = int(item.out_point_ms)
        return out
    if item.source_type == "http":
        out = {"source_type": "http", "uri": item.uri}
        if item.in_point_ms is not None:
            out["in_point_ms"] = int(item.in_point_ms)
        if item.out_point_ms is not None:
            out["out_point_ms"] = int(item.out_point_ms)
        return out
    if item.source_type == "lavfi":
        return {"source_type": "lavfi", "params": item.params or ""}
    raise ValueError(f"unknown source_type {item.source_type!r}")


def write_playout(items: list[ScheduledItem], out_dir: str | Path) -> Path:
    """Write playout JSON to ``{out_dir}/{startCompact}_{finishCompact}.json``
    using atomic tmp+rename. Returns the written path."""
    if not items:
        raise ValueError("no items; refusing to write empty playout")
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    start_compact = format_iso_compact(items[0].start)
    finish_compact = format_iso_compact(items[-1].finish)
    path = out_dir_p / f"{start_compact}_{finish_compact}.json"
    doc = render_playout(items)

    tmp_fd, tmp_path_str = tempfile.mkstemp(prefix=".playout-", suffix=".json.tmp", dir=str(out_dir_p))
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()
        raise
    return path


import contextlib  # placed at bottom to keep the `Exception` cleanup tight

__all__ = ["render_playout", "write_playout"]
