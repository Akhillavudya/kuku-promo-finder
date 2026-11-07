# Promo finder

Reads a microdrama screenplay and finds the 20-60 second stretches that work
as a standalone promo: hooked inside the first three seconds, cut on an
unresolved cliffhanger, understandable to someone who has seen nothing else.

Output is episode + ordered segment timestamps + the hook line + the
cliffhanger + one line on why it works, plus a ranking and an account of
where it picks badly.

**The screenplay pack is not in this repository and never will be.** It was
shared for one assignment and `.gitignore` and `.dockerignore` both exclude
it. The shipped outputs quote only the hook and cliffhanger lines.

## Shape

- `src/promo/` — the pipeline. Parsing, the 3-second hook gate, the duration
  gate, scoring, selection. The deterministic half is Python; the LLM returns
  **block indices and scores, never timestamps**.
- `src/promo/llm/` — provider router: tier dispatch, rate limiting, backoff,
  failover, response cache. Providers grouped by cost under `free/`, `paid/`,
  `local/`.
- `api/main.py` — five endpoints over functions that already exist. No
  scoring or timestamp arithmetic lives here.
- `web/` — React 18 + Vite + TypeScript. No UI framework, no CSS framework,
  no chart library.
- `outputs/` — what the last full 50-episode run wrote. The Season view reads
  this, so it needs no API key and makes no model call.

## Run it locally

```bash
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -r requirements.txt
python -m promo.run                               # the season -> outputs/
```

The demo, same-origin, one URL:

```bash
cd web && npm install && npm run build            # writes web/dist
cd .. && pip install -r api/requirements.txt
uvicorn api.main:app --port 8000                  # serves the API *and* dist
```

Or with hot reload, two processes — Vite proxies `/api` to :8000, so the
browser still sees one origin and no CORS is involved:

```bash
uvicorn api.main:app --reload --port 8000
cd web && npm run dev                             # http://localhost:5173
```

A live run needs `GEMINI_API_KEY` in `.env` (see `.env.example`), or a key
pasted into the Settings dialog, which is used for that one request and never
stored. The Season view needs neither.

## Deploy

Two halves on two hosts: the static frontend on shared hosting, the API on
Render. A static host cannot proxy `/api`, which is why the frontend needs the
backend's absolute URL and the backend needs a CORS allowlist.

The Render image also builds and serves `web/dist` itself, so **the Render URL
is a complete working copy of the app on its own** — a useful fallback.

### 1. Backend, on Render

New → Blueprint, pointed at this repo; `render.yaml` describes it (Docker,
free plan, healthcheck `/api/health`). Then in the dashboard set:

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | your key — **dashboard only, never in a file here** |
| `ALLOWED_ORIGINS` | the frontend's exact origin, e.g. `https://promofinder.byfrontage.com` |

`ALLOWED_ORIGINS` is comma-separated and scheme-exact: `https://` and
`http://` are different origins, as are `example.com` and `www.example.com`.
Changing it needs a restart, not a rebuild.

Verify before going further:

```
https://<service>.onrender.com/api/health     -> {"ok": true, ...}
https://<service>.onrender.com/api/season     -> the promos
https://<service>.onrender.com/               -> the whole app
```

Free plan spins down when idle; the first request after that waits on a cold
start. The Season view is precomputed JSON for exactly this reason — once the
page is up, only a live run is slow.

### 2. Frontend, on shared hosting

Put the real Render URL in `web/.env.production`, then build:

```bash
cd web && npm run build
```

`VITE_API_BASE` is **baked into the bundle at build time**. Pointing the
frontend at a different backend means a rebuild and a re-upload.

Upload the *contents* of `web/dist` — not the folder itself — to the
subdomain's document root. Confirm `index.html` sits at the root and
`assets/` beside it.

Then set `ALLOWED_ORIGINS` on Render to that subdomain's `https://` origin and
restart.

### 3. Verify the deployed pair

Open the subdomain and check, in order:

- the Season view fills — that is one `GET /api/season` across origins
- the browser console has no CORS error and no mixed-content warning
- a live run completes, allowing for one cold start on the first attempt
- nothing scrolls sideways at 320px wide

A failure here is almost always one of three things: `VITE_API_BASE` still
pointing somewhere stale, an `ALLOWED_ORIGINS` value that does not match the
browser's origin character for character, or the frontend served over `http://`
while the allowlist names `https://`.
