"""End-to-end pipeline test with no network, no API key and no quota.

The router already takes injected providers, so the whole pipeline can be
exercised against a scripted backend. This checks the plumbing - indices to
timestamps, gates, scoring, dedup, ordering, output files - without making a
single call.

It is explicitly **not** an evaluation of pick quality. That is `compare.py`
against `eval/labels.json`, and per D7 the labels must be written before the
tool is ever run for real.

    python -m pytest tests/ -q        # if pytest is installed
    python tests/test_pipeline_offline.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from promo import gates as gate_mod  # noqa: E402
from promo.config import load_settings_profile  # noqa: E402
from promo.llm import Router  # noqa: E402
from promo.llm.base import LLMResponse  # noqa: E402
from promo.parse import Episode, find_episode, parse_episode  # noqa: E402
from promo import run as run_mod  # noqa: E402
from promo.run import run  # noqa: E402
from promo.schemas import AXES  # noqa: E402

EPISODES = [1, 17, 44]


class ScriptedProvider:
    """Stands in for Gemini. Returns schema-valid answers, deterministically."""

    name = "scripted"

    def __init__(self, episodes: dict[int, Episode]) -> None:
        self.episodes = episodes
        self.calls: list[str] = []

    def complete(self, prompt: str, *, json_schema: dict[str, Any], **kw: Any) -> LLMResponse:
        is_candidates = "candidates" in json_schema.get("properties", {})
        self.calls.append("candidates" if is_candidates else "rank")
        data = self._candidates(prompt) if is_candidates else self._scores(prompt)
        return LLMResponse(
            data=data,
            text=json.dumps(data),
            provider=self.name,
            model=kw.get("model", "scripted"),
            tokens_in=1000,
            tokens_out=400,
        )

    def _candidates(self, prompt: str) -> dict[str, Any]:
        number = int(prompt.split("EPISODE", 1)[1].split("\n", 1)[0].strip())
        episode = self.episodes[number]
        content = [b for b in episode.blocks if b.is_content]

        out: list[dict[str, Any]] = []
        # Three honest-ish spans: one good, one deliberately too short (the
        # repair should rescue it), one opening on CAMERA (must be rejected).
        for anchor in (content[0], content[len(content) // 2]):
            end = anchor.index
            while (
                end + 1 < len(episode.blocks)
                and episode.span_seconds(anchor.index, end + 1)[1]
                - anchor.start_s
                < 35.0
            ):
                end += 1
            out.append(
                {
                    "segments": [{"start_block": anchor.index, "end_block": end}],
                    "hook": f"[scripted] {anchor.text[:60]}",
                    # Alternates a real label with an off-list one, so both
                    # branches of `_hook_type` are exercised: a valid label
                    # survives, an invalid one becomes "" and is counted as
                    # unlabelled rather than silently as "other" (D19).
                    "hook_type": "accusation" if len(out) % 2 == 0 else "NOT_A_TYPE",
                    "cliffhanger": "[scripted] cuts before the answer lands",
                    "why": "[scripted] test fixture",
                    "needs_to_know": "",
                }
            )
        camera = next((b for b in episode.blocks if b.kind == "CAMERA"), None)
        if camera is not None:
            # A span that opens on camera direction with no content beat for a
            # long time. Exists so the hook gate has something to reject.
            lonely = next(
                (
                    b
                    for b in episode.blocks[camera.index :]
                    if b.kind == "CAMERA"
                    and all(
                        not n.is_content or n.start_s - b.start_s > 3.0
                        for n in episode.blocks[b.index : b.index + 4]
                    )
                ),
                None,
            )
            if lonely is not None:
                out.append(
                    {
                        "segments": [
                            {"start_block": lonely.index, "end_block": min(lonely.index + 14, len(episode.blocks) - 1)}
                        ],
                        "hook": "[scripted] a camera move, which is not a hook",
                        "cliffhanger": "[scripted] nothing",
                        "why": "[scripted] should be rejected",
                        "needs_to_know": "",
                    }
                )
        return {"candidates": out}

    def _scores(self, prompt: str) -> dict[str, Any]:
        ids = [
            line.split()[1]
            for line in prompt.splitlines()
            if line.startswith("### ")
        ]
        scores = []
        for n, cid in enumerate(ids):
            base = 5 + (n % 5)  # spread so ordering and the floor both bite
            scores.append(
                {
                    "id": cid,
                    "hook_strength": min(10, base + 2),
                    "cliffhanger": min(10, base + 1),
                    "standalone": base,
                    "emotional_charge": max(1, base - 1),
                    "why": "[scripted] reason",
                    "weakness": "[scripted] weakness",
                }
            )
        return {"scores": scores}


def test_pipeline() -> None:
    episodes = {n: parse_episode(find_episode(n)) for n in EPISODES}
    provider = ScriptedProvider(episodes)
    settings = load_settings_profile("free")
    # job_dir=None disables the cache and the log, so the test cannot pollute
    # a real run's .llm_cache/ or llm.log.
    router = Router(settings, providers={"gemini": provider})

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        summary = run(
            out_dir=out,
            profile="free",
            episode_numbers=EPISODES,
            router=router,
            verbose=False,
        )

        assert summary["n_episodes"] == 3, summary
        assert summary["n_candidates_proposed"] > 0, summary
        assert provider.calls.count("candidates") == 3, provider.calls
        assert provider.calls.count("rank") >= 1, provider.calls

        payload = json.loads((out / "promos.json").read_text(encoding="utf-8"))
        promos = payload["promos"]
        assert promos, "pipeline produced no promos at all"

        gates = gate_mod.Gates.from_rubric()
        seen_ids = set()
        for promo in promos:
            assert promo["id"] not in seen_ids
            seen_ids.add(promo["id"])

            # Every shipped promo obeys every gate.
            assert gates.min_duration_s <= promo["duration_s"] <= gates.max_duration_s, promo
            assert 1 <= len(promo["segments"]) <= gates.max_segments, promo
            assert promo["hook_block"] is not None, promo
            assert promo["hook_offset_s"] <= gates.hook_deadline_s, promo

            # The hook block is a real content block, never CAMERA (D4).
            episode = episodes[promo["episode"]]
            assert episode.block(promo["hook_block"]).is_content, promo

            # Timestamps came from the block table, not from the model.
            for seg in promo["segments"]:
                lo, hi = episode.span_seconds(seg["start_block"], seg["end_block"])
                assert abs(seg["start_s"] - lo) < 0.01, seg
                assert abs(seg["end_s"] - hi) < 0.01, seg

            # Rule 4: all four raw axis scores survive into the output.
            assert set(promo["scores"]) == set(AXES), promo
            assert promo["weighted_score"] >= payload["summary"]["rubric"]["min_score"]
            # ACCURACY.md #2: the cliffhanger floor, not just the weighted total.
            assert (
                promo["scores"]["cliffhanger"]
                >= payload["summary"]["rubric"]["min_cliffhanger"]
            ), promo

        # Ranked descending.
        order = [p["weighted_score"] for p in promos]
        assert order == sorted(order, reverse=True), order

        # D19: the hook label reaches the output, and the two kinds of
        # "no useful label" stay apart. The scripted model alternates a valid
        # label with an off-list one, so both branches must show up: valid
        # ones in the distribution, invalid ones counted as unlabelled and
        # NOT silently folded into "other" (the ACCURACY.md #6 trap).
        from promo.schemas import HOOK_TYPES as _HT

        labels = {p["hook_type"] for p in promos}
        assert labels - {"", *_HT} == set(), f"off-vocabulary label shipped: {labels}"
        assert summary["hook_types"], "no hook_type distribution in the summary"
        assert all(k in _HT for k in summary["hook_types"]), summary["hook_types"]
        assert (
            sum(summary["hook_types"].values()) + summary["n_hooks_unlabelled"]
            == len(promos)
        ), summary
        assert "other" not in summary["hook_types"], (
            "the scripted model never returns 'other', so its presence means "
            "an off-list label was coerced into it"
        )

        # The camera-opening candidate was rejected by the hook gate.
        rejected = json.loads((out / "rejected.json").read_text(encoding="utf-8"))
        assert "no_hook_in_3s" in rejected["by_gate"], rejected["by_gate"]

        # ACCURACY.md #3: every pass's raw axes survive (rule 4), and the
        # published `scores` are their mean, not a replacement for them.
        for promo in promos:
            passes = promo["score_passes"]
            assert len(passes) == summary["rank_passes"], promo
            for axis in AXES:
                raw = [p[axis] for p in passes]
                assert all(isinstance(v, int) for v in raw), promo
                assert abs(promo["scores"][axis] - sum(raw) / len(raw)) < 0.01, promo
            assert promo["score_spread"] >= 0.0, promo

        for name in ("promos.json", "rejected.json", "ranked.md", "run_summary.json"):
            assert (out / name).is_file(), name

    _report(summary)


def test_the_repair_only_ever_shortens() -> None:
    """ACCURACY.md #0 / D14: a span under 20s is not a promo to be repaired.

    The brief asks for a 20-60 second clip. Every way of inflating a short span
    spends something the brief also asked for - the tail version played past
    the cliffhanger, the head version changed the opening the scorer judged -
    so neither is done. The gate rejects instead.

    Runs on the real pack when it is present, because this is where the
    behaviour was measured; skipped with a note otherwise, so the suite still
    works with no `pack/`.
    """
    try:
        episode = parse_episode(find_episode(4))
    except (FileNotFoundError, OSError):
        print("ok  test_the_repair_only_ever_shortens  (skipped, no pack/)")
        return

    gates = gate_mod.Gates.from_rubric()

    # Short spans: untouched, and rejected. These four were all silently
    # inflated to ~20s by one or other previous version of this function.
    for pairs in ([(88, 94)], [(41, 48)], [(20, 22)], [(0, 2)]):
        adjusted, note = gate_mod.fit_to_window(episode, pairs, gates)
        assert adjusted == pairs, (pairs, adjusted)
        assert note is None, note
        report = gate_mod.check(episode, adjusted, gates)
        assert not report.ok, pairs
        assert "too_short" in [f.gate for f in report.failures], report.failures

    # Over-long spans are still trimmed, because cutting earlier than the model
    # asked is the one direction that cannot hurt the cliffhanger.
    long_pairs = None
    for start in range(0, len(episode.blocks) - 2):
        for end in range(start + 2, len(episode.blocks)):
            lo, hi = episode.span_seconds(start, end)
            if hi - lo > gates.max_duration_s:
                long_pairs = [(start, end)]
                break
        if long_pairs:
            break
    assert long_pairs, "no over-long span in this episode to test trimming"

    before_dur = (lambda s: s[1] - s[0])(episode.span_seconds(*long_pairs[0]))
    adjusted, note = gate_mod.fit_to_window(episode, long_pairs, gates)
    assert adjusted != long_pairs, (long_pairs, before_dur)
    assert note and "trimmed" in note, note
    # It shortened, and the start never moved.
    assert adjusted[0][0] == long_pairs[0][0], (long_pairs, adjusted)
    assert adjusted[-1][1] < long_pairs[-1][1], (long_pairs, adjusted)
    report = gate_mod.check(episode, adjusted, gates)
    assert report.duration_s <= gates.max_duration_s, report.duration_s

    print("ok  test_the_repair_only_ever_shortens")


def test_rank_batches_are_deterministic_and_pass_dependent() -> None:
    """The batching half of the ACCURACY.md #3 fix, with no model involved."""

    class Stub:
        def __init__(self, episode: int, n: int) -> None:
            self.episode = episode
            self.id = f"ep{episode:03d}-c{n}"

    pool = [Stub(ep, n) for ep in (13, 18, 42) for n in range(1, 5)]

    def ids(batches):
        return [[c.id for c in b] for b in batches]

    # Deterministic: same input, same batches, whatever order it arrives in.
    assert ids(run_mod.rank_batches(pool, 5, 0)) == ids(
        run_mod.rank_batches(list(reversed(pool)), 5, 0)
    )

    even = run_mod.rank_batches(pool, 5, 0)
    odd = run_mod.rank_batches(pool, 5, 1)

    # Every candidate appears exactly once in each pass.
    for batches in (even, odd):
        seen = [c.id for b in batches for c in b]
        assert sorted(seen) == sorted(c.id for c in pool), seen

    # And the company is genuinely different - that is the whole point.
    def pairs(batches):
        return {
            frozenset((a.id, b.id))
            for batch in batches
            for a in batch
            for b in batch
            if a is not b
        }

    shared = pairs(even) & pairs(odd)
    assert len(shared) < len(pairs(even)) / 2, (
        f"odd pass reuses too much of the even pass's company: {len(shared)}"
    )

    # One batch means there is no composition to vary, and that is reported
    # rather than papered over.
    assert ids(run_mod.rank_batches(pool, 99, 0)) == ids(run_mod.rank_batches(pool, 99, 1))

    print("ok  test_rank_batches_are_deterministic_and_pass_dependent")


def test_the_hook_label_never_reaches_the_scoring_model() -> None:
    """D19: `hook_type` is metadata, and that is enforced, not asserted.

    The decision's whole claim is that labelling a hook cannot move its
    score. That is only true if the scoring model never sees the label, so
    this checks the card it *does* see - the same reasoning as D4: a
    guarantee the model is merely instructed to honour is unverifiable.

    MISTAKES.md #10: for every property the spec names, ask what would
    notice if it broke. Without this, somebody adds the label to
    `candidate_card` for context one day and nothing anywhere objects.
    """
    from dataclasses import replace

    import promo.schemas as schemas_mod
    from promo.parse import parse_text

    sample = Path(__file__).resolve().parents[1] / "examples" / "sample_episode.txt"
    episode = parse_text(sample.read_text(encoding="utf-8"), path=str(sample))
    gates = gate_mod.Gates.from_rubric()
    content = next(b for b in episode.blocks if b.is_content)
    pairs, _ = gate_mod.fit_to_window(
        episode, [(content.index, content.index + 8)], gates
    )
    report = gate_mod.check(episode, pairs, gates)
    candidate = run_mod.Candidate(
        id="ep099-c1",
        episode=99,
        segments=report.segments,
        hook="a line someone says",
        cliffhanger="the answer does not arrive",
        why="x",
        needs_to_know="",
        duration_s=30.0,
        hook_type="violence",
    )
    # The exact check, rather than searching the card for category words:
    # every label must produce a BYTE-IDENTICAL card. Substring matching
    # would be unsound in both directions - "reveal", "violence" and "other"
    # are ordinary English that appears in screenplay text and in rank.md on
    # its own account, so a match proves nothing and a miss proves nothing.
    baseline = run_mod.candidate_card(replace(candidate, hook_type=""), episode)
    for label in (*schemas_mod.HOOK_TYPES, "NOT_A_TYPE"):
        card = run_mod.candidate_card(replace(candidate, hook_type=label), episode)
        assert card == baseline, (
            f"the scoring card changes when hook_type is {label!r} - the "
            "label must not be able to anchor the scorer (D19)"
        )

    # And it must still reach the output, or it is metadata nobody can use.
    assert candidate.to_dict()["hook_type"] == "violence"

    print("ok  test_the_hook_label_never_reaches_the_scoring_model")


def test_selection_accounts_for_every_candidate() -> None:
    """ACCURACY.md #4: all four selection rules must leave a record.

    The assertion worth making is **conservation**, not "dedup logs
    something": every candidate handed to `select()` either ships or appears
    in `dropped`, exactly once. A per-rule check would pass while a fifth
    `continue` added later silently swallowed candidates - which is precisely
    how three of the four rules came to be unrecorded in the first place.

    Built from synthetic candidates rather than a run, because each rule needs
    a specific shape (a 4 on cliffhanger, a 70%-overlapping twin, a third
    promo in one episode) and waiting for a real season to contain all four is
    how a gap goes unnoticed. MISTAKES.md #10.
    """
    import promo.score as score_mod

    rubric = score_mod.Rubric.load()

    def candidate(
        cid: str, episode: int, span: tuple[float, float], cliff: int, hook: int
    ) -> run_mod.Candidate:
        start_s, end_s = span
        scores = {
            "hook_strength": hook,
            "cliffhanger": cliff,
            "standalone": 8,
            "emotional_charge": 8,
        }
        return run_mod.Candidate(
            id=cid,
            episode=episode,
            segments=[
                gate_mod.Segment(
                    start_block=int(start_s), end_block=int(end_s),
                    start_s=start_s, end_s=end_s,
                )
            ],
            hook=f"hook for {cid}",
            cliffhanger="unresolved",
            why="because",
            needs_to_know="nothing",
            duration_s=round(end_s - start_s, 2),
            scores=scores,
            weighted_score=round(
                sum(scores[a] * w for a, w in rubric.weights.items()), 2
            ),
            score_passes={a: [v] for a, v in scores.items()},
        )

    candidates = [
        # ships
        candidate("ep001-c1", 1, (0.0, 30.0), cliff=9, hook=9),
        # cliffhanger floor is 5, so a 4 is out however strong the rest is
        candidate("ep001-c2", 1, (100.0, 130.0), cliff=4, hook=10),
        # every axis low -> under the 6.0 weighted floor
        candidate("ep002-c1", 2, (0.0, 30.0), cliff=5, hook=2),
        # near-identical twin of ep003-c1, one second shifted: ~97% overlap
        candidate("ep003-c1", 3, (0.0, 30.0), cliff=9, hook=9),
        candidate("ep003-c2", 3, (1.0, 31.0), cliff=8, hook=8),
        # episode 4 gets three clean, non-overlapping promos; the cap is 2
        candidate("ep004-c1", 4, (0.0, 30.0), cliff=9, hook=9),
        candidate("ep004-c2", 4, (40.0, 70.0), cliff=8, hook=8),
        candidate("ep004-c3", 4, (80.0, 110.0), cliff=7, hook=7),
    ]

    dropped: list[dict] = []
    promos = run_mod.select(candidates, rubric, dropped=dropped)

    # The invariant. Nothing leaves select() unaccounted for.
    assert len(promos) + len(dropped) == len(candidates), (
        f"{len(candidates)} in, {len(promos)} shipped, {len(dropped)} recorded"
    )
    ids_in = {c.id for c in candidates}
    ids_out = {p.id for p in promos} | {d["id"] for d in dropped}
    assert ids_out == ids_in, ids_in ^ ids_out

    by_rule = {d["selection"]["rule"]: d for d in dropped}
    assert set(by_rule) == {"min_cliffhanger", "min_score", "dedup", "episode_cap"}, (
        f"not every rule fired: {sorted(by_rule)}"
    )

    # Each record must carry the number that caused it, not just a rule name.
    assert by_rule["min_cliffhanger"]["selection"]["cliffhanger"] == 4
    assert by_rule["min_score"]["selection"]["weighted_score"] < rubric.min_score
    # A relative rule is only explicable next to the candidate that won.
    assert by_rule["dedup"]["selection"]["lost_to"] == "ep003-c1"
    assert by_rule["dedup"]["selection"]["overlap"] >= run_mod.DEDUP_OVERLAP
    assert by_rule["episode_cap"]["selection"]["place_in_episode"] == 3
    assert by_rule["episode_cap"]["selection"]["cap"] == rubric.max_promos_per_episode
    # A cap drop is not a weak clip, and the record has to say so.
    assert by_rule["episode_cap"]["weighted_score"] >= rubric.min_score

    # The shape is a gate failure's shape, so one renderer handles both.
    for record in dropped:
        assert record["failures"] and record["failures"][0]["gate"] == (
            record["selection"]["rule"]
        )
        assert record["failures"][0]["detail"].strip(), record["id"]
        assert record["segments"] and "start_s" in record["segments"][0]

    # And the survivors are the ones we expect, in ranked order.
    assert [p.id for p in promos] == [
        "ep001-c1", "ep003-c1", "ep004-c1", "ep004-c2",
    ], [p.id for p in promos]

    print(
        f"ok  test_selection_accounts_for_every_candidate  "
        f"({len(promos)} shipped, {len(dropped)} recorded: "
        f"{sorted(by_rule)})"
    )


#: A synthetic episode built for one purpose: block 2 is a 22-second SOUND FX
#: cue whose end runs far past every line of dialogue around it. This is the
#: ACCURACY.md #5 shape, written by hand so the test needs no `pack/`.
UMBRELLA_EPISODE = """EPISODE NUMBER: 98
EPISODE LOGLINE: A test fixture for the umbrella-block span rule.
CONTINUITY NOTES: Synthetic. No real episode is reproduced here.

SCENE 1
Scene heading: INT. A BELL TOWER - NIGHT

**ACTION:**
Start: (00:00.00) | End: (00:03.00)
She reaches the top of the stair and stops.

**MAYA (Hard):**
Start: (00:03.10) | End: (00:08.00)
"You said he was dead. You stood at the grave and you said it."

**SOUND FX:**
Start: (00:05.00) | End: (00:27.00)
A bell begins to toll and keeps tolling under everything that follows.

**RAVI (Quiet):**
Start: (00:08.20) | End: (00:12.00)
"I said what your mother paid me to say."

**CAMERA:**
Start: (00:12.10) | End: (00:30.00)
Hold on her face as the tolling continues. Do not cut.

**MAYA (Breaking):**
Start: (00:12.50) | End: (00:16.00)
"Then say it again. Say it to me now."
"""


def test_an_umbrella_block_cannot_decide_where_a_promo_ends() -> None:
    """ACCURACY.md #5: only content blocks may set the span end.

    A `SOUND FX` or `CAMERA` block can be far longer than the dialogue nested
    inside it. Letting one of those set the end pushed the clip past the last
    beat a viewer perceives - past the cliffhanger the model named and the
    scorer judged. That is the same defect as #0, arriving by a back door:
    D14 forbids extending a clip, and the span rule was extending it anyway.

    The rule now matches D4, which is the whole argument for it: **content
    blocks decide the hook and the end; CAMERA and SOUND FX decide neither.**
    """
    from promo.parse import parse_text

    episode = parse_text(UMBRELLA_EPISODE, number=98, path="<umbrella>")
    kinds = [b.kind for b in episode.blocks]
    assert "SOUND FX" in kinds and "CAMERA" in kinds, kinds

    # Blocks 0-4: ACTION, MAYA, SOUND FX(->27.0), RAVI, CAMERA(->30.0).
    # The last *content* block in that range is RAVI, ending at 12.00.
    lo, hi = episode.span_seconds(0, 4)
    assert lo == 0.0, lo
    assert hi == 12.0, (
        f"span end is {hi}, not 12.0 - an umbrella block set the end. "
        "SOUND FX runs to 27.0 and CAMERA to 30.0; neither is perceivable "
        "content and neither may decide where the promo stops."
    )

    # The whole episode: the last content block is MAYA, ending at 16.00,
    # even though CAMERA runs to 30.00.
    lo, hi = episode.span_seconds(0, len(episode.blocks) - 1)
    assert hi == 16.0, f"span end {hi} should be the last dialogue end, 16.0"

    # Overlap is still handled: a content block nested inside an earlier one
    # must not be cut short just because it is not last.
    lo, hi = episode.span_seconds(1, 3)
    assert hi == 12.0, hi

    # The documented fallback: a range with no content block at all keeps the
    # old behaviour, because there is no perceivable end to prefer.
    sfx = next(b.index for b in episode.blocks if b.kind == "SOUND FX")
    lo, hi = episode.span_seconds(sfx, sfx)
    assert hi == 27.0, (
        f"span end {hi} - with no content block in range every block counts, "
        "or the function would have no end at all to return"
    )

    print("ok  test_an_umbrella_block_cannot_decide_where_a_promo_ends")


def test_a_missing_axis_is_countable_not_just_a_one() -> None:
    """ACCURACY.md #6: a judged 1 and an unanswered axis mean opposite things.

    `clamp` turns both into 1, which is the defect. The fix reports rather
    than repairs, so what this pins is that the *distinction survives* - the
    arithmetic is deliberately unchanged, and a test that only checked the
    score would pass either way.
    """
    import promo.score as score_mod

    rubric = score_mod.Rubric.load()
    full = {"hook_strength": 9, "cliffhanger": 8, "standalone": 7,
            "emotional_charge": 6}

    # A model that judged every axis, one of them a 1.
    judged = dict(full, emotional_charge=1)
    assert score_mod.missing_axes(judged) == [], "a judged 1 is an answer"

    # A model that did not answer that axis at all, and one that answered junk.
    for broken in ({k: v for k, v in full.items() if k != "emotional_charge"},
                   dict(full, emotional_charge=None),
                   dict(full, emotional_charge="n/a")):
        assert score_mod.missing_axes(broken) == ["emotional_charge"], broken
        # The two cases still produce the same number - that is the point of
        # #6 and why it had to be made visible some other way.
        assert rubric.axis_table(broken) == rubric.axis_table(judged)
        assert rubric.weighted(broken) == rubric.weighted(judged)

    # Every axis absent is reported in full, in rubric order, not as one flag.
    assert score_mod.missing_axes({}) == list(AXES)

    # A 0 or a 99 is an answer, however wrong: clamp's job, not this one.
    assert score_mod.missing_axes(dict(full, standalone=0)) == []
    assert score_mod.missing_axes(dict(full, standalone=99)) == []

    print("ok  test_a_missing_axis_is_countable_not_just_a_one")


def _report(summary) -> None:
    print(
        f"OK  {summary['n_candidates_proposed']} proposed, "
        f"{summary['n_passed_gates']} passed gates, "
        f"{summary['n_promos']} shipped, "
        f"{summary['n_rejected_by_gates']} rejected "
        f"({summary['rejections_by_gate']}), "
        f"{summary['duration_repairs']} duration repairs"
    )


if __name__ == "__main__":
    test_rank_batches_are_deterministic_and_pass_dependent()
    test_the_repair_only_ever_shortens()
    test_the_hook_label_never_reaches_the_scoring_model()
    test_selection_accounts_for_every_candidate()
    test_an_umbrella_block_cannot_decide_where_a_promo_ends()
    test_a_missing_axis_is_countable_not_just_a_one()
    test_pipeline()
