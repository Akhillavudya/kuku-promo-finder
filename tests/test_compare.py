"""The eval comparison, exercised before there are any real labels.

`promo.compare` is the module that answers the brief's "where does your tool
pick badly". It reads `eval/labels.json`, which is a **human** artefact that
does not exist yet - so until this file was written the module had never
executed once, and the first thing to run it would have been a reviewer, or
the author at 2am with an hour of hand-labelling already spent.

That is the whole point of this suite: **prove the report renders before the
labels are written, not after.** The fixtures below are synthetic and are
deliberately shaped so that every branch of `compare()` fires at least once -
an agreeing pick, a disagreeing pick, a declined episode, an unlabelled
episode, and a pick that lands on something the human explicitly rejected.

    python tests/test_compare.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from promo import compare as cmp  # noqa: E402


def _promo(pid: str, episode: int, spans: list[tuple[float, float]],
           score: float = 8.0) -> dict[str, Any]:
    """A minimal output record: what compare.py actually reads off a promo."""
    return {
        "id": pid,
        "episode": episode,
        "weighted_score": score,
        "scores": {"hook_strength": 8, "cliffhanger": 8, "standalone": 8,
                   "emotional_charge": 8},
        "duration_s": round(sum(e - s for s, e in spans), 2),
        "segments": [
            {"start_block": int(s), "end_block": int(e),
             "start_s": s, "end_s": e, "duration_s": round(e - s, 2)}
            for s, e in spans
        ],
    }


def _labels(**over: Any) -> dict[str, Any]:
    base = {
        "labelled_by": "test",
        "labelled_at": "2026-11-07",
        "tool_had_been_run": False,
        "labels": [
            # 1: the tool agrees - same start, same end, inside tolerance.
            {"episode": 1, "segments": [{"start_s": 10.0, "end_s": 40.0}],
             "rejected": []},
            # 2: the tool starts 9s late and ends 9s late - disagrees on both.
            {"episode": 2, "segments": [{"start_s": 10.0, "end_s": 40.0}],
             "rejected": []},
            # 3: the tool produced nothing for this episode.
            {"episode": 3, "segments": [{"start_s": 5.0, "end_s": 35.0}],
             "rejected": []},
            # 4: no segments recorded - the label itself is unusable.
            {"episode": 4, "segments": [], "rejected": []},
            # 5: the tool picked the span the human consciously rejected.
            {"episode": 5, "segments": [{"start_s": 0.0, "end_s": 30.0}],
             "rejected": [{"what": "the argument in the kitchen",
                           "why_not": "resolves on screen",
                           "segments": [{"start_s": 60.0, "end_s": 95.0}]}]},
        ],
    }
    base.update(over)
    return base


PROMOS = [
    _promo("ep001-c1", 1, [(10.5, 39.0)], score=9.0),
    _promo("ep002-c1", 2, [(19.0, 49.0)], score=8.5),
    # nothing for episode 3 - the tool declined
    _promo("ep004-c1", 4, [(0.0, 30.0)], score=7.0),
    # episode 5: the top pick is fine, but a lower pick hits the rejected span
    _promo("ep005-c1", 5, [(1.0, 29.0)], score=8.0),
    _promo("ep005-c2", 5, [(61.0, 94.0)], score=6.5),
]


def test_iou_is_symmetric_and_bounded() -> None:
    a, b = [(0.0, 10.0)], [(5.0, 15.0)]
    assert cmp.iou(a, b) == cmp.iou(b, a)
    assert abs(cmp.iou(a, b) - 1 / 3) < 1e-9, cmp.iou(a, b)
    assert cmp.iou(a, a) == 1.0
    assert cmp.iou(a, [(20.0, 30.0)]) == 0.0
    assert cmp.iou([], b) == 0.0, "an empty span must not divide by zero"
    print("ok  test_iou_is_symmetric_and_bounded")


def test_the_report_renders_on_every_branch() -> None:
    """The real reason this file exists: run all four measures end to end."""
    report = cmp.compare(_labels(), PROMOS, tolerance_s=2.0)
    s = report["summary"]
    by_ep = {e["episode"]: e for e in report["episodes"]}

    assert s["labelled_episodes"] == 5
    # Episodes 3 (declined) and 4 (no label segments) are not comparable.
    assert s["comparable_episodes"] == 3, s
    assert s["tool_declined_on"] == [3], s

    # 1 agrees on both ends; 2 is 9s out on both; 5 agrees within 1s.
    assert by_ep[1]["hook_agreement"] is True
    assert by_ep[1]["cliffhanger_agreement"] is True
    assert by_ep[2]["hook_agreement"] is False, by_ep[2]
    assert by_ep[2]["cliffhanger_agreement"] is False, by_ep[2]
    assert by_ep[5]["hook_agreement"] is True
    assert s["hook_agreement"] == "2/3", s["hook_agreement"]
    assert s["cliffhanger_agreement"] == "2/3", s["cliffhanger_agreement"]

    # Sign convention stated in the rendered report must hold: positive means
    # the tool starts later than the human.
    assert by_ep[2]["hook_delta_s"] == 9.0, by_ep[2]

    # Episode 3 declined, so it is reported, not silently dropped.
    assert by_ep[3]["tool_declined"] is True
    assert by_ep[3]["overlap"] is None
    assert "no promo" in by_ep[3]["note"]
    # Episode 4's label is unusable and says so rather than scoring 0.
    assert by_ep[4]["overlap"] is None
    assert "no segments" in by_ep[4]["note"]

    # The fourth measure, which is the one that teaches you something.
    assert s["rejected_candidate_hits"] == 1, s
    assert by_ep[5]["rejected_candidate_hits"] == [
        "ep005-c2: the argument in the kitchen"
    ], by_ep[5]

    text = cmp.render(report)
    assert "# Tool vs hand labels" in text
    assert "Hook agreement:** 2/3" in text
    assert "Picked something the human rejected" in text
    assert "the argument in the kitchen" in text
    assert "ep3" in text, "a declined episode must be named in the report"
    # Every labelled episode gets a row, including the two incomparable ones.
    assert text.count("\n| ") >= 5, text

    print("ok  test_the_report_renders_on_every_branch")


def test_comparison_is_against_the_top_pick_not_the_best_match() -> None:
    """An editor reads the ranking from the top, so the eval must too.

    Scoring against whichever pick happened to match the human would flatter
    the tool: with two candidates per episode it could be wrong about which
    is better and still score 100% agreement.
    """
    labels = {
        "tool_had_been_run": False,
        "labels": [{"episode": 7, "segments": [{"start_s": 80.0, "end_s": 110.0}],
                    "rejected": []}],
    }
    promos = [
        _promo("ep007-c1", 7, [(0.0, 30.0)], score=9.0),    # top, disagrees
        _promo("ep007-c2", 7, [(80.0, 110.0)], score=6.5),  # exact, ranked 2nd
    ]
    report = cmp.compare(labels, promos, tolerance_s=2.0)
    ep = report["episodes"][0]
    assert ep["hook_agreement"] is False, (
        "compared against the matching pick instead of the top-ranked one, "
        "which would make the eval unable to detect a bad ranking"
    )
    assert ep["overlap"] == 0.0
    print("ok  test_comparison_is_against_the_top_pick_not_the_best_match")


def test_labels_written_after_the_run_are_refused() -> None:
    """D7's ordering rule, enforced in code rather than in a README."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "labels.json"
        path.write_text(json.dumps(_labels(tool_had_been_run=True)),
                        encoding="utf-8")
        try:
            cmp.load_labels(path)
        except cmp.LabelOrderError as exc:
            assert "rationalisation" in str(exc)
        else:
            raise AssertionError("labels written after the run were accepted")

        # And a missing file must say what to do about it, not just ENOENT.
        try:
            cmp.load_labels(Path(tmp) / "nope.json")
        except FileNotFoundError as exc:
            assert "labels.template.json" in str(exc), str(exc)
        else:
            raise AssertionError("a missing labels file was accepted")
    print("ok  test_labels_written_after_the_run_are_refused")


def test_the_template_can_express_every_measure_the_readme_promises() -> None:
    """The template is a contract with the human who fills it in.

    `eval/README.md` lists **rejected-candidate hits** as one of four measures,
    and `compare.py` computes it from `rejected[].segments`. If the template
    has no `segments` key under `rejected`, that measure is silently dead: the
    labeller records prose, `_spans` returns nothing, the loop never fires and
    the report prints 0 hits forever - which reads as "the tool never picked a
    rejected span" when it actually means "this was never checked".

    Found by writing this suite, which is the argument for having written it.
    """
    template = json.loads(
        (ROOT / "eval" / "labels.template.json").read_text(encoding="utf-8")
    )
    entry = template["labels"][0]
    assert entry["rejected"], "the template must prompt for rejected spans"
    rejected = entry["rejected"][0]
    assert "segments" in rejected, (
        "labels.template.json has no `segments` under `rejected`, so the "
        "rejected-candidate-hits measure can never fire - eval/README.md "
        "promises it as one of the four measures"
    )
    for key in ("start_s", "end_s"):
        assert key in rejected["segments"][0], (
            f"rejected segments need {key}; compare._spans reads start_s/end_s"
        )
    print("ok  test_the_template_can_express_every_measure_the_readme_promises")


TESTS = [
    test_iou_is_symmetric_and_bounded,
    test_the_report_renders_on_every_branch,
    test_comparison_is_against_the_top_pick_not_the_best_match,
    test_labels_written_after_the_run_are_refused,
    test_the_template_can_express_every_measure_the_readme_promises,
]


def main() -> int:
    for test in TESTS:
        test()
    print(f"\n{len(TESTS)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
