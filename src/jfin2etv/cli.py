"""Command-line interface (DESIGN.md §13)."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

import click

from . import __version__
from .config import load_config
from .jellyfin.client import JellyfinClient
from .jellyfin.query import parse_query
from .jellyfin.resolver import QueryResolver
from .logging import configure as configure_logging
from .logging import get_logger
from .orchestrator import Orchestrator, discover_channels
from .ruby_bridge import RubyDslError, invoke_plan


@click.group()
@click.version_option(__version__)
@click.option("--config", "config_path", default=None, help="Path to jfin2etv.yml (default /config/jfin2etv.yml or $JFIN2ETV_CONFIG).")
@click.option("--log-level", default=None, help="Override logging level.")
@click.pass_context
def main(ctx: click.Context, config_path: str | None, log_level: str | None) -> None:
    cfg = load_config(config_path)
    if log_level:
        cfg.logging.level = log_level
    configure_logging(level=cfg.logging.level, stream=sys.stderr)
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg


@main.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Start the daemon (APScheduler + health server)."""
    from .daemon import run_daemon
    cfg = ctx.obj["config"]
    asyncio.run(run_daemon(cfg))


@main.command()
@click.option("--force", is_flag=True, help="Rewrite existing playout days.")
@click.option("--channel", "only_channel", default=None, help="Run a single channel.")
@click.option("--from", "from_date", default=None, help="Start date (YYYY-MM-DD), inclusive.")
@click.option("--dry-run", is_flag=True, help="Plan but do not write files.")
@click.pass_context
def once(
    ctx: click.Context,
    force: bool,
    only_channel: str | None,
    from_date: str | None,
    dry_run: bool,
) -> None:
    """Run a single daily cycle now."""
    cfg = ctx.obj["config"]
    from_d: date | None = None
    if from_date:
        from_d = date.fromisoformat(from_date)
    if dry_run:
        click.echo(json.dumps({"dry_run": True, "message": "not implemented fully in v1; use `plan` instead"}, indent=2))
        return
    orch = Orchestrator(cfg)
    result = asyncio.run(
        orch.run_once(force=force, only_channel=only_channel, from_date=from_d)
    )
    click.echo(
        json.dumps(
            {
                "run_id": result.run_id,
                "channels": [
                    {
                        "channel": c.channel,
                        "items_written": c.items_written,
                        "errors": c.errors,
                    }
                    for c in result.channels
                ],
            },
            indent=2,
        )
    )


@main.command()
@click.option("--channel", "only_channel", default=None, help="Validate a single channel.")
@click.pass_context
def validate(ctx: click.Context, only_channel: str | None) -> None:
    """Parse & validate scripts without hitting Jellyfin (Ruby VALIDATE_ONLY)."""
    cfg = ctx.obj["config"]
    channels = discover_channels(cfg.scripts_dir)
    if only_channel:
        channels = [c for c in channels if c[0] == only_channel]
    failures = 0
    for channel_number, scripts in channels:
        try:
            invoke_plan(channel_number, scripts, validate_only=True)
            click.echo(f"ok: {channel_number}")
        except RubyDslError as e:
            failures += 1
            click.echo(f"fail: {channel_number}: {e}", err=True)
        except Exception as e:  # noqa: BLE001
            failures += 1
            click.echo(f"fail: {channel_number}: {type(e).__name__}: {e}", err=True)
    sys.exit(1 if failures else 0)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print last-run summary per channel from the state DBs."""
    cfg = ctx.obj["config"]
    from .state import StateStore

    state_dir = Path(cfg.state_dir)
    out: list[dict] = []
    for db in sorted(state_dir.glob("channel-*.sqlite")):
        ch = db.stem.replace("channel-", "")
        with StateStore(db) as s:
            last = s.last_run()
        out.append({"channel": ch, "last_run": last})
    click.echo(json.dumps(out, indent=2, default=str))


@main.command()
@click.pass_context
def gc(ctx: click.Context) -> None:
    """Delete playout files older than the configured retention window."""
    cfg = ctx.obj["config"]
    orch = Orchestrator(cfg)
    orch._gc(None)  # noqa: SLF001 — intentional CLI escape hatch
    click.echo("ok")


@main.command()
@click.option("--channel", "only_channel", required=True, help="Channel number to plan.")
@click.pass_context
def plan(ctx: click.Context, only_channel: str) -> None:
    """Print the Ruby-side plan AST for a single channel."""
    cfg = ctx.obj["config"]
    channels = discover_channels(cfg.scripts_dir)
    matching = [c for c in channels if c[0] == only_channel]
    if not matching:
        click.echo(f"no channel {only_channel!r} found in {cfg.scripts_dir}", err=True)
        sys.exit(2)
    ast = invoke_plan(only_channel, matching[0][1])
    click.echo(json.dumps(ast, indent=2))


@main.command()
@click.argument("expression")
@click.pass_context
def resolve(ctx: click.Context, expression: str) -> None:
    """Resolve a Jellyfin query expression and print the matched items."""
    cfg = ctx.obj["config"]

    async def _run():
        async with JellyfinClient(
            base_url=cfg.jellyfin.url,
            api_key=cfg.jellyfin_api_key(),
            timeout_s=cfg.jellyfin.request_timeout_s,
        ) as jf:
            resolver = QueryResolver(jf)
            items = await resolver.resolve(parse_query(expression))
            click.echo(json.dumps([{"Id": i.get("Id"), "Name": i.get("Name"), "Type": i.get("Type")} for i in items], indent=2))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
