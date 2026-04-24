"""Daily-run orchestrator (DESIGN.md §7.1, §10).

Responsibilities:
  1. Discover `/scripts/<channel>/*.rb` — one subfolder per channel.
  2. Invoke Ruby runner for each to obtain plan AST.
  3. Resolve every collection + filler expression against Jellyfin.
  4. Expand each day in the 72h rolling window, honoring immutability /
     gap-fill rules (§10.2, §10.3).
  5. Atomically write playout, channel.json, per-channel XMLTV.
  6. Merge XMLTVs, regenerate lineup.json.
  7. GC files older than 48h.
  8. Write per-channel run markers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .config import Config
from .jellyfin.client import JellyfinClient
from .jellyfin.query import parse_query
from .jellyfin.resolver import QueryResolver
from .logging import get_logger, log_event
from .output import (
    merge_xmltv_files,
    render_channel_xmltv,
    write_channel_config,
    write_lineup_config,
    write_playout,
)
from .output.lineup import LineupEntry
from .planner import PlanAST, expand_day
from .planner.expander import build_resolved_pools
from .planner.fillers import PlayableItem
from .ruby_bridge import invoke_plan
from .state import StateStore, expression_sha
from .time_utils import format_iso_compact, load_tz

logger = get_logger(__name__)


@dataclass(slots=True)
class ChannelResult:
    channel: str
    files_written: list[Path] = field(default_factory=list)
    xmltv_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    items_written: int = 0


@dataclass(slots=True)
class RunResult:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    channels: list[ChannelResult] = field(default_factory=list)
    merged_xmltv: Path | None = None
    lineup_path: Path | None = None


def discover_channels(scripts_dir: str | Path) -> list[tuple[str, list[Path]]]:
    """Return a list of ``(channel_number, [script_path])`` sorted by number."""
    base = Path(scripts_dir)
    if not base.exists():
        return []
    out: list[tuple[str, list[Path]]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        scripts = sorted(child.glob("*.rb"))
        if scripts:
            out.append((child.name, scripts))
    return sorted(out, key=lambda x: x[0])


class Orchestrator:
    def __init__(
        self,
        config: Config,
        *,
        jellyfin_factory=None,
    ) -> None:
        self.config = config
        self._jf_factory = jellyfin_factory or self._default_jf_factory
        self._sem = asyncio.Semaphore(max(1, config.scheduler.channels_in_parallel))

    async def _default_jf_factory(self) -> JellyfinClient:
        return JellyfinClient(
            base_url=self.config.jellyfin.url,
            api_key=self.config.jellyfin_api_key(),
            timeout_s=self.config.jellyfin.request_timeout_s,
        )

    # ---- discovery / planning ----

    async def run_once(
        self,
        *,
        force: bool = False,
        only_channel: str | None = None,
        from_date: date | None = None,
    ) -> RunResult:
        run_id = datetime.now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        started = datetime.now()
        result = RunResult(run_id=run_id, started_at=started)
        log_event(logger, "run.started", "daily run started", run_id=run_id)

        tz = load_tz(self.config.effective_timezone())
        today = (from_date or date.today())
        window_days = [today + timedelta(days=i) for i in range(3)]  # 72h

        channels = discover_channels(self.config.scripts_dir)
        if only_channel:
            channels = [c for c in channels if c[0] == only_channel]
        if not channels:
            log_event(logger, "run.no_channels", "no channels found")
            return self._finalize(result)

        async def _worker(ch_entry: tuple[str, list[Path]]) -> ChannelResult:
            async with self._sem:
                return await self._run_channel(
                    ch_entry, window_days, tz, force=force, run_id=run_id,
                )

        tasks = [asyncio.create_task(_worker(c)) for c in channels]
        for t in asyncio.as_completed(tasks):
            result.channels.append(await t)

        # Merge + lineup + GC.
        self._merge_xmltvs(result)
        self._write_lineup(result)
        self._gc(tz)

        return self._finalize(result)

    def _finalize(self, result: RunResult) -> RunResult:
        result.finished_at = datetime.now()
        log_event(
            logger, "run.finished", "daily run finished",
            run_id=result.run_id,
            channels=len(result.channels),
        )
        runs_dir = Path(self.config.state_dir) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        marker = runs_dir / f"{result.run_id}.json"
        marker.write_text(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "started_at": result.started_at.isoformat(),
                    "finished_at": result.finished_at.isoformat(),
                    "channels": [
                        {
                            "channel": c.channel,
                            "files": [str(p) for p in c.files_written],
                            "xmltv": str(c.xmltv_path) if c.xmltv_path else None,
                            "items_written": c.items_written,
                            "errors": c.errors,
                        }
                        for c in result.channels
                    ],
                    "merged_xmltv": str(result.merged_xmltv) if result.merged_xmltv else None,
                    "lineup": str(result.lineup_path) if result.lineup_path else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return result

    async def _run_channel(
        self,
        ch_entry: tuple[str, list[Path]],
        days: list[date],
        tz,
        *,
        force: bool,
        run_id: str,
    ) -> ChannelResult:
        channel_number, scripts = ch_entry
        cr = ChannelResult(channel=channel_number)
        log_event(logger, "channel.started", "channel evaluation", channel=channel_number)

        try:
            ast_dict = invoke_plan(channel_number, scripts)
            plan = PlanAST.model_validate(ast_dict)
        except Exception as e:
            cr.errors.append(f"plan: {e}")
            log_event(logger, "channel.plan_error", "plan failed", channel=channel_number)
            return cr

        state_path = Path(self.config.state_dir) / f"channel-{channel_number}.sqlite"

        # Resolve Jellyfin pools once per channel.
        try:
            pools = await self._resolve_pools(plan)
        except Exception as e:
            cr.errors.append(f"resolve: {e}")
            log_event(logger, "channel.resolve_error", "resolve failed", channel=channel_number)
            return cr

        programmes: list = []

        playout_dir = Path(self.config.ersatztv.config_dir) / "channels" / channel_number / "playout"
        playout_dir.mkdir(parents=True, exist_ok=True)

        with StateStore(state_path) as state:
            state.start_run(run_id, notes=f"channel {channel_number}")
            try:
                # Update expression hashes & reset cursors as needed.
                for cname, c in plan.collections.items():
                    state.get_or_init_cursor(cname, expression_sha(c.expression))

                for d in days:
                    existing = self._existing_playout(playout_dir, d, tz)
                    if existing and not force:
                        cutoff = datetime.now() - timedelta(
                            hours=self.config.scheduler.window_hours_behind
                        )
                        if existing.stat().st_mtime >= cutoff.timestamp():
                            log_event(
                                logger, "channel.day_immutable", "skipping existing day",
                                channel=channel_number,
                            )
                            continue
                    exp = expand_day(plan, d, pools, tz)
                    path = write_playout(exp.items, playout_dir)
                    cr.files_written.append(path)
                    cr.items_written += len(exp.items)
                    programmes.extend(exp.programmes)

                    # Update recent_plays for random_with_memory collections.
                    for s in exp.items:
                        if s.collection and s.item and s.item.meta and not s.is_filler:
                            iid = s.item.meta.get("Id")
                            if iid:
                                state.record_play(s.collection, str(iid))

                state.prune_recent_plays()

                # Render channel.json
                channel_cfg = (
                    Path(self.config.ersatztv.config_dir)
                    / "channels" / channel_number / "channel.json"
                )
                write_channel_config(
                    plan.channel,
                    channel_cfg,
                    playout_folder=str(Path("/config/channels") / channel_number / "playout/"),
                )

                # Render per-channel XMLTV.
                xmltv_dir = Path(self.config.epg.per_channel_output_dir)
                xmltv_dir.mkdir(parents=True, exist_ok=True)
                xmltv_path = xmltv_dir / f"{channel_number}.xml"
                xmltv_path.write_bytes(render_channel_xmltv(plan.channel, programmes))
                cr.xmltv_path = xmltv_path

                state.finish_run(run_id, outcome="ok", items_written=cr.items_written)
            except Exception as e:
                cr.errors.append(f"expand/write: {e}")
                state.finish_run(run_id, outcome="error", items_written=cr.items_written, notes=str(e))
                log_event(logger, "channel.error", "channel failed", channel=channel_number)

        return cr

    async def _resolve_pools(self, plan: PlanAST):
        async with await self._jf_factory() as jf:
            resolver = QueryResolver(jf)
            collections_items: dict[str, list[dict]] = {}
            for name, c in plan.collections.items():
                collections_items[name] = await resolver.resolve(parse_query(c.expression))
            filler_local: dict[str, PlayableItem] = {}
            filler_collections: dict[str, list[dict]] = {}
            for kind, f in plan.fillers.items():
                if f.kind == "local":
                    filler_local[kind] = PlayableItem(
                        source_type="local",
                        path=f.path,
                        duration_nanos=1_000_000_000,  # 1s default; updated at planner emission
                    )
                elif f.kind == "collection" and f.expression:
                    filler_collections[kind] = await resolver.resolve(parse_query(f.expression))
            return build_resolved_pools(
                collections=collections_items,
                filler_local=filler_local,
                filler_collections=filler_collections,
            )

    def _existing_playout(self, playout_dir: Path, day: date, tz) -> Path | None:
        start_of_day = datetime.combine(day, time.min, tzinfo=tz)
        prefix = format_iso_compact(start_of_day)[:15]  # YYYYMMDDThhmmss
        for p in playout_dir.glob("*.json"):
            if p.name.startswith(prefix):
                return p
        return None

    def _merge_xmltvs(self, result: RunResult) -> None:
        paths = [c.xmltv_path for c in result.channels if c.xmltv_path]
        if not paths:
            return
        out = Path(self.config.epg.merged_output)
        merge_xmltv_files([p for p in paths if p is not None], out)
        result.merged_xmltv = out

    def _write_lineup(self, result: RunResult) -> None:
        entries: list[LineupEntry] = []
        for c in result.channels:
            if c.errors:
                continue
            cfg = Path(self.config.ersatztv.config_dir) / "channels" / c.channel / "channel.json"
            entries.append(LineupEntry(number=c.channel, name=c.channel, config=str(cfg)))
        if not entries:
            return
        out = Path(self.config.ersatztv.config_dir) / "lineup.json"
        result.lineup_path = write_lineup_config(
            entries,
            out,
            output_folder=self.config.ersatztv.output_folder,
            server_bind=self.config.ersatztv.server.bind_address,
            server_port=self.config.ersatztv.server.port,
        )

    def _gc(self, tz) -> None:
        """Delete playout files older than window_hours_behind (§7.1 step 11)."""
        hours = self.config.scheduler.window_hours_behind
        cutoff = datetime.now() - timedelta(hours=hours)
        base = Path(self.config.ersatztv.config_dir) / "channels"
        if not base.exists():
            return
        for channel_dir in base.iterdir():
            pdir = channel_dir / "playout"
            if not pdir.exists():
                continue
            for f in pdir.glob("*.json"):
                try:
                    if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                        f.unlink()
                        log_event(logger, "gc.removed", "removed stale playout", file=str(f))
                except OSError:
                    pass


__all__ = ["ChannelResult", "Orchestrator", "RunResult", "discover_channels"]
