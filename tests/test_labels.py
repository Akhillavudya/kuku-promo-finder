"""The eval-set label resolver: block indices in, seconds out, problems named.

The point of these tests is the failure that `promo/labels.py` exists to stop:
a label written in block indices resolving to an empty span, `compare.py`
skipping the episode, and the report printing a clean-looking nothing. That is
the same defect as D24 one layer up, so it gets a test that fails loudly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from promo import compare as compare_mod
from promo import labels as labels_mod
from promo.gates import Gates
from promo.parse import parse_text

#: A synthetic episode in the pack's measured format (`notes/FORMAT.md`).
#: Block indices, and what each one is for:
#:
#:   0  CAMERA    0.00-3.00    not content - cannot open a promo or end one
#:   1  ACTION    0.00-3.00    the hook beat
#:   2  DIALOGUE  3.00-8.00
#:   3  ACTION    8.00-14.00   end here and the span is 14.0s -> too_short
#:   4  DIALOGUE 14.00-22.00
#:   5  ACTION   22.00-30.00   end here and the span is 30.0s -> legal
#:   6  CAMERA   30.00-33.00   must never set the span's end (D22)
EPISODE = """\
EPISODE NUMBER: 7
EPISODE LOGLINE: A test fixture.
CONTINUITY NOTES: Synthetic. No episode of the real pack is reproduced here.

SCENE 1
Scene heading: INT. A ROOM - NIGHT

**CAMERA:**
Start: (00:00.00) | End: (00:03.00)
Wide on the room.

**ACTION:**
Start: (00:00.00) | End: (00:03.00)
She slaps him.

**NADIA (Cold):**
Start: (00:03.00) | End: (00:08.00)
"You knew."

**ACTION:**
Start: (00:08.00) | End: (00:14.00)
He steps back into the doorway.

**NADIA (Quiet):**
Start: (00:14.00) | End: (00:22.00)
"I did."

**ACTION:**
Start: (00:22.00) | End: (00:30.00)
The door opens behind them both.

**CAMERA:**
Start: (00:30.00) | End: (00:33.00)
Hold on the doorway.
"""


@pytest.fixture
def episodes():
    return {7: parse_text(EPISODE, number=7)}


def _label(**overrides):
    label = {
        "episode": 7,
        "in_one_sentence": "She slaps him and someone walks in.",
        "segments": [{"start_block": 1, "end_block": 5}],
        "hook": "the slap",
        "cliffhanger": "who is in the doorway",
        "why": "a stranger wants to know who walked in",
        "rejected": [],
        "confidence": "high",
    }
    label.update(overrides)
    return {"tool_had_been_run": False, "labels": [label]}


def test_block_indices_resolve_to_seconds(episodes):
    """The whole contract: indices in, seconds out, no hand arithmetic."""
    labels = _label()
    problems = labels_mod.resolve(labels, episodes)

    assert not [p for p in problems if p.fatal]
    segment = labels["labels"][0]["segments"][0]
    assert segment["start_s"] == 0.0
    assert segment["end_s"] == 30.0
    assert labels["labels"][0]["duration_s"] == 30.0


def test_resolution_goes_through_the_block_table_not_the_written_seconds(episodes):
    """Hard rule 1: a hand-typed second loses to the block table, and says so."""
    labels = _label(segments=[{"start_block": 1, "end_block": 5,
                              "start_s": 0.0, "end_s": 99.0}])
    problems = labels_mod.resolve(labels, episodes)

    assert labels["labels"][0]["segments"][0]["end_s"] == 30.0
    assert any("the block table wins" in p.message for p in problems)


def test_an_empty_segment_is_fatal_not_silent(episodes):
    """The defect this module exists to prevent."""
    labels = _label(segments=[{"start_block": None, "end_block": None}])
    problems = labels_mod.resolve(labels, episodes)

    fatal = [p for p in problems if p.fatal]
    assert fatal, "an unfillable label must be an error, not a skipped episode"
    assert any("compare.py will skip this episode" in p.message for p in fatal)


def test_out_of_range_and_inverted_blocks_are_caught(episodes):
    for segments in ([{"start_block": 1, "end_block": 999}],
                     [{"start_block": 5, "end_block": 2}]):
        problems = labels_mod.resolve(_label(segments=segments), episodes)
        assert [p for p in problems if p.fatal]


def test_rejected_spans_resolve_too(episodes):
    """D24's defect must not come back through the other door."""
    labels = _label(
        rejected=[{"what": "the quiet half", "why_not": "no hook",
                   "segments": [{"start_block": 3, "end_block": 5}]}]
    )
    labels_mod.resolve(labels, episodes)

    rejected = labels["labels"][0]["rejected"][0]["segments"][0]
    assert rejected["start_s"] == 8.0
    assert rejected["end_s"] == 30.0


def test_gate_check_warns_when_the_human_pick_is_unmatchable(episodes):
    """A 14s human pick can never be matched by a tool floored at 20s."""
    labels = _label(segments=[{"start_block": 1, "end_block": 3}])
    labels_mod.resolve(labels, episodes)
    problems = labels_mod.check_against_gates(labels, episodes, Gates())

    assert any("too_short" in p.where for p in problems)
    assert all(not p.fatal for p in problems), "a human label is ground truth"


def test_gate_check_confirms_a_legal_pick(episodes):
    labels = _label()
    labels_mod.resolve(labels, episodes)
    problems = labels_mod.check_against_gates(labels, episodes, Gates())

    assert any("legal" in p.message for p in problems)


def test_blanks_flags_template_text_left_in_place(episodes):
    labels = _label(hook="the line or beat that lands in the first 3 seconds",
                    confidence="")
    problems = labels_mod.blanks(labels)

    assert any("template's instruction text" in p.message for p in problems)
    assert any(p.where == "confidence" for p in problems)


def test_compare_refuses_index_only_labels_it_cannot_resolve(tmp_path, monkeypatch):
    """End to end: the CLI must exit non-zero rather than measure nothing."""
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(
        json.dumps(_label(segments=[{"start_block": None, "end_block": None}])),
        encoding="utf-8",
    )
    promos_path = tmp_path / "promos.json"
    promos_path.write_text(json.dumps({"promos": []}), encoding="utf-8")

    monkeypatch.setattr(compare_mod, "load_season", lambda _pack: [parse_text(EPISODE, number=7)])

    code = compare_mod.main(
        ["--labels", str(labels_path), "--promos", str(promos_path),
         "--out", str(tmp_path / "report.md")]
    )
    assert code == 2


def test_compare_accepts_labels_written_only_in_block_indices(tmp_path, monkeypatch):
    """The case that silently scored nothing before this wiring existed."""
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(_label()), encoding="utf-8")
    promos_path = tmp_path / "promos.json"
    promos_path.write_text(
        json.dumps({"promos": [{
            "id": "ep007-c1", "episode": 7, "score": 7.0,
            "scores": {"hook_strength": 7, "cliffhanger": 7,
                       "standalone": 7, "emotional_charge": 7},
            "duration_s": 30.0,
            "segments": [{"start_block": 1, "end_block": 5,
                          "start_s": 0.0, "end_s": 30.0}],
        }]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(compare_mod, "load_season", lambda _pack: [parse_text(EPISODE, number=7)])

    out = tmp_path / "report.md"
    code = compare_mod.main(
        ["--labels", str(labels_path), "--promos", str(promos_path), "--out", str(out)]
    )
    assert code == 0

    report = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["summary"]["comparable_episodes"] == 1
    assert report["summary"]["mean_overlap"] == 1.0
    assert report["summary"]["hook_agreement"] == "1/1"
