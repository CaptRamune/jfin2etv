"""Structured JSON logging for jfin2etv (DESIGN.md §14.1)."""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from datetime import UTC, datetime
from typing import Any

LEVELS = {
    "debug": stdlib_logging.DEBUG,
    "info": stdlib_logging.INFO,
    "warning": stdlib_logging.WARNING,
    "error": stdlib_logging.ERROR,
}


class JsonFormatter(stdlib_logging.Formatter):
    """Render every record as a single-line JSON object.

    Records can carry extra fields via `logger.info("msg", extra={...})`.
    Standard fields always emitted: `ts`, `level`, `event`, `msg`.
    """

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", record.name),
            "msg": record.getMessage(),
        }
        for key in ("channel", "collection", "file", "run_id", "items_written"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str = "info", stream: Any = None) -> None:
    """Configure root logger for JSON output. Idempotent."""
    root = stdlib_logging.getLogger()
    root.setLevel(LEVELS.get(level.lower(), stdlib_logging.INFO))
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = stdlib_logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> stdlib_logging.Logger:
    return stdlib_logging.getLogger(name)


def log_event(logger: stdlib_logging.Logger, event: str, msg: str = "", **fields: Any) -> None:
    """Emit an event-shaped log entry."""
    extra = {"event": event, **fields}
    logger.info(msg, extra=extra)


__all__ = ["JsonFormatter", "configure", "get_logger", "log_event"]
