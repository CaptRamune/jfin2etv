# jfin2etv

**jfin2etv** is a scheduler that compiles [Jellyfin](https://jellyfin.org) libraries and a small Ruby DSL into the playout JSON and XMLTV EPG consumed by [ErsatzTV-Next](https://github.com/ErsatzTV/Next) — letting you build broadcast-style IPTV channels with a few lines of Ruby, a daily cron, and no persistent GUI state.

The design contract is [`DESIGN.md`](DESIGN.md). This README is the quickstart.

## What's in the stack

| Piece | Role |
|---|---|
| **Jellyfin** | authoritative media library (metadata, thumbnails, paths) |
| **ErsatzTV-Next** | IPTV server that turns playout JSON + media into an M3U / HLS feed |
| **jfin2etv** (this repo) | nightly scheduler that queries Jellyfin, evaluates your Ruby channel scripts, and emits playout JSON + XMLTV |
| **Traefik** | serves the M3U and XMLTV over HTTPS to clients |

## Quickstart (Docker + Dockge)

> You'll need Docker Engine with the `compose` plugin on the host. These instructions assume you already have [Dockge](https://dockge.kuma.pet/) and [Traefik](https://doc.traefik.io/traefik/) running.

1. **Create the shared network** once on the host:

   ```bash
   docker network create media_proxy
   ```

2. **Deploy the Jellyfin stack** from [`stacks/jellyfin/compose.yml`](stacks/jellyfin/compose.yml). Edit the `Host(...)` label to your hostname.

3. In Jellyfin: add your library, create an **API key** under *Dashboard → API Keys*.

4. **Deploy the ErsatzTV-Next + jfin2etv stack** from [`stacks/jfin2etv/compose.yml`](stacks/jfin2etv/compose.yml). In the stack's `.env` set:

   ```env
   JELLYFIN_API_KEY=<the key you just made>
   ```

   Also swap `ghcr.io/OWNER/jfin2etv:latest` for your published image tag.

5. **Drop channel scripts** into the stack's bind-mounted directory:

   ```
   ./jfin2etv/scripts/01/main.rb   # copy examples/scripts/01/main.rb
   ./jfin2etv/scripts/02/main.rb
   ./jfin2etv/scripts/03/main.rb
   ```

   The three bundled examples (`examples/scripts/{01,02,03}`) correspond to DESIGN.md §18 (Classic Rock Videos, Toonz, Springfield).

6. **Drop the config** (optional — all values have defaults):

   ```
   ./jfin2etv/config/jfin2etv.yml   # copy examples/config/jfin2etv.yml
   ```

7. **Wait for 04:00** (the default daily run time) or force one immediately:

   ```bash
   docker compose exec jfin2etv jfin2etv once
   ```

   ErsatzTV-Next picks up the emitted playout JSON and the M3U is available at `http://tv.example.com/iptv`. The XMLTV guide is at `http://tv.example.com/epg/epg.xml`.

## Local development

### Python (uv)

```bash
cd jfin2etv-main
uv sync --extra dev
uv run pytest          # unit suite; E2E tests are excluded by default
uv run ruff check .
uv run mypy src/
```

### Ruby (bundler)

```bash
cd jfin2etv-main
bundle install
bundle exec rspec
```

### End-to-end tests

Spin up real Jellyfin + ErsatzTV-Next containers. Requires Docker, a small media fixture, and a Jellyfin API key. Opt-in:

```bash
JFIN2ETV_E2E=1 JELLYFIN_API_KEY=<key> uv run pytest -m slow tests/e2e
```

## CLI cheatsheet

All commands live under the `jfin2etv` entry point (inside the container: `docker compose exec jfin2etv jfin2etv <cmd>`).

| Command | What it does |
|---|---|
| `run` | Start the daemon: cron trigger + HTTP server (`/healthz`, `/metrics`, `/epg`). Default `CMD` in the Docker image. |
| `once` | Execute one full orchestration pass and exit. Supports `--force`, `--from YYYY-MM-DD`, `--channel N` (repeatable), `--dry-run`. |
| `validate [--channel N]` | Parse every Ruby script; report DSL errors. No Jellyfin calls. |
| `status` | Print last-run markers and channel state summaries. |
| `gc` | Delete playout / EPG entries older than the GC horizon. |
| `plan --channel N` | Dump the raw plan AST emitted by the Ruby runner (debugging). |
| `resolve --channel N [--collection NAME]` | Run collection queries and print resolved items (debugging). |

Examples:

```bash
docker compose exec jfin2etv jfin2etv validate --channel 03
docker compose exec jfin2etv jfin2etv plan --channel 03
docker compose exec jfin2etv jfin2etv once --force
docker compose exec jfin2etv jfin2etv resolve --channel 01 --collection rock_videos
docker compose exec jfin2etv jfin2etv status
```

## Project layout

```
jfin2etv-main/
  DESIGN.md                     authoritative spec
  README.md                     (you are here)
  Dockerfile                    production image (Python 3.12 + MRI Ruby + ffmpeg)
  pyproject.toml  uv.lock       Python deps (uv)
  Gemfile         Gemfile.lock  Ruby deps (bundler)
  src/jfin2etv/                 Python host: CLI, planner, orchestrator, output writers
  lib/jfin2etv/                 Ruby DSL: plan, validation, serializer, runner
  examples/scripts/{01,02,03}/  the three §18 channels, ready to copy into /scripts
  examples/config/jfin2etv.yml  fully-commented host config
  stacks/jellyfin/              Dockge stack 1
  stacks/jfin2etv/              Dockge stack 2 (ErsatzTV-Next + jfin2etv)
  tests/                        pytest suite (unit + optional e2e)
  spec/                         rspec suite
  vendor/ersatztv-schemas/      vendored snapshot of ErsatzTV-Next's JSON schemas
  .github/workflows/ci.yml      GitHub Actions (python, ruby, e2e, image)
```

## Troubleshooting

- **`jfin2etv once` fails with `JELLYFIN_API_KEY not set`** — the env var is required; set it in the stack's `.env`.
- **ErsatzTV-Next sees no channels** — check that `/ersatztv-config/channels/<N>/playout/` contains a `*.json` file after the run and that `/ersatztv-config/lineup.json` lists it. Re-run with `jfin2etv once --force`.
- **XMLTV is empty for a channel** — run `jfin2etv resolve --channel N` to confirm collections are matching items.
- **`jfin2etv status`** shows the last successful run per channel; use it to confirm the cron job is actually running.
- **State got wedged** — delete `/state/channel-<N>.sqlite`; it'll be re-created on the next run (you lose shuffle memory but not media).

## License

MIT. See `DESIGN.md` §0 for authorship and references.
