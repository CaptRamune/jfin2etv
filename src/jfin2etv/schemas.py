"""Schema URIs and vendored-schema locators.

Per DESIGN.md section 12.3, the ErsatzTV-Next playout schema URI is a build-time
constant that travels with the jfin2etv release. Operators cannot override it;
bumping it is a code change.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

ERSATZTV_PLAYOUT_SCHEMA_URI = "https://ersatztv.org/playout/version/0.0.1"

XMLTV_GENERATOR_NAME = "jfin2etv"
XMLTV_SOURCE_NAME = "Jellyfin"


def vendored_schema_dir() -> Path:
    """Return the directory containing the vendored ErsatzTV-Next schemas."""
    root = Path(__file__).resolve().parents[2]
    return root / "vendor" / "ersatztv-schemas"


def load_vendored_schema(name: str) -> dict:
    """Load a vendored ErsatzTV-Next JSON schema by filename."""
    import json

    path = vendored_schema_dir() / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "ERSATZTV_PLAYOUT_SCHEMA_URI",
    "XMLTV_GENERATOR_NAME",
    "XMLTV_SOURCE_NAME",
    "vendored_schema_dir",
    "load_vendored_schema",
]
