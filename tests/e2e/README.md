# End-to-end tests

These tests spin up real Jellyfin and ErsatzTV-Next containers via Docker Compose,
drop a minimal Ruby DSL script in place, run `jfin2etv once`, and validate the
resulting playout JSON (against the vendored ErsatzTV-Next schema) and the
merged XMLTV file (against `xmltv.dtd`).

## Prerequisites

- Docker Engine + the `compose` plugin
- A small media fixture under `tests/e2e/fixture/media/` (e.g. a few public-domain Blender
  shorts); the suite skips gracefully if no fixture is found or Docker is unavailable
- `xmltv.dtd` at `tests/e2e/fixture/xmltv.dtd`

## Running

```bash
JFIN2ETV_E2E=1 JELLYFIN_API_KEY=<key> pytest -m slow tests/e2e
```

They are marked `slow` and excluded from the default test run.
