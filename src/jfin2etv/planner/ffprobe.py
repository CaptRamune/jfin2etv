"""Fallback duration probe via `ffprobe` when Jellyfin lacks RunTimeTicks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..logging import get_logger
from ..time_utils import NANOS_PER_SECOND

logger = get_logger(__name__)


def probe_duration_nanos(path: str | Path, ffprobe_bin: str = "ffprobe") -> int | None:
    """Return duration in nanoseconds, or None if probing fails."""
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("ffprobe failed", extra={"event": "ffprobe.error", "file": str(path), "msg": str(e)})
        return None
    if result.returncode != 0:
        logger.warning(
            "ffprobe non-zero exit",
            extra={"event": "ffprobe.error", "file": str(path), "msg": result.stderr.strip()[:200]},
        )
        return None
    try:
        data = json.loads(result.stdout)
        dur_s = float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
    return int(dur_s * NANOS_PER_SECOND)


__all__ = ["probe_duration_nanos"]
