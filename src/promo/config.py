"""Profile resolution: the whole of the "swap the model" feature.

D13. The router already accepts a settings *dict* as well as a path, so a
profile needs no change to the borrowed code at all: load the YAML, copy the
chosen profile over the ``tiers`` key, hand the dict to ``Router``. The
router, the pipeline and the prompts never learn that profiles exist, and
hard rule 2 is untouched - pipeline code still asks for the tier
``"candidates"`` and has no idea which company answers.

    settings = load_settings_profile("claude")
    router = Router(settings, job_dir=Path("."))
    router.complete("candidates", prompt, json_schema=SCHEMA)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SETTINGS_PATH = Path("config/settings.yaml")

DEFAULT_ENV_PATH = Path(".env")


class UnknownProfile(KeyError):
    """A profile name that is not in settings.yaml."""


def load_env(path: Path | str = DEFAULT_ENV_PATH) -> list[str]:
    """Load ``KEY=value`` lines from ``.env`` into the environment.

    Returns the names it set, for logging. Missing file is not an error:
    production sets real environment variables and has no ``.env`` at all.

    **Why this exists** (`notes/MISTAKES.md` #11). ``.env``, ``.env.example``
    and a ``START_HERE.md`` build step all described this behaviour and
    nothing implemented it; every run that worked did so because the variable
    happened to be exported in that shell. A fresh clone - which is the path
    a reviewer takes - failed with ``GEMINI_API_KEY is not set``.

    **Why it is hand-rolled rather than ``python-dotenv``.** Twelve lines
    against a dependency, for parsing that is `split("=", 1)`. Nothing here
    needs interpolation, multi-line values or export syntax.

    A real environment variable always wins, so ``.env`` cannot silently
    override what a container or a CI runner set deliberately.
    """
    path = Path(path)
    if not path.is_file():
        return []
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")
        loaded.append(key)
    return loaded


def load_raw(path: Path | str = DEFAULT_SETTINGS_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"settings file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def available_profiles(path: Path | str = DEFAULT_SETTINGS_PATH) -> list[str]:
    return sorted((load_raw(path).get("profiles") or {}).keys())


def load_settings_profile(
    profile: str | None = None,
    path: Path | str = DEFAULT_SETTINGS_PATH,
) -> dict[str, Any]:
    """Return a settings dict with ``tiers`` set from the chosen profile."""
    settings = load_raw(path)
    profiles = settings.get("profiles") or {}

    name = profile or settings.get("default_profile")
    if not name:
        return settings  # no profiles configured; use `tiers` as written

    if name not in profiles:
        raise UnknownProfile(
            f"unknown profile {name!r}; settings.yaml defines {sorted(profiles)}"
        )

    settings["tiers"] = profiles[name]
    settings["_profile"] = name
    return settings


def describe_profile(settings: dict[str, Any]) -> str:
    """One line naming what is actually about to run. Printed on every run."""
    tiers = settings.get("tiers") or {}
    parts = [
        f"{tier}={cfg.get('provider')}:{cfg.get('model')}" for tier, cfg in tiers.items()
    ]
    paid = {"claude", "gpt"} & {cfg.get("provider") for cfg in tiers.values()}
    tag = "PAID" if paid else "free"
    return f"profile {settings.get('_profile', '?')} [{tag}]  " + "  ".join(parts)


def is_paid(settings: dict[str, Any]) -> bool:
    """True when any tier resolves to a billed provider."""
    tiers = settings.get("tiers") or {}
    return bool({"claude", "gpt"} & {cfg.get("provider") for cfg in tiers.values()})


__all__ = [
    "DEFAULT_SETTINGS_PATH",
    "UnknownProfile",
    "available_profiles",
    "describe_profile",
    "is_paid",
    "load_raw",
    "load_settings_profile",
]
