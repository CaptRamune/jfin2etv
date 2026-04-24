# Publishing jfin2etv to GitHub + GHCR

This guide walks you — as a relative GitHub newcomer — from "I have a folder of source code on my machine" to "Dockge is pulling my image from the internet." Everything is a one-time setup except for step 7 (pushing updates), which becomes routine.

The Docker image lives in the **GitHub Container Registry (GHCR)**, which is automatically available to every GitHub account at no cost. The `ci.yml` workflow already in this repo builds and pushes the image for you — you just need to get the code on GitHub and flip a couple of switches.

---

## 0. What you'll need

- A GitHub account (free is fine). Sign up at https://github.com/ if you don't have one.
- [Git](https://git-scm.com/downloads) installed on your machine. Check with `git --version` in PowerShell.
- Your GitHub username. In every step below, replace `<YOUR_USERNAME>` with that — **all lowercase** in Docker image names (GHCR requires lowercase).

You do **not** need Docker Desktop on your local machine to publish. GitHub's servers build the image for you.

---

## 1. Replace the `OWNER` placeholder

Two files hard-code `ghcr.io/OWNER/jfin2etv` as a placeholder for your username. Swap them now:

- `.github/workflows/ci.yml` — find the line `images: ghcr.io/OWNER/jfin2etv` and change `OWNER` to your lowercase GitHub username.
- `stacks/jfin2etv/compose.yml` — find the line `image: ghcr.io/OWNER/jfin2etv:latest` and change `OWNER` the same way.

For example, if your GitHub username is `JaneDoe`:

```yaml
images: ghcr.io/janedoe/jfin2etv
```

```yaml
image: ghcr.io/janedoe/jfin2etv:latest
```

Save both files.

---

## 2. Initialize git locally

Open PowerShell in the `jfin2etv-main` folder and run:

```powershell
cd C:\Users\captr\Documents\Cursor\jfin2etv\jfin2etv-main
git init -b main
git add .
git status
```

`git status` should show a list of files staged for commit. If it's pages long, that's fine — the `.gitignore` file in this repo already excludes caches, lockfiles that shouldn't be committed, and secrets.

Commit:

```powershell
git commit -m "Initial import of jfin2etv v1"
```

If git complains that your identity isn't configured, run these once (they can be anything — they just show up in commit history):

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Then re-run the `git commit` line.

---

## 3. Create the empty GitHub repository

1. In a browser, go to https://github.com/new.
2. **Repository name:** `jfin2etv` (or whatever you like — just keep it consistent with step 1).
3. **Description:** optional.
4. **Public or Private:** either works. Public is simpler because the published Docker image can then be pulled by anyone (including your Dockge host) without credentials. Private is also fine; step 6 shows how to unlock pulls.
5. **Do NOT** check "Add a README," "Add .gitignore," or "Choose a license." The repo already contains these, and pre-filling them will cause a merge conflict on your first push.
6. Click **Create repository**.

GitHub will now show you a page titled "Quick setup." Leave it open; you'll use the URL it shows in the next step.

---

## 4. Connect your local repo to GitHub and push

On the "Quick setup" page, copy the HTTPS URL under "…or push an existing repository from the command line." It looks like `https://github.com/<YOUR_USERNAME>/jfin2etv.git`.

Back in PowerShell:

```powershell
git remote add origin https://github.com/<YOUR_USERNAME>/jfin2etv.git
git push -u origin main
```

A browser popup (or a terminal prompt) will ask you to sign in to GitHub. Use your GitHub credentials; on modern git on Windows this uses Git Credential Manager and only happens once.

If the push succeeds, refresh your GitHub repo page — you should see all the files.

---

## 5. Let CI build your first image

The push in step 4 automatically triggered the GitHub Actions workflow defined in `.github/workflows/ci.yml`. Click the **Actions** tab at the top of your GitHub repo page. You'll see a run in progress titled "CI."

Wait for all jobs to complete (5–15 minutes for the first run because nothing is cached yet):

- `Python` — runs the pytest suite and linters.
- `Ruby` — runs RSpec.
- `End-to-end` — skipped unless you scheduled a nightly run or included `[e2e]` in the commit message. Ignore it.
- `Docker image` — builds for `linux/amd64` + `linux/arm64` and pushes to GHCR.

Once the **Docker image** job has a green check, your image is published. You can find it at:

```
https://github.com/<YOUR_USERNAME>?tab=packages
```

It will be listed as `jfin2etv`.

---

## 6. Make the image pullable from Dockge

GHCR images default to **private**, which means Dockge (on your Ubuntu server) can't pull them unless it authenticates. You have two options; pick one.

### Option A — make the image public (simplest)

1. Go to your package page: `https://github.com/users/<YOUR_USERNAME>/packages/container/jfin2etv`.
2. On the right, click **Package settings**.
3. Scroll to the bottom to **Danger Zone → Change visibility**.
4. Click **Change visibility**, pick **Public**, and confirm.

That's it — any Docker host can now pull `ghcr.io/<YOUR_USERNAME>/jfin2etv:latest` without credentials.

### Option B — keep it private and log Docker in on the server

On the Ubuntu host:

1. Create a GitHub **Personal Access Token (classic)** at https://github.com/settings/tokens/new with the single scope `read:packages`. Copy the token — you won't see it again.
2. SSH into your Ubuntu server and run:
   ```bash
   echo <THE_TOKEN> | docker login ghcr.io -u <YOUR_USERNAME> --password-stdin
   ```
   Docker will save the credentials in `~/.docker/config.json`; Dockge then inherits them.

Dockge will now successfully pull the private image.

---

## 7. Pulling and running on the Ubuntu host (via Dockge)

You already have the compose files for this — `stacks/jellyfin/compose.yml` and `stacks/jfin2etv/compose.yml`. On the host:

1. One-time: `docker network create media_proxy`.
2. In Dockge, create two stacks, one per file. For stack 2 (`jfin2etv`):
   - Paste the contents of `stacks/jfin2etv/compose.yml`.
   - In the **Environment variables** / `.env` section, set `JELLYFIN_API_KEY=<your Jellyfin API key>`.
   - Hit **Deploy**. Dockge runs `docker compose pull && docker compose up -d`, which fetches `ghcr.io/<YOUR_USERNAME>/jfin2etv:latest` from GHCR.
3. Follow logs from Dockge's UI. After the first daily run (or `docker compose exec jfin2etv jfin2etv once`), ErsatzTV-Next will start serving the M3U.

---

## 8. Shipping changes

After the initial setup, your update loop is:

```powershell
# edit files locally, then:
git add .
git commit -m "Describe what changed"
git push
```

That push triggers CI again. Within ~5 minutes you'll have a fresh image tagged with:

- `ghcr.io/<YOUR_USERNAME>/jfin2etv:main` — whatever's on the `main` branch.
- `ghcr.io/<YOUR_USERNAME>/jfin2etv:sha-<first 7 chars of commit>` — pinned to that exact commit, handy for rollbacks.

On the host, pull the new image:

```bash
docker compose pull jfin2etv && docker compose up -d jfin2etv
```

(Or use Dockge's "Update" button on the stack.)

---

## 9. (Optional) Release tagging

When you want a versioned release (e.g. for a friend who wants a stable pin):

```powershell
git tag v0.1.0
git push origin v0.1.0
```

CI sees the tag and additionally tags the image as:

- `ghcr.io/<YOUR_USERNAME>/jfin2etv:v0.1.0`
- `ghcr.io/<YOUR_USERNAME>/jfin2etv:0.1`
- `ghcr.io/<YOUR_USERNAME>/jfin2etv:latest` (only on tagged pushes; branch pushes do **not** update `:latest`)

Follow [SemVer](https://semver.org/) — `v0.1.0`, `v0.1.1`, `v0.2.0`, etc.

---

## Troubleshooting

**Image job fails with "permission denied" on push to GHCR.**
Go to your GitHub repo → **Settings → Actions → General → Workflow permissions**. Select **"Read and write permissions"** and save. Re-run the failed job from the **Actions** tab.

**`docker compose pull` on the host says "unauthorized" or "not found".**
Either the image is still private (revisit step 6) or the image name has a typo. Remember: the part after `ghcr.io/` must be **all lowercase**, even if your GitHub username has capitals.

**CI keeps running on every single push and I just edited the README.**
That's expected — the workflow runs on every push. The Docker image only gets rebuilt on pushes to `main` and on `v*` tags, so README-only commits are cheap (just python + ruby + e2e jobs).

**I want to delete an old image version to save quota.**
Go to your package page → **Package settings → Manage versions** → delete individual tags there. GHCR storage is free for public images, so this rarely matters.

**I pushed before replacing `OWNER` and CI failed.**
Fix `ci.yml` and `compose.yml` locally, commit, push again — the next run will succeed. The failed run can be ignored.
