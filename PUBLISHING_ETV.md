# Building your own ErsatzTV-Next Docker image

ErsatzTV-Next does not currently publish a Docker image to any public registry, but the upstream repo already includes a working `docker/Dockerfile`. The simplest path is to fork the project on GitHub, add a single workflow file that publishes to your own GHCR, and let GitHub's runners do the build for you. **No Docker installation on your local machine is required.**

This guide assumes you've already worked through [`PUBLISHING.md`](PUBLISHING.md) for jfin2etv, so a few of the GitHub fundamentals (Actions, GHCR, package visibility) are referenced rather than re-explained.

---

## 1. Fork the upstream repo

1. In a browser, go to https://github.com/ErsatzTV/next.
2. In the top-right, click **Fork**.
3. Owner: your account. Repository name: leave as `next` (or rename if you prefer; just be consistent below).
4. Leave **"Copy the main branch only"** checked.
5. Click **Create fork**.

After a moment you'll be looking at `https://github.com/<YOUR_USERNAME>/next` — your own copy of the source.

---

## 2. Add a publishing workflow

Forking gave you all the source code, but the upstream's existing publishing workflow needs Docker Hub credentials we don't have and pushes to `ghcr.io/ersatztv/next` (which you can't write to). We'll add a small parallel workflow that pushes to **your** GHCR namespace.

In your fork's GitHub web UI:

1. Click **Add file → Create new file**.
2. Name it: `.github/workflows/ghcr.yml` (the `/` characters create folders for you).
3. Paste in the entire contents of [`stacks/ersatztv-next/ghcr.yml`](stacks/ersatztv-next/ghcr.yml) from the jfin2etv repo (also reproduced below for convenience).
4. Scroll down, write a short commit message like `Add GHCR publishing workflow`, leave "Commit directly to the main branch" selected, and click **Commit new file**.

```yaml
name: Publish to GHCR

on:
  push:
    branches: [main]
    tags: ["v*"]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  image:
    name: Build and push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/ersatztv-next
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ./docker/Dockerfile
          platforms: linux/amd64
          push: true
          provenance: false
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

> **Why amd64 only?** Upstream's own workflow has the arm32v7 and arm64 build targets commented out (they're in `next-main/.github/workflows/docker.yml` if you're curious) — the ffmpeg base image they're built on isn't published for ARM yet. If you're on an x86 server (almost certainly true for a Dockge homelab), this is exactly what you want. If you're on a Raspberry Pi or similar, this approach won't work yet and you'd be better off waiting for upstream to publish multi-arch images.

---

## 3. Watch the build

The commit you just made auto-triggered the workflow. Click the **Actions** tab on your fork and wait for the **Publish to GHCR** run to finish.

Heads-up: **the first build is slow** — Rust compilation from scratch with all dependencies typically takes 15–30 minutes. Subsequent builds will be ~3–5 minutes thanks to the GHA layer cache. Get a coffee.

If it finishes with a green check, you'll find the published package at:

```
https://github.com/<YOUR_USERNAME>?tab=packages
```

It will be listed as `ersatztv-next`.

---

## 4. Make the image pullable

Same drill as the jfin2etv image (see `PUBLISHING.md` §6). Easiest path:

1. Click into the `ersatztv-next` package.
2. Right-side: **Package settings → Danger Zone → Change visibility → Public**.

Now any Docker host (your Ubuntu server included) can pull `ghcr.io/<YOUR_USERNAME>/ersatztv-next:latest` without credentials.

---

## 5. Wire it into the jfin2etv Dockge stack

The compose file at `stacks/jfin2etv/compose.yml` currently references the placeholder image `ghcr.io/ersatztv/next:latest` (which doesn't exist). Change it to point at your build:

Open `stacks/jfin2etv/compose.yml` and find the `ersatztv:` service. Update its `image:` line:

```yaml
services:
  ersatztv:
    image: ghcr.io/<YOUR_USERNAME>/ersatztv-next:latest
    # ... everything else stays the same
```

Commit and push that change to your jfin2etv repo (or just edit the stack file directly inside Dockge and click **Update**).

---

## 6. Day-to-day: keeping up with upstream

The advantage of forking (vs copy-pasting the source into a brand-new repo) is that pulling future updates is trivial:

1. Visit your fork's main page on GitHub.
2. If there's a notice like **"This branch is N commits behind ErsatzTV/next:main"**, click **Sync fork → Update branch**.
3. That sync push triggers your workflow. ~3–5 minutes later your `:latest` tag has the upstream's newest commit baked in.
4. On the host: `docker compose pull ersatztv && docker compose up -d ersatztv`.

That's it — no rebasing, no merging, no local Docker. Whenever ErsatzTV-Next ships a fix you want, three clicks and a `docker compose pull` get it to your server.

---

## Troubleshooting

**Workflow fails with "permission denied" on `docker push`.**
Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save. Re-run the failed workflow.

**Build fails inside the cargo-chef stage with cryptic Rust errors.**
This generally means upstream pushed a commit that doesn't compile yet — they're explicit that the project is in early-stage active development. Either wait a day for them to fix it, or temporarily change the workflow trigger to `workflow_dispatch` only (so you build only when you click "Run workflow") and pick a known-good commit by syncing the fork to a specific commit instead of `main`.

**The ErsatzTV container exits immediately on startup.**
Check the container logs from Dockge. Most likely you haven't created the `ersatztv/config/lineup.json` file yet (see DESIGN.md §4 for the canonical layout, or copy `next-main/examples/lineup.json` as a starting point and edit the channel paths). jfin2etv generates `lineup.json` for you on its first successful run — so this typically resolves itself once the daily 04:00 job has fired.
