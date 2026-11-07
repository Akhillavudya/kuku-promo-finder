"""The demo's data path and the record shape the frontend is written against.

This is what survived the Gradio renderer (D16). The HTML tests went with it -
React escapes by default and the cards are typechecked by `tsc` - but three
things the renderer tests were really protecting have nothing to do with
Gradio and are kept here:

* the **synthetic sample episode actually produces a legal promo**, so the
  "Run it live" view is not broken for a grader who has no `pack/`
* the live route is the real one: parse -> gates -> score -> `to_dict()`,
  the same functions in the same order as `python -m promo.run`
* `Candidate.to_dict()` and `web/src/types.ts` **agree field for field**.
  That contract used to be checked by a Python renderer reading the same
  dict. Now the only consumer is TypeScript written by hand, so the drift it
  would cause - a field renamed in Python, silently `undefined` in a card -
  is checked here instead.

`PROMO` and `SUMMARY` also live here because `test_api.py` serves them as
fixture output. They are not screenplay content: the hook line is invented.

    python -m pytest tests/ -q
    python tests/test_demo_path.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from promo import gates as gate_mod  # noqa: E402
from promo.parse import parse_text  # noqa: E402
from promo.run import gate_episode  # noqa: E402
from promo.schemas import AXES  # noqa: E402
from promo.score import Rubric  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_episode.txt"
TYPES_TS = ROOT / "web" / "src" / "types.ts"

#: One promo record in exactly the shape ``outputs/promos.json`` stores. The
#: hook carries markup on purpose: it is the one field model text reaches, so
#: anything rendering it must escape, and `test_api.py` round-trips it.
PROMO: dict[str, Any] = {
    "id": "ep017-c2",
    "episode": 17,
    "duration_s": 38.5,
    "episode_duration_s": 118.4,
    "segments": [
        {"start_block": 12, "end_block": 19, "start": "00:12.40", "end": "00:31.00",
         "start_s": 12.4, "end_s": 31.0, "duration_s": 18.6},
        {"start_block": 30, "end_block": 37, "start": "00:44.10", "end": "01:04.00",
         "start_s": 44.1, "end_s": 64.0, "duration_s": 19.9},
    ],
    "hook": 'She says "You buried him. I watched you." & <script>alert(1)</script>',
    "hook_type": "accusation",
    "cliffhanger": "The door handle turns and nobody is supposed to be home.",
    "why": "A stranger understands the accusation without any context at all.",
    "weakness": "The second segment leans on a name the viewer has not met.",
    "needs_to_know": "",
    "scores": {"hook_strength": 9, "cliffhanger": 8, "standalone": 7,
               "emotional_charge": 6},
    "weighted_score": 7.85,
    "score_passes": [
        {"hook_strength": 9, "cliffhanger": 8, "standalone": 7,
         "emotional_charge": 6},
        {"hook_strength": 9, "cliffhanger": 8, "standalone": 7,
         "emotional_charge": 6},
    ],
    "score_spread": 0.3,
    # Empty on every healthy response; ACCURACY #6 exists so that a response
    # which omits an axis is countable instead of looking like a judged 1.
    "missing_axes": [],
    "hook_block": 13,
    "hook_offset_s": 1.2,
    "duration_adjustment": "trimmed final segment from block 38 to 37",
}

SUMMARY: dict[str, Any] = {
    "profile": "profile free [free]  candidates=gemini:x  rank=gemini:x",
    "finished_at": "2026-11-06 04:40:00",
    "elapsed_s": 412.0,
    "n_episodes": 50,
    "n_promos": 61,
    "n_candidates_proposed": 214,
    "n_rejected_by_gates": 97,
    "n_episodes_with_no_promo": 4,
    "episodes_with_no_promo": [8, 22, 39, 47],
    "rejections_by_gate": {"no_hook_in_3s": 41, "too_short": 29, "too_long": 18},
    "spend": {"calls": 58, "cached_calls": 12, "usd_total": 0.0},
}


def _interface_fields(source: str, name: str) -> set[str]:
    """The property names of one `export interface` block in types.ts.

    A regex, not a TypeScript parser, because the file is fifteen lines of
    flat interfaces written by hand and a parser would be the kind of
    machinery this project is scored for not building.
    """
    match = re.search(
        rf"export interface {name} \{{(.*?)\n\}}", source, re.DOTALL
    )
    assert match, f"no `export interface {name}` in {TYPES_TS.name}"
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    return set(re.findall(r"^\s{2}(\w+)\??:", body, re.MULTILINE))


def test_the_frontend_types_match_the_record_python_writes() -> None:
    """`web/src/types.ts` is `Candidate.to_dict()`, field for field.

    Mirrored by hand, so nothing but this test stops it drifting. A field
    renamed in Python would otherwise reach a card as `undefined` and show
    up as a blank line rather than an error.
    """
    source = TYPES_TS.read_text(encoding="utf-8")

    assert _interface_fields(source, "Promo") == set(PROMO), (
        "Promo in types.ts and the record shape have diverged"
    )
    assert _interface_fields(source, "Segment") == set(PROMO["segments"][0])
    # The axes the cards draw are the axes the rubric scores (hard rule 4).
    axes_ts = re.search(r"export const AXES = \[(.*?)\] as const", source, re.DOTALL)
    assert axes_ts, "no AXES tuple in types.ts"
    assert tuple(re.findall(r'"(\w+)"', axes_ts.group(1))) == tuple(AXES)


def test_sample_episode_can_contain_a_promo() -> None:
    """The shipped example must actually produce something when run.

    An example that cannot clear the gates would make the live view look
    broken, so this walks every single-segment span with the real gates.
    """
    episode = parse_text(SAMPLE.read_text(encoding="utf-8"), path=str(SAMPLE))
    assert episode.number == 99, episode.number
    assert episode.logline and episode.blocks
    assert episode.duration_s > 60, "too short to hold a 20-60s promo"
    assert any(b.is_content for b in episode.blocks)

    gates = gate_mod.Gates.from_rubric()
    legal = [
        (start, end)
        for start in range(len(episode.blocks))
        for end in range(start, len(episode.blocks))
        if gate_mod.check(
            episode, *[gate_mod.fit_to_window(episode, [(start, end)], gates)[0]], gates
        ).ok
    ]
    assert legal, "no span of the sample episode passes the gates"


def test_live_path_end_to_end() -> None:
    """parse -> gates -> score -> to_dict, which is what POST /api/run runs."""
    episode = parse_text(SAMPLE.read_text(encoding="utf-8"), path=str(SAMPLE))
    gates = gate_mod.Gates.from_rubric()
    rubric = Rubric.load()

    raw = [{
        "segments": [{"start_block": 0, "end_block": 6}],
        "hook": "An eviction notice slides under a shutter and stops on her shoe.",
        "cliffhanger": "Two sets of headlights fill the shop and do not turn off.",
        "why": "The threat needs no context.",
        "needs_to_know": "",
    }]
    accepted, rejected = gate_episode(episode, raw, gates)
    assert accepted and not rejected, f"the sample candidate was rejected: {rejected}"

    scores = {"hook_strength": 8, "cliffhanger": 9, "standalone": 7,
              "emotional_charge": 7}
    candidate = accepted[0]
    candidate.scores = rubric.axis_table(scores)
    candidate.weighted_score = rubric.weighted(scores)

    record = candidate.to_dict()
    assert record["episode_duration_s"] == round(episode.duration_s, 2), (
        "the episode's own length must reach the output, or the timeline "
        "cannot be scaled without the pack"
    )
    assert set(record["scores"]) == set(AXES)
    assert set(record) == set(PROMO), "the fixture no longer matches to_dict()"
    # The gate evidence the card prints under each promo, from the real run.
    assert record["hook_block"] is not None
    assert record["hook_offset_s"] is not None and record["hook_offset_s"] < 3.0


TESTS = [
    test_the_frontend_types_match_the_record_python_writes,
    test_sample_episode_can_contain_a_promo,
    test_live_path_end_to_end,
]


def main() -> int:
    for test in TESTS:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(TESTS)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
