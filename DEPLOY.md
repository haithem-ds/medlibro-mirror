# Deploy MedLibro mirror (GitHub → Render)

This repo is laid out for a **Docker** deploy: `Data/` (question JSON) plus `medlibro_website_scraper/` (Flask + static `mirror/`).

## Environment variables

| Variable | Purpose | Default (local) |
|----------|---------|-----------------|
| `MEDLIBRO_DATA_DIR` | Folder with `1st.json`, … (and optional `*.jsonl`) | `/app/Data` in Docker |
| `MEDLIBRO_STATE_DIR` | Writable folder for `mirror_users.json` and `mirror_sessions.json` | App folder |
| `MEDLIBRO_YEAR_KEYS` | Comma list of keys to expose (e.g. `1st,2nd,3rd,4th,5th,6th,residency`). **Overrides** default and `MEDLIBRO_ALL_YEARS`. | *(see below)* |
| `MEDLIBRO_ALL_YEARS` | Set to `1` / `true` to expose **full** curriculum (all keys in code). Ignored if `MEDLIBRO_YEAR_KEYS` is set. | **`0`** (off): default is **1st, 2nd, 3rd, residency** only (4th–6th omitted) for fast `json.load` + LRU on small instances |
| `MEDLIBRO_PREFER_JSONL` | `1` / `true` if both `.json` and `.jsonl` exist: prefer streaming JSONL (lower peak RAM, slower). | **`0`**: prefer `.json` |
| `MEDLIBRO_JSON_CACHE_YEARS` | Max number of **full parsed** `.json` roots in RAM (LRU). Default = all active years, capped at **8** (`min(8, n)`). | **8** max fits default 4-year test set so **Revision** stays hot after warm load |
| `MEDLIBRO_SKIP_JSON_WARMUP` | `1` to skip preloading `.json` at first API init (faster cold boot, slower first **Revision**). | **`0`**: warm cache on startup |
| `PORT` | HTTP port | `8080` (Render sets this automatically) |

**Default (test):** the API and data layer only include **1er, 2ème, 3ème, Résidanat** — **4th–6th** are excluded so Render-style RAM stays safe and responses stay snappy.

**Full curriculum:** set either `MEDLIBRO_ALL_YEARS=1` or  
`MEDLIBRO_YEAR_KEYS=1st,2nd,3rd,4th,5th,6th,residency` in the dashboard.

**Optional JSONL:** to serve huge years on tiny RAM, generate `*.jsonl` with `build_jsonl.py` and set `MEDLIBRO_PREFER_JSONL=1`.

**Why Revision felt slow:** with a **single-year** cache, each year kicked the previous one out, so one request re-parsed every file. The server now keeps **several** parsed years (default: all active, max 8) and **warms** them on first API init unless `MEDLIBRO_SKIP_JSON_WARMUP=1`. On full curriculum + small RAM, set `MEDLIBRO_JSON_CACHE_YEARS=1` (old behavior) or use JSONL.

## GitHub

This folder is already a **git** repo with an initial commit (deploy-related paths only).

### GitHub authentication (so pushes work from Cursor or scripts)

**Do not put tokens in chat with an AI.** Use one of these on your machine only:

1. **Interactive (simplest):** in PowerShell run `gh auth login` and finish the browser or device-code steps.
2. **Token in environment (works without browser, good for automation):**
   - GitHub → **Settings** → **Developer settings** → **Personal access tokens** → create a **classic** token with the **`repo`** scope.
   - In PowerShell (current session only):

     ```powershell
     $env:GH_TOKEN = "ghp_your_token_here"
     ```

     Or persist for your user (new terminals only): `setx GH_TOKEN "ghp_your_token_here"` then open a **new** terminal.

   - Run `.\push-to-github.ps1` — it detects `GH_TOKEN` or `GITHUB_TOKEN` and runs `gh auth login --with-token` for you.

### Option A — GitHub CLI (fastest)

1. Install [GitHub CLI](https://cli.github.com/) if needed (`winget install GitHub.cli`).
2. Log in once: `gh auth login` (choose HTTPS and complete browser/device flow), **or** set `GH_TOKEN` as above.
3. From this directory run:

   ```powershell
   .\push-to-github.ps1
   ```

   Or pick another name: `.\push-to-github.ps1 my-medlibro-mirror`

   That creates a **public** repo under your account and pushes branch `main`.

### Option B — github.com

1. Create an empty repository (no README) on GitHub.
2. Add the remote and push:

   ```powershell
   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
   git push -u origin main
   ```

Do **not** commit secrets; `.gitignore` skips local session/user JSON, HARs, zip dumps, and `scraped_website/`.

Optional: copy `medlibro_website_scraper/mirror_users_seed.json.example` to `mirror_users_seed.json` and commit if you want seeded accounts in the image (still under the app directory, not state dir).

## Render

1. **New** → **Web Service** → connect the GitHub repo.
2. **Runtime**: Docker (Render will use the root `Dockerfile`).
3. No extra env vars are required; `PORT` is injected by Render.
4. **Ephemeral disk**: user signups live in `/data` in the container. On free tier, data can be lost on restarts. For durable accounts, add a **persistent disk** mounted at `/data` (paid feature) or accept ephemeral storage.

## Local Docker

From the repo root (folder that contains `Dockerfile`, `Data/`, `medlibro_website_scraper/`):

```bash
docker build -t medlibro-mirror .
docker run --rm -p 8080:8080 -e PORT=8080 medlibro-mirror
```

Open `http://localhost:8080`.
