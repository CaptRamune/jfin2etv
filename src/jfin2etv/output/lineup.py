"""lineup.json writer (DESIGN.md §4.2).

One file per ErsatzTV-Next instance, aggregating every discovered channel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LineupEntry:
    number: str
    name: str
    config: str  # path (relative or absolute) to that channel's channel.json


def render_lineup_config(
    entries: list[LineupEntry],
    output_folder: str,
    *,
    server_bind: str = "0.0.0.0",
    server_port: int = 8409,
) -> dict[str, Any]:
    return {
        "output": {"folder": output_folder},
        "server": {"bind_address": server_bind, "port": server_port},
        "channels": [
            {"number": e.number, "name": e.name, "config": e.config}
            for e in sorted(entries, key=lambda x: x.number)
        ],
    }


def write_lineup_config(
    entries: list[LineupEntry],
    out_path: str | Path,
    output_folder: str,
    *,
    server_bind: str = "0.0.0.0",
    server_port: int = 8409,
) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = render_lineup_config(entries, output_folder, server_bind=server_bind, server_port=server_port)
    with p.open("w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return p


__all__ = ["LineupEntry", "render_lineup_config", "write_lineup_config"]
