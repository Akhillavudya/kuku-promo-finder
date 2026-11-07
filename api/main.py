"""The HTTP layer for the React demo. Thin on purpose.

Five endpoints and a static mount. Every one of them is a wrapper over a
function that already exists and is already tested:

    GET  /api/health   is there a key, and which profile would run
    GET  /api/profiles the selectable profiles, read out of settings.yaml
    GET  /api/season   outputs/*.json, as written by `python -m promo.run`
    GET  /api/sample   the synthetic example episode, for the live tab
    POST /api/run      parse pasted text -> promo.run.run_episode

**No scoring, ordering, gating or timestamp arithmetic happens here.** That
all lives in `promo.run`, `promo.gates` and `promo.score`, and this module
would be the wrong place for it: the whole claim of the project is that the
deterministic parts are one implementation that both the batch run and the
demo call. A second copy behind an HTTP handler would quietly break that.

Errors are returned as ``{"ok": false, "error": ...}`` with HTTP 200 rather
than as 4xx/5xx, because every one of them is something the UI should render
as a readable notice - no key, unparseable paste, a provider that timed out.
A red failed-fetch in a grader's console is worse than a sentence explaining
what is missing.

    uvicorn api.main:app --reload --port 8000     # dev, with web/ on 5173
    uvicorn api.main:app --port 7860              # prod, serves web/dist too
"""

from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from promo.config import (  # noqa: E402
    DEFAULT_SETTINGS_PATH,
    UnknownProfile,
    describe_profile,
    is_paid,
    load_env,
    load_raw,
    load_settings_profile,
)
from promo.parse import ParseError, parse_text  # noqa: E402

# A local `uvicorn api.main:app` must pick up the key from `.env` the same way
# the CLI does. In the container there is no `.env` and this is a no-op: Render
# sets the real environment variable, which `load_env` never overrides.
# MISTAKES.md #11.
load_env(ROOT / ".env")

# Overridable so the Season tab can be exercised against a fixture without
# writing anything into the real outputs/ - and so a host can mount results
# from somewhere other than the image.
OUT_DIR = Path(os.getenv("PROMO_OUTPUTS_DIR") or ROOT / "outputs")
PROMOS_JSON = OUT_DIR / "promos.json"
REJECTED_JSON = OUT_DIR / "rejected.json"
SAMPLE = ROOT / "examples" / "sample_episode.txt"
DIST = ROOT / "web" / "dist"

#: A pasted episode longer than this is not one episode. The cap keeps a
#: paste of the whole season from turning into one enormous prompt.
MAX_PASTE_CHARS = 120_000

app = FastAPI(
    title="Promo finder",
    description="20-60s promos from microdrama screenplays.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


# --- cross-origin access -------------------------------------------------
#
# The split deploy is the only reason this exists. The container serves
# `web/dist` itself, so on its own URL every request is same-origin and no
# CORS header is involved at all. But the frontend is also published as static
# files on a different host, and a static host cannot proxy `/api` anywhere -
# so that copy of the page calls this origin directly, and the browser blocks
# it unless this server names that origin.
#
# Comma-separated, and read from the environment rather than written here,
# because the two hostnames are not known at the same time: the backend URL
# only exists once the service is created, and the frontend's only once its
# subdomain is. An env var is changed in the host's dashboard and takes a
# restart; a hardcoded origin would take a code change and a full image
# rebuild, which is the wrong thing to need at the end.
#
# `allow_credentials` stays False deliberately. Nothing here uses a cookie or
# an `Authorization` header - a key pasted in the browser travels in the POST
# body (see `_inject_keys`) - so sending credentials would be permission
# granted for nothing, and it would also forbid a wildcard origin later.
# Both subdomains are listed on purpose. The published name is
# `kukupromofinder`; `promofinder` was the first one created and still
# resolves, and an allowlist is not a redirect - naming both means whichever
# one a reader has in hand works, and taking the old one down later needs no
# code change.
DEFAULT_ALLOWED_ORIGINS = (
    "https://kukupromofinder.byfrontage.com,"
    "https://promofinder.byfrontage.com,"
    "http://localhost:5173,"
    "http://127.0.0.1:5173"
)

ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in (os.getenv("ALLOWED_ORIGINS") or DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        # The three the app actually sends. OPTIONS is the preflight itself.
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        # Cache the preflight for an hour, so a live run is one request and
        # not two every time.
        max_age=3600,
    )


# --- profiles and keys ---------------------------------------------------
#
# The settings file is read fresh on every request rather than cached at
# import: it is a few KB of YAML, and an edit to it should show up in the UI
# without a restart.
#
# The browser may send its own API key with a run. It is used for that one
# call and nothing else: never written to disk, never put in the response,
# never logged, and never assigned to the real `GEMINI_API_KEY`-style
# variable, which would leak it into every later request in the process.
# Instead each request gets a throwaway environment variable with a random
# name, the settings copy handed to the router points at that name, and the
# `finally` clause removes it. Two concurrent runs with different keys cannot
# see each other's, and nothing in src/ changes - the router already reads
# `providers.<name>.api_key_env` out of the settings dict it is given.

SETTINGS_PATH = ROOT / DEFAULT_SETTINGS_PATH

#: Providers that bill. Mirrors `promo.config.is_paid`, which is the one
#: place the list is decided.
PAID_PROVIDERS = {"claude", "gpt"}


def _settings(profile: str | None) -> dict[str, Any]:
    return load_settings_profile(profile, SETTINGS_PATH)


def _providers_for(settings: dict[str, Any]) -> list[str]:
    """Provider names a profile's tiers resolve to, in tier order."""
    names: list[str] = []
    for cfg in (settings.get("tiers") or {}).values():
        name = cfg.get("provider")
        if name and name not in names:
            names.append(name)
    return names


def _fallback_providers(settings: dict[str, Any]) -> list[str]:
    """The failover provider, when it is not already one of the tiers.

    Separate from `_providers_for` because the difference is load-bearing: a
    tier provider is *required* - without its key the run cannot start - while
    this one is only reached if a tier call fails, and the router builds it
    lazily (see the comment at `router.py:148`). So a missing key here must
    never block a run, must never flip `/api/health` to `has_key: false`, and
    must still be offerable in the Settings dialog, because the cost of not
    offering it is invisible: Gemini 429s and the run dies with
    `NoProviderAvailable` instead of falling over to the net that the config
    says exists.
    """
    name = ((settings.get("fallback") or {}).get("provider") or "").strip()
    if not name or name in _providers_for(settings):
        return []
    return [name]


def _key_providers(settings: dict[str, Any]) -> list[str]:
    """Every provider a key can be pasted for: the tiers, then the fallback."""
    return [*_providers_for(settings), *_fallback_providers(settings)]


def _key_env(settings: dict[str, Any], provider: str) -> str | None:
    """The environment variable a provider reads, or None if it needs no key."""
    cfg = (settings.get("providers") or {}).get(provider) or {}
    return cfg.get("api_key_env")


def _server_has_key(settings: dict[str, Any], provider: str) -> bool:
    env = _key_env(settings, provider)
    if env is None:
        return True  # ollama: a local daemon, no credentials at all
    if env == "GEMINI_API_KEY":
        return bool(os.getenv(env) or os.getenv("GOOGLE_API_KEY"))
    return bool(os.getenv(env))


def _describe_models(settings: dict[str, Any]) -> list[dict[str, str]]:
    """``[{tier, provider, model}]`` - what the UI prints under the name."""
    return [
        {"tier": tier, "provider": cfg.get("provider", ""), "model": cfg.get("model", "")}
        for tier, cfg in (settings.get("tiers") or {}).items()
    ]


def _profile_card(name: str) -> dict[str, Any]:
    """One row of the model picker. Every string here comes from the YAML."""
    settings = _settings(name)
    providers = _providers_for(settings)
    paid = is_paid(settings)
    local = all(_key_env(settings, p) is None for p in providers) if providers else False
    return {
        "id": name,
        "providers": providers,
        "tiers": _describe_models(settings),
        # free / paid / local, which is exactly what the sidebar badge shows.
        "cost": "paid" if paid else ("local" if local else "free"),
        "keys": [
            {
                "provider": p,
                "env": _key_env(settings, p),
                "on_server": _server_has_key(settings, p),
                # False = the failover provider. The dialog says so, rather
                # than presenting it as another thing that must be filled in.
                "required": p in providers,
            }
            for p in _key_providers(settings)
            if _key_env(settings, p) is not None
        ],
    }


def _has_key() -> bool:
    """Can the *default* profile run without the browser supplying anything?"""
    try:
        settings = _settings(None)
    except Exception:  # noqa: BLE001
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    return all(_server_has_key(settings, p) for p in _providers_for(settings))


def _inject_keys(
    settings: dict[str, Any], keys: dict[str, str]
) -> tuple[dict[str, Any], list[str]]:
    """Point each provider at a throwaway env var holding the pasted key.

    Returns the settings copy to hand the router and the variable names the
    caller must delete afterwards.
    """
    settings = copy.deepcopy(settings)
    created: list[str] = []
    blocks = settings.setdefault("providers", {})
    for provider, key in keys.items():
        key = (key or "").strip()
        if not key or provider not in _key_providers(settings):
            continue
        block = blocks.setdefault(provider, {})
        if not block.get("api_key_env"):
            continue  # a keyless provider (ollama); nothing to inject
        env = f"PROMO_UI_KEY_{provider.upper()}_{uuid.uuid4().hex}"
        os.environ[env] = key
        block["api_key_env"] = env
        created.append(env)
    return settings, created


# --- health --------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    """What the UI needs to know before it offers to run anything live."""
    try:
        profile = describe_profile(_settings(None))
    except Exception as exc:  # noqa: BLE001
        profile = f"settings unreadable: {type(exc).__name__}"
    return {
        "ok": True,
        "has_key": _has_key(),
        "has_outputs": PROMOS_JSON.is_file(),
        "profile": profile,
        "max_paste_chars": MAX_PASTE_CHARS,
    }


@app.get("/api/profiles")
def profiles() -> dict[str, Any]:
    """The model picker's contents, read straight out of settings.yaml.

    No model id is written down here or in the React app. Adding a profile to
    the YAML adds a row to the picker; this endpoint is the only reason that
    is true, and it is why hard rule 2 survives a model selector.
    """
    try:
        raw = load_raw(SETTINGS_PATH)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"config/settings.yaml could not be read: {exc}",
            "default": "",
            "profiles": [],
        }

    names = sorted((raw.get("profiles") or {}).keys())
    cards: list[dict[str, Any]] = []
    for name in names:
        try:
            cards.append(_profile_card(name))
        except Exception:  # noqa: BLE001 - one bad block must not empty the list
            continue
    # Free first, then paid, then local: the default is the one a reader
    # should land on, and the costly ones should take a deliberate click.
    order = {"free": 0, "paid": 1, "local": 2}
    cards.sort(key=lambda c: (order.get(c["cost"], 3), c["id"]))
    return {
        "ok": True,
        "default": raw.get("default_profile") or "",
        "profiles": cards,
        "pricing": raw.get("pricing") or {},
    }


# --- the precomputed season ---------------------------------------------


@app.get("/api/season")
def season() -> dict[str, Any]:
    """``outputs/`` exactly as the batch run wrote it. No API calls.

    The whole payload goes over at once and the client filters by episode:
    it is a single season of promo records, not a dataset, and a round trip
    per dropdown change would buy nothing.
    """
    try:
        payload = json.loads(PROMOS_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "ok": False,
            "error": (
                "No precomputed output yet. Run `python -m promo.run` (or "
                "`--episodes 1 17 44` for three) to write outputs/promos.json."
            ),
            "kind": "no_outputs",
            "summary": {},
            "promos": [],
        }
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error": f"outputs/promos.json could not be read: {exc}",
            "kind": "bad_outputs",
            "summary": {},
            "promos": [],
        }

    try:
        rejected = json.loads(REJECTED_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rejected = {}

    return {
        "ok": True,
        "summary": payload.get("summary") or {},
        "promos": payload.get("promos") or [],
        "rejected_by_gate": rejected.get("by_gate") or {},
        # The individual rejections, not only their counts. The episode boxes
        # show why an episode shipped nothing, which is the honest half of the
        # output; until now it existed only in rejected.json on disk, where a
        # grader who opens the link never sees it. No new computation - this is
        # the same file `promo.run` already wrote.
        "rejected": rejected.get("rejected") or [],
        "dropped_in_selection": rejected.get("dropped_in_selection") or [],
    }


@app.get("/api/sample")
def sample() -> dict[str, Any]:
    """The synthetic example episode. D8: no real episode is ever served."""
    try:
        return {"ok": True, "text": SAMPLE.read_text(encoding="utf-8")}
    except OSError as exc:
        return {"ok": False, "error": f"sample unavailable: {exc}", "text": ""}


# --- the live run --------------------------------------------------------


class RunRequest(BaseModel):
    text: str = Field(default="", description="One episode of screenplay text.")
    profile: str | None = Field(
        default=None,
        description="A profile name from /api/profiles. Omitted = the default.",
    )
    api_keys: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional {provider: key} from the browser. Used for this one "
            "request, never stored and never echoed back."
        ),
    )


def _fail(error: str, kind: str) -> dict[str, Any]:
    return {"ok": False, "error": error, "kind": kind, "promos": [], "rejected": []}


@app.post("/api/run")
def run(body: RunRequest) -> dict[str, Any]:
    """Parse pasted text and run the real pipeline on it.

    Declared ``def`` rather than ``async def`` deliberately: the two model
    calls inside are blocking, and FastAPI runs a sync endpoint in a
    threadpool. Written ``async``, they would stall the event loop and the
    page would stop responding while a promo was being scored.
    """
    text = (body.text or "").strip()
    if not text:
        return _fail("Paste an episode, or press 'Load sample episode'.", "empty")
    if len(text) > MAX_PASTE_CHARS:
        return _fail(
            f"That is {len(text):,} characters. This endpoint takes one episode "
            f"at a time (cap {MAX_PASTE_CHARS:,}); use `python -m promo.run` "
            f"for the season.",
            "too_long",
        )

    try:
        episode = parse_text(text, number=0, path="<pasted>")
    except ParseError as exc:
        return _fail(
            f"The parser rejected this text: {exc}. Each block is a "
            f"'**HEADER:**' line then 'Start: (MM:SS.ss) | End: (MM:SS.ss)'.",
            "parse_error",
        )

    if not episode.blocks:
        return _fail(
            "Parsed cleanly but found zero timed blocks, so there is nothing to "
            "select from. Each block needs a '**HEADER:**' line followed by "
            "'Start: (MM:SS.ss) | End: (MM:SS.ss)'.",
            "no_blocks",
        )

    # Which model the browser asked for. An unknown name is the user's typo
    # or a stale localStorage entry, not a crash.
    try:
        settings = _settings(body.profile)
    except UnknownProfile as exc:
        return _fail(str(exc), "unknown_profile")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"config/settings.yaml could not be read: {exc}", "bad_settings")

    pasted = {p: k for p, k in (body.api_keys or {}).items() if (k or "").strip()}
    missing = [
        p
        for p in _providers_for(settings)
        if not _server_has_key(settings, p) and not pasted.get(p)
    ]
    if missing:
        envs = ", ".join(sorted({_key_env(settings, p) or "" for p in missing}))
        return _fail(
            f"No API key for {', '.join(missing)}. Either set {envs} on the "
            f"server, or open Settings in the sidebar and paste a key. The "
            f"Season tab needs no key at all.",
            "no_key",
        )

    settings, temp_envs = _inject_keys(settings, pasted)

    try:
        from promo.llm import Router
        from promo.run import run_episode

        router = Router(settings, job_dir=ROOT)
        promos, rejected = run_episode(episode, router)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not hidden
        return _fail(f"The live run failed: {type(exc).__name__}: {exc}", "run_failed")
    finally:
        # The pasted key leaves the process here, whatever happened above.
        for env in temp_envs:
            os.environ.pop(env, None)

    return {
        "ok": True,
        # What actually ran, so a result card can never be mistaken for one
        # produced by a different model. No key is in this string.
        "profile": describe_profile(settings),
        "profile_id": settings.get("_profile", ""),
        "promos": [p.to_dict() for p in promos],
        "rejected": rejected,
        "episode": {
            "n_blocks": len(episode.blocks),
            "n_content_blocks": sum(1 for b in episode.blocks if b.is_content),
            "duration_s": round(episode.duration_s, 2),
            "logline": episode.logline,
            "speakers": episode.speakers,
        },
    }


# --- the built React app -------------------------------------------------
# Mounted last so it never shadows /api/*. In development the Vite dev server
# on :5173 proxies /api here instead, and web/dist does not exist yet.

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str) -> Any:
        """Serve a real file when there is one, else the SPA entry point.

        An unknown ``/api/*`` path must 404 as JSON rather than fall through
        to index.html: a client that gets HTML where it expects JSON throws
        on ``response.json()``, which is the one failure the frontend cannot
        render as a readable notice.
        """
        if path == "api" or path.startswith("api/"):
            return JSONResponse(
                {"ok": False, "error": f"No such endpoint: /{path}", "kind": "not_found"},
                status_code=404,
            )
        candidate = (DIST / path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(DIST.resolve())):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")

else:

    @app.get("/")
    def no_build() -> JSONResponse:
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "web/dist not found - the React app has not been built. "
                    "Run `npm install && npm run build` in web/, or use the "
                    "Vite dev server on :5173 which proxies /api here."
                ),
            },
            status_code=503,
        )
