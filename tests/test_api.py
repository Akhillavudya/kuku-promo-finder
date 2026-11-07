"""The HTTP contract, with no server, no key and no network.

FastAPI's TestClient drives the app in-process, so this runs anywhere
`api/requirements.txt` is installed. It needs no `pack/` - the live-run paths
are exercised with the synthetic sample episode and stop at the missing key,
which is the behaviour that matters: **a visitor without a key must get a
sentence, never a stack trace.**

What is worth asserting about this layer, given it is deliberately thin:

* `/api/season` answers with `ok: false` and an explanation when `outputs/`
  is empty, rather than 404 or an empty page
* the same endpoint serves a real payload when output exists, in the order
  the pipeline ranked it
* `POST /api/run` refuses empty, oversized and unparseable input *before*
  reaching for a model, each with its own `kind`
* `/api/*` is never shadowed by the SPA catch-all, and the catch-all cannot
  be walked out of the dist directory

    python -m pytest tests/test_api.py -q
    python tests/test_api.py
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from test_demo_path import PROMO, SUMMARY  # noqa: E402


def _client(outputs_dir: Path | None = None) -> TestClient:
    """A fresh app, optionally pointed at a fixture outputs directory.

    `api.main` reads PROMO_OUTPUTS_DIR at import time, so the module is
    reloaded rather than mutated - that keeps the test honest about what the
    deployed process actually does on startup.
    """
    import os

    if outputs_dir is None:
        os.environ.pop("PROMO_OUTPUTS_DIR", None)
    else:
        os.environ["PROMO_OUTPUTS_DIR"] = str(outputs_dir)

    import api.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_health_reports_what_the_ui_needs() -> None:
    body = _client().get("/api/health").json()
    assert body["ok"] is True
    assert isinstance(body["has_key"], bool)
    assert isinstance(body["has_outputs"], bool)
    assert body["max_paste_chars"] > 0
    # The profile string must name the tier, never leak a key.
    assert "candidates=" in body["profile"] or "unreadable" in body["profile"]


def test_season_explains_itself_when_there_is_no_output() -> None:
    with tempfile.TemporaryDirectory() as empty:
        response = _client(Path(empty)).get("/api/season")
    assert response.status_code == 200, "an empty outputs/ is not an HTTP error"
    body = response.json()
    assert body["ok"] is False
    assert body["kind"] == "no_outputs"
    assert "promo.run" in body["error"], "the error must say how to fix it"
    assert body["promos"] == []


def test_season_serves_output_in_ranked_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        promos = [
            dict(PROMO, id="a", episode=17, weighted_score=8.9),
            dict(PROMO, id="b", episode=3, weighted_score=7.4),
            dict(PROMO, id="c", episode=17, weighted_score=6.2),
        ]
        (out / "promos.json").write_text(
            json.dumps({"summary": SUMMARY, "promos": promos}), encoding="utf-8"
        )
        (out / "rejected.json").write_text(
            json.dumps({"by_gate": {"no_hook_in_3s": 41}}), encoding="utf-8"
        )
        body = _client(out).get("/api/season").json()

    assert body["ok"] is True
    assert [p["id"] for p in body["promos"]] == ["a", "b", "c"], "order is the ranking"
    assert body["summary"]["n_promos"] == 61
    assert body["rejected_by_gate"] == {"no_hook_in_3s": 41}
    # The field the timeline is scaled by must survive the round trip.
    assert body["promos"][0]["episode_duration_s"] == PROMO["episode_duration_s"]


def test_sample_is_served_and_is_the_synthetic_one() -> None:
    body = _client().get("/api/sample").json()
    assert body["ok"] is True
    assert "EPISODE NUMBER: 99" in body["text"], "episode 99 is the synthetic stand-in"
    assert "Start: (" in body["text"]


def _run(client: TestClient, text: str) -> dict[str, Any]:
    return client.post("/api/run", json={"text": text}).json()


def test_run_refuses_bad_input_before_calling_a_model() -> None:
    client = _client()

    empty = _run(client, "   ")
    assert empty["ok"] is False and empty["kind"] == "empty"

    oversized = _run(client, "x" * 130_000)
    assert oversized["ok"] is False and oversized["kind"] == "too_long"
    assert "130,000" in oversized["error"], "say the measured size"

    prose = _run(client, "just prose, nothing timed in here at all")
    assert prose["ok"] is False and prose["kind"] == "no_blocks"

    # Every failure keeps the shape the UI renders, so there is one code path.
    for body in (empty, oversized, prose):
        assert body["promos"] == [] and body["rejected"] == []


def test_run_on_the_sample_stops_at_the_missing_key() -> None:
    """Without a key this must be a sentence, not an exception.

    **Order matters here, and it did not used to.** `api.main` now calls
    `load_env()` at import so that a local `uvicorn` picks up `.env` the way
    the CLI does (MISTAKES.md #11). So the client must be built - and the
    import done - *before* the keys are cleared, or importing it reads `.env`
    straight back in and this test silently exercises a successful run
    instead of the missing-key path. That is exactly how this test failed
    when `load_env` was added: it asserted `ok is False` and got a real
    two-promo result.
    """
    import os

    client = _client()
    sample = client.get("/api/sample").json()["text"]

    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        os.environ.pop(name, None)
    body = _run(client, sample)

    assert body["ok"] is False
    assert body["kind"] == "no_key", (
        "the sample must parse and gate cleanly, failing only for want of a key"
    )
    assert "GEMINI_API_KEY" in body["error"]


def test_api_is_not_shadowed_by_the_spa_catch_all() -> None:
    client = _client()
    # /api/* still answers JSON even though a catch-all route exists.
    assert client.get("/api/health").json()["ok"] is True
    # An unknown /api path is a 404, not the React shell.
    assert client.get("/api/nope").status_code == 404


def test_spa_catch_all_cannot_escape_dist() -> None:
    """Only relevant once web/dist exists; skipped cleanly when it does not."""
    if not (ROOT / "web" / "dist" / "index.html").is_file():
        print("    (web/dist not built - traversal check skipped)")
        return

    client = _client()
    settings = (ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    for attempt in ("../config/settings.yaml", "..%2fconfig%2fsettings.yaml"):
        response = client.get(f"/{attempt}")
        assert response.status_code == 200
        assert "tiers" not in response.text, f"served a file outside dist: {attempt}"
        assert settings[:40] not in response.text


TESTS = [
    test_health_reports_what_the_ui_needs,
    test_season_explains_itself_when_there_is_no_output,
    test_season_serves_output_in_ranked_order,
    test_sample_is_served_and_is_the_synthetic_one,
    test_run_refuses_bad_input_before_calling_a_model,
    test_run_on_the_sample_stops_at_the_missing_key,
    test_api_is_not_shadowed_by_the_spa_catch_all,
    test_spa_catch_all_cannot_escape_dist,
]


def main() -> int:
    for test in TESTS:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(TESTS)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
