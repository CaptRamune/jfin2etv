"""Ruby-to-Python bridge (DESIGN.md §6).

Spawns the MRI Ruby subprocess that evaluates a channel's DSL scripts and
emits the plan AST as JSON. Also supports re-entering Ruby to evaluate a
variant selector Proc for a given date (§6.2).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .logging import get_logger

logger = get_logger(__name__)

RUBY_BIN_ENV = "JFIN2ETV_RUBY_BIN"
DEFAULT_TIMEOUT_S = 30


class RubyBridgeError(Exception):
    """Base class for Ruby bridge failures."""


class RubyDslError(RubyBridgeError):
    """Raised when the Ruby runner exits with status 2 (DSL error)."""


class RubyRuntimeError(RubyBridgeError):
    """Raised when the Ruby runner exits with status 1 (uncaught exception)."""


class RubyTimeoutError(RubyBridgeError):
    """Raised when the Ruby runner exceeds its wall-clock timeout."""


@dataclass(slots=True)
class RubyResult:
    stdout: str
    stderr: str
    exit_code: int


def _ruby_bin() -> str:
    return os.environ.get(RUBY_BIN_ENV, "ruby")


def _lib_root() -> Path:
    """Return the on-disk directory containing lib/jfin2etv.rb.

    Precedence:
      1. `JFIN2ETV_LIB_DIR` env var (for containerized deploys — set to
         `/app/lib`).
      2. The `lib/` directory adjacent to the Python source checkout.
    """
    env_dir = os.environ.get("JFIN2ETV_LIB_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "lib"


def invoke_plan(
    channel: str,
    script_paths: list[str | Path],
    *,
    validate_only: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """Evaluate the given scripts via the Ruby runner and return the plan AST.

    Exit codes map to exceptions per DESIGN.md §6.3.
    """
    scripts = [str(p) for p in script_paths]
    env = {**os.environ, **(extra_env or {})}
    if validate_only:
        env["VALIDATE_ONLY"] = "1"

    cmd = [
        _ruby_bin(),
        "-I",
        str(_lib_root()),
        "-r",
        "jfin2etv/runner",
        "-e",
        f"Jfin2etv::Runner.run({json.dumps(scripts)}, channel: {json.dumps(channel)})",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RubyTimeoutError(
            f"ruby runner for channel {channel!r} timed out after {timeout_s}s"
        ) from e

    if result.stderr:
        for line in result.stderr.rstrip().splitlines():
            logger.info(line, extra={"event": "ruby.stderr", "channel": channel})

    if result.returncode == 0:
        if validate_only:
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RubyRuntimeError(
                f"ruby runner for channel {channel!r} returned invalid JSON: {e}"
            ) from e
    if result.returncode == 2:
        raise RubyDslError(result.stderr.strip() or "DSL error")
    raise RubyRuntimeError(
        f"ruby runner for channel {channel!r} failed with exit code {result.returncode}: {result.stderr.strip()}"
    )


def invoke_variant_selector(
    proc_source: str,
    target_date: date,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Evaluate a captured variant-selector Proc for `target_date`.

    Returns the variant key as a string (the Proc must return a Symbol or
    String; both serialize to a JSON string).
    """
    cmd = [
        _ruby_bin(),
        "-I",
        str(_lib_root()),
        "-r",
        "jfin2etv/selector",
        "-e",
        "exit Jfin2etv::Selector.run_proc(ENV.fetch('PROC_SOURCE'), ENV.fetch('DATE'))",
    ]
    env = {**os.environ, "PROC_SOURCE": proc_source, "DATE": target_date.isoformat()}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RubyTimeoutError("variant selector timed out") from e

    if result.returncode != 0:
        raise RubyDslError(
            f"variant selector evaluation failed: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RubyRuntimeError(
            f"variant selector returned invalid JSON: {result.stdout!r}"
        ) from e


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "RubyBridgeError",
    "RubyDslError",
    "RubyResult",
    "RubyRuntimeError",
    "RubyTimeoutError",
    "invoke_plan",
    "invoke_variant_selector",
]
