"""APScheduler daemon + filesystem watcher (DESIGN.md §12.4)."""

from __future__ import annotations

import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from watchfiles import awatch

from .config import Config
from .logging import get_logger
from .orchestrator import Orchestrator
from .server import start_server
from .time_utils import load_tz

logger = get_logger(__name__)


async def _watch_scripts(scripts_dir: str) -> None:
    """Log but do not trigger runs on script edits (§12.4)."""
    try:
        async for changes in awatch(scripts_dir):
            for change, path in changes:
                logger.info(
                    "script changed (not triggering run)",
                    extra={"event": "watcher.change", "file": path},
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("script watcher stopped", extra={"event": "watcher.stopped", "msg": str(e)})


async def run_daemon(config: Config) -> None:
    tz = load_tz(config.effective_timezone())
    hh, mm = (int(x) for x in config.scheduler.run_time.split(":")[:2])
    scheduler = AsyncIOScheduler(timezone=tz)
    orch = Orchestrator(config)

    async def _job():
        try:
            await orch.run_once()
        except Exception as e:  # noqa: BLE001
            logger.error("scheduled run failed", extra={"event": "run.error", "msg": str(e)})

    scheduler.add_job(_job, CronTrigger(hour=hh, minute=mm, timezone=tz))
    scheduler.start()
    logger.info(
        "scheduler started",
        extra={"event": "scheduler.started", "file": f"{hh:02d}:{mm:02d} {tz}"},
    )

    runner = await start_server(config)
    watcher = asyncio.create_task(_watch_scripts(config.scripts_dir))

    stop_event = asyncio.Event()

    def _stop(*_args):
        stop_event.set()

    try:
        loop = asyncio.get_event_loop()
        if hasattr(loop, "add_signal_handler"):
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _stop)
                except NotImplementedError:
                    pass
    except NotImplementedError:
        pass

    await stop_event.wait()

    watcher.cancel()
    scheduler.shutdown(wait=False)
    await runner.cleanup()


__all__ = ["run_daemon"]
