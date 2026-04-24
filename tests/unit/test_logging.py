"""Tests for structured logging."""

from __future__ import annotations

import io
import json
import logging

from jfin2etv.logging import configure, get_logger, log_event


def test_emits_json_line_with_event_and_fields():
    buf = io.StringIO()
    configure(level="debug", stream=buf)
    logger = get_logger("jfin2etv.test")
    log_event(logger, event="channel.plan_loaded", msg="loaded", channel="01")
    buf.seek(0)
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "channel.plan_loaded"
    assert payload["channel"] == "01"
    assert payload["level"] == "info"
    # Clean up so other tests aren't polluted
    logging.getLogger().handlers.clear()
