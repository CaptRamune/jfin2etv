"""aiohttp server exposing /healthz, /metrics, and static /epg (DESIGN.md §14)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from .config import Config
from .logging import get_logger
from .state import StateStore

logger = get_logger(__name__)


def _last_run_at(state_dir: str) -> datetime | None:
    latest: datetime | None = None
    for db in Path(state_dir).glob("channel-*.sqlite"):
        try:
            with StateStore(db) as s:
                last = s.last_run()
                if last and last.get("finished_at"):
                    ts = datetime.fromisoformat(str(last["finished_at"]))
                    if latest is None or ts > latest:
                        latest = ts
        except Exception:  # noqa: BLE001
            continue
    return latest


class HealthServer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.app = web.Application()
        self.registry = CollectorRegistry()
        self._last_run_gauge = Gauge(
            "jfin2etv_last_run_age_seconds",
            "Seconds since the most recent successful daily run.",
            registry=self.registry,
        )
        self._channels_gauge = Gauge(
            "jfin2etv_channels_configured",
            "Number of channels discovered in /scripts.",
            registry=self.registry,
        )
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/healthz", self._healthz)
        self.app.router.add_get("/metrics", self._metrics)
        epg = Path(self.config.epg.per_channel_output_dir).parent
        if epg.exists():
            self.app.router.add_static("/epg", str(epg), show_index=True, follow_symlinks=True)

    async def _healthz(self, request: web.Request) -> web.Response:
        last = _last_run_at(self.config.state_dir)
        if last is None:
            return web.json_response({"status": "unknown", "last_run": None}, status=503)
        age = datetime.now() - last
        ok = age < timedelta(hours=36)
        return web.json_response(
            {"status": "ok" if ok else "stale", "last_run": last.isoformat(), "age_seconds": int(age.total_seconds())},
            status=200 if ok else 503,
        )

    async def _metrics(self, request: web.Request) -> web.Response:
        from .orchestrator import discover_channels

        self._channels_gauge.set(len(discover_channels(self.config.scripts_dir)))
        last = _last_run_at(self.config.state_dir)
        if last is not None:
            self._last_run_gauge.set((datetime.now() - last).total_seconds())
        body = generate_latest(self.registry)
        return web.Response(body=body, content_type="text/plain; version=0.0.4")


async def start_server(config: Config) -> web.AppRunner:
    host, port = config.health.host_port
    server = HealthServer(config)
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("health server started", extra={"event": "server.started", "file": f"{host}:{port}"})
    return runner


__all__ = ["HealthServer", "start_server"]
