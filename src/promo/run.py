"""The pipeline: parse -> candidates -> gates -> score -> rank -> outputs/.

Two model passes (D6), mirroring shorts-clipper's recall/rerank split:

1. **candidates** - one call per episode. Cheap, cacheable, individually
   re-runnable, and told to favour coverage over taste. Returns block indices.
2. **rank** - scores the surviving shortlist on four axes, 1-10, in batches.

Everything between and after those two calls is deterministic Python: the
index-to-timestamp lookup, the gates, the duration repair, the weighted sum,
the deduplication and the ordering. **The model never emits a timestamp and
never emits a ranking** - it emits indices and axis scores, and arithmetic
does the rest. That division is the answer to the brief's question about what
you gave to AI and what you kept as code.

    python -m promo.run                        # all 50, free profile
    python -m promo.run --episodes 1 17 44     # three, to read with your eyes
    python -m promo.run --profile claude       # paid, same everything else
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from promo import gates as gate_mod
from promo.config import (
    DEFAULT_SETTINGS_PATH,
    available_profiles,
    describe_profile,
    is_paid,
    load_env,
    load_settings_profile,
)
from promo.llm import Router
from promo.parse import DEFAULT_PACK, Episode, find_episode, load_season, parse_episode
from promo.schemas import AXES, CANDIDATES_SCHEMA, HOOK_TYPES, RANK_SCHEMA
from promo.score import Rubric, missing_axes, rank_key

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_OUT = Path("outputs")

#: How many candidates go into one `rank` call. Small enough that a single
#: failure costs one batch rather than the season. D6 says "one season-wide
#: pass"; batching is the robust form of it.
#:
#: It used to say here that a batch lets the model "see its neighbours and use
#: the full 1-10 range instead of scoring in a vacuum". That was the bug, not
#: the feature: a score calibrated against its neighbours is only valid within
#: its batch, and `select()` then compares every batch against every other.
#: The batch now exists purely for throughput and failure isolation, `rank.md`
#: tells the model to ignore its company, and `RANK_PASSES` measures whether
#: it managed to. See ACCURACY.md #3.
RANK_BATCH = 12

#: How many times each candidate is scored, in deliberately dissimilar batches
#: (see `rank_batches`). Two is the cheapest number that yields an error bar.
#: One restores the old single-pass behaviour; the cost is linear in this.
RANK_PASSES = 2

#: Two surviving candidates in one episode that overlap by more than this are
#: the same promo with a different cut. Keep the better-scored one.
DEDUP_OVERLAP = 0.70


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


# --- pass 1: candidates --------------------------------------------------


def episode_prompt(episode: Episode) -> str:
    """The user message for the candidates call. Indices, plus a clock.

    D27a: the model is handed each block's absolute start and end time so it
    can measure a segment exactly, and still answers in block indices only -
    `schemas.SEGMENT` has nowhere to put a time. The scoring call does *not*
    get the clock; see `candidate_block`.
    """
    return "\n".join(
        [
            f"EPISODE {episode.number}",
            f"LOGLINE: {episode.logline}",
            f"CONTINUITY SO FAR: {episode.continuity}",
            f"BLOCKS: 0 to {len(episode.blocks) - 1}",
            "",
            "Full episode, block by block:",
            "",
            episode.render(),
        ]
    )


def propose_candidates(episode: Episode, router: Router) -> list[dict[str, Any]]:
    """One call. Returns the model's raw candidates, unvalidated."""
    data = router.complete(
        "candidates",
        episode_prompt(episode),
        system=load_prompt("candidates"),
        json_schema=CANDIDATES_SCHEMA,
        temperature=0.4,  # recall task - a little spread is wanted here
    )
    out = data.get("candidates")
    return out if isinstance(out, list) else []


# --- the gates (no model) ------------------------------------------------


@dataclass(slots=True)
class Candidate:
    """One proposal, carried through gating and scoring."""

    id: str
    episode: int
    segments: list[gate_mod.Segment]
    hook: str
    cliffhanger: str
    why: str
    needs_to_know: str
    duration_s: float
    #: One of `schemas.HOOK_TYPES`. Editor-facing metadata, never a judgement:
    #: it is not scored, not weighted, not gated, and `score.py` never reads
    #: it. Defaulted because a model that omits it must not break the run -
    #: an unlabelled promo is a missing label, not a failed candidate (D19).
    hook_type: str = ""
    episode_duration_s: float = 0.0
    hook_block: int | None = None
    hook_offset_s: float | None = None
    adjustment: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    weighted_score: float = 0.0
    rank_why: str = ""
    weakness: str = ""
    #: One raw axis table per rank pass, in pass order. Rule 4: `scores` above
    #: is the mean of these, and the means never replace the originals.
    score_passes: list[dict[str, int]] = field(default_factory=list)
    #: Axes a rank response did not answer, which `clamp` silently turned
    #: into 1s. ACCURACY.md #6: counted so the collapse is visible.
    missing_axes: list[str] = field(default_factory=list)
    #: Highest minus lowest weighted total across the passes. The error bar on
    #: this candidate's position in the ranking. See ACCURACY.md #3.
    score_spread: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Output record. Quotes the hook and cliffhanger lines only (D8)."""
        return {
            "id": self.id,
            "episode": self.episode,
            "duration_s": round(self.duration_s, 2),
            "episode_duration_s": round(self.episode_duration_s, 2),
            "segments": [s.to_dict() for s in self.segments],
            "hook": self.hook,
            "hook_type": self.hook_type,
            "cliffhanger": self.cliffhanger,
            "why": self.rank_why or self.why,
            "weakness": self.weakness,
            "needs_to_know": self.needs_to_know,
            "scores": self.scores,
            "weighted_score": self.weighted_score,
            "score_passes": self.score_passes,
            "missing_axes": self.missing_axes,
            "score_spread": self.score_spread,
            "hook_block": self.hook_block,
            "hook_offset_s": self.hook_offset_s,
            "duration_adjustment": self.adjustment,
        }


def _hook_type(value: Any) -> str:
    """Normalise the model's `hook_type` against `schemas.HOOK_TYPES`.

    The real enforcement is the provider's own enum handling - Gemini,
    OpenAI and Anthropic all constrain a schema `enum` server-side - so this
    is the belt to that braces, and it exists for the `--profile local` case
    where a small model may ignore the constraint entirely.

    Note what it deliberately does **not** do: it does not coerce an
    unrecognised label to `"other"`. That would overload one value with two
    meanings - "the model judged this `other`" and "the model said something
    off-list" - which is exactly the defect `notes/ACCURACY.md` #6 records
    for a missing axis becoming a silent 1. An off-list label is dropped to
    the empty string, and the empty count is reported separately from the
    `other` count, so the two stay distinguishable.
    """
    label = str(value or "").strip().lower()
    return label if label in HOOK_TYPES else ""


def _pairs(raw: dict[str, Any]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for seg in raw.get("segments") or []:
        try:
            out.append((int(seg["start_block"]), int(seg["end_block"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def gate_episode(
    episode: Episode,
    raw_candidates: list[dict[str, Any]],
    gates: gate_mod.Gates,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Apply every gate. Returns (survivors, rejections-with-reasons).

    Rejections are kept, not discarded: the counts by gate are the evidence
    for the write-up, and a tool that cannot say why it declined is not
    auditable.
    """
    accepted: list[Candidate] = []
    rejected: list[dict[str, Any]] = []

    for i, raw in enumerate(raw_candidates, start=1):
        cid = f"ep{episode.number:03d}-c{i}"
        pairs = _pairs(raw)
        if not pairs:
            rejected.append(
                {
                    "id": cid,
                    "episode": episode.number,
                    "hook": str(raw.get("hook", ""))[:200],
                    "failures": [
                        {"gate": "no_segments", "detail": "model returned no usable segments"}
                    ],
                }
            )
            continue

        adjusted, note = gate_mod.fit_to_window(episode, pairs, gates)
        report = gate_mod.check(episode, adjusted, gates)

        if not report.ok:
            rejected.append(
                {
                    "id": cid,
                    "episode": episode.number,
                    "hook": str(raw.get("hook", ""))[:200],
                    "duration_s": report.duration_s,
                    "segments": [s.to_dict() for s in report.segments],
                    "duration_adjustment": note,
                    "failures": [
                        {"gate": f.gate, "detail": f.detail} for f in report.failures
                    ],
                }
            )
            continue

        accepted.append(
            Candidate(
                id=cid,
                episode=episode.number,
                segments=report.segments,
                hook=str(raw.get("hook", "")).strip(),
                hook_type=_hook_type(raw.get("hook_type")),
                cliffhanger=str(raw.get("cliffhanger", "")).strip(),
                why=str(raw.get("why", "")).strip(),
                needs_to_know=str(raw.get("needs_to_know", "")).strip(),
                duration_s=report.duration_s,
                episode_duration_s=episode.duration_s,
                hook_block=report.hook_block,
                hook_offset_s=report.hook_offset_s,
                adjustment=note,
            )
        )

    return accepted, rejected


# --- pass 2: scoring -----------------------------------------------------


def candidate_card(candidate: Candidate, episode: Episode) -> str:
    """How one candidate is shown to the scoring model: as a viewer sees it.

    **`hook_type` is deliberately absent from this card** (D19). The claim
    that the label changes no ranking is only worth making if it is true by
    construction, and this is where it becomes true: the scoring model never
    sees the label, so it cannot anchor on it - a `violence` tag cannot talk
    it into a higher `hook_strength` than the same beat tagged `romance`.
    The alternative - passing the label and instructing the model to ignore
    it - is the unverifiable kind of guarantee D4 exists to avoid.
    """
    lines = [
        f"### {candidate.id}  (episode {candidate.episode}, "
        f"{candidate.duration_s:.1f}s, {len(candidate.segments)} segment(s))",
        f"HOOK AS IDENTIFIED: {candidate.hook}",
        f"CLIFFHANGER AS IDENTIFIED: {candidate.cliffhanger}",
        f"NEEDS TO KNOW: {candidate.needs_to_know or '(nothing claimed)'}",
        "",
    ]
    for n, seg in enumerate(candidate.segments, start=1):
        if len(candidate.segments) > 1:
            lines.append(f"-- segment {n} --")
        for block in episode.blocks[seg.start_block : seg.end_block + 1]:
            lines.append(
                block.as_line(
                    truncate=110 if block.kind == "CAMERA" else None,
                    show_duration=False,
                    # Byte-identical to the pre-D27 rendering on purpose: the
                    # clock goes to the candidates prompt only, so the re-run
                    # changes recall and leaves ranking untouched.
                    show_clock=False,
                )
            )
    lines.append("")
    return "\n".join(lines)


def rank_batches(
    candidates: list[Candidate], size: int, pass_index: int
) -> list[list[Candidate]]:
    """Split candidates into rank batches, deterministically.

    Batch membership used to be whatever order the episodes happened to finish
    in, which made the whole ranking unreproducible. Here it is a pure function
    of the candidate set, the batch size and the pass number.

    Even passes take contiguous chunks of the season. Odd passes deal the same
    sorted list round-robin into the same number of buckets, so a candidate's
    neighbours on an odd pass are ones it did *not* sit beside on an even pass.
    That is the point: two scorings with deliberately dissimilar company, so
    averaging them cancels some of the batch-composition effect rather than
    averaging the same bias twice.

    With a single batch there is no composition to vary and both passes are
    identical - which the response cache turns into a free second call.
    """
    ordered = sorted(candidates, key=lambda c: (c.episode, c.id))
    if size < 1:
        size = 1
    if pass_index % 2 == 0:
        return [ordered[i : i + size] for i in range(0, len(ordered), size)]

    n_batches = max(1, math.ceil(len(ordered) / size))
    buckets: list[list[Candidate]] = [[] for _ in range(n_batches)]
    for i, candidate in enumerate(ordered):
        buckets[i % n_batches].append(candidate)
    return [b for b in buckets if b]


def score_batch(
    batch: list[Candidate],
    episodes: dict[int, Episode],
    router: Router,
    rubric: Rubric,
) -> None:
    """Score one batch in place, appending one pass. Failures append nothing.

    Temperature 0: any variation left between two passes is then attributable
    to batch composition, which is the thing being measured, rather than to
    sampling. See ACCURACY.md #3.
    """
    prompt = "\n".join(
        ["Score each candidate below.", ""]
        + [candidate_card(c, episodes[c.episode]) for c in batch]
    )
    data = router.complete(
        "rank",
        prompt,
        system=load_prompt("rank"),
        json_schema=RANK_SCHEMA,
        temperature=0.0,
    )

    by_id = {c.id: c for c in batch}
    for row in data.get("scores") or []:
        candidate = by_id.get(str(row.get("id", "")))
        if candidate is None:
            continue
        candidate.score_passes.append(rubric.axis_table(row))  # rule 4
        # ACCURACY.md #6. Recorded, not repaired - see score.missing_axes.
        for axis in missing_axes(row):
            if axis not in candidate.missing_axes:
                candidate.missing_axes.append(axis)
        # The prose comes from the first pass that supplies any; a second
        # opinion on the wording is not worth overwriting a good sentence.
        if not candidate.rank_why:
            candidate.rank_why = str(row.get("why", "")).strip()
        if not candidate.weakness:
            candidate.weakness = str(row.get("weakness", "")).strip()


def _spread_stats(candidates: list[Candidate]) -> dict[str, Any]:
    """How much the same clip's score moved between rank passes.

    This is the ACCURACY.md #3 defect, turned into a number the run reports on
    itself. `n_multi_pass` is how many candidates actually got more than one
    independent scoring - with a single batch both passes see identical company
    and the figure is vacuous, so it is published alongside.
    """
    multi = [c for c in candidates if len(c.score_passes) > 1]
    if not multi:
        return {
            "n_multi_pass": 0,
            "note": "every candidate scored once, or all in one batch - no comparison",
        }
    spreads = [c.score_spread for c in multi]
    disagree = [c for c in multi if c.score_spread >= 1.0]
    return {
        "n_multi_pass": len(multi),
        "median": round(statistics.median(spreads), 2),
        "mean": round(statistics.mean(spreads), 2),
        "max": round(max(spreads), 2),
        "n_over_1_point": len(disagree),
        "worst": sorted(
            ({"id": c.id, "spread": c.score_spread, "passes": c.score_passes}
             for c in disagree),
            key=lambda d: -float(d["spread"]),
        )[:5],
    }


def consolidate(candidates: list[Candidate], rubric: Rubric) -> None:
    """Fold each candidate's rank passes into its final score, in place."""
    for candidate in candidates:
        if not candidate.score_passes:
            continue
        axes, weighted, spread = rubric.consolidate(candidate.score_passes)
        candidate.scores = axes
        candidate.weighted_score = weighted
        candidate.score_spread = spread


def score_all(
    candidates: list[Candidate],
    episodes: dict[int, Episode],
    router: Router,
    rubric: Rubric,
    *,
    batch_size: int = RANK_BATCH,
    passes: int = RANK_PASSES,
    on_failure: Callable[[int, int, Exception], None] | None = None,
) -> None:
    """Run every rank pass over every batch, then consolidate. In place."""
    for pass_index in range(max(1, passes)):
        for n, batch in enumerate(
            rank_batches(candidates, batch_size, pass_index), start=1
        ):
            try:
                score_batch(batch, episodes, router, rubric)
            except Exception as exc:  # one bad batch must not lose the run
                if on_failure is not None:
                    on_failure(pass_index, n, exc)
    consolidate(candidates, rubric)


# --- selection (no model) ------------------------------------------------


def overlap_fraction(a: Candidate, b: Candidate) -> float:
    """Intersection over union, in seconds, across all segments."""

    def spans(c: Candidate) -> list[tuple[float, float]]:
        return [(s.start_s, s.end_s) for s in c.segments]

    inter = sum(
        max(0.0, min(ae, be) - max(as_, bs))
        for as_, ae in spans(a)
        for bs, be in spans(b)
    )
    union = a.duration_s + b.duration_s - inter
    return inter / union if union > 0 else 0.0


def _selection_drop(
    candidate: Candidate,
    rule: str,
    detail: str,
    **facts: Any,
) -> dict[str, Any]:
    """One selection rejection, in the same shape `gate_episode` writes.

    Deliberately the *same* keys as a gate failure, because `rejected.json`,
    `web/` and `tests/test_demo_path.py` already read that shape and a second
    record layout would mean a second code path for nothing.

    The one addition is ``selection``, a small dict of the numbers that caused
    the drop, and it exists because two of the four rules are **relative**.
    "cliffhanger 3 below floor 5" explains itself. "dropped by dedup" does
    not: it only means something next to *which* candidate won and by how much
    overlap. Hard rule 4's reasoning applies to selection too - keep the
    evidence, not the conclusion. It is one key rather than three loose ones so
    that gate records stay byte-identical to what they were before.
    """
    return {
        "id": candidate.id,
        "episode": candidate.episode,
        "hook": candidate.hook[:200],
        "duration_s": candidate.duration_s,
        "segments": [s.to_dict() for s in candidate.segments],
        "scores": dict(candidate.scores or {}),
        "weighted_score": candidate.weighted_score,
        "failures": [{"gate": rule, "detail": detail}],
        "selection": {"rule": rule, **facts},
    }


def select(
    candidates: list[Candidate],
    rubric: Rubric,
    *,
    dropped: list[dict[str, Any]] | None = None,
) -> list[Candidate]:
    """Drop weak and duplicate promos, then order the season.

    Four deterministic steps, in this order:

    1. the `min_cliffhanger` floor - a failed brief requirement, not a low score
    2. the rubric's `min_score` floor
    3. near-duplicate removal inside an episode (two cuts of the same beat)
    4. the `max_promos_per_episode` cap

    Step 1 is separate from step 2 on purpose. `cliffhanger` carries 0.30 of
    the weight, so a 3 instead of a 10 costs only 2.1 points and three strong
    axes outvote it - which is how a promo whose own scorer wrote "the clip
    ends on a tender reassurance, completely diffusing the tension" shipped at
    6.50. An axis the brief names by name gets a floor of its own.

    **Every one of the four now writes to `dropped`** (ACCURACY.md #4). The
    invariant that matters, and that `test_selection_accounts_for_every_candidate`
    asserts, is that nothing leaves this function unaccounted for:

        len(returned) + len(dropped) == len(candidates)

    A candidate that fails steps 1 and 2 both is recorded once, under step 1.
    That is first-cause reporting and it is the right way round: the floors run
    in order of how much they mean, and `min_cliffhanger` means more, because
    it is a requirement the brief states rather than a threshold we chose.
    """

    def drop(candidate: Candidate, rule: str, detail: str, **facts: Any) -> None:
        if dropped is not None:
            dropped.append(_selection_drop(candidate, rule, detail, **facts))

    kept: list[Candidate] = []
    for candidate in candidates:
        cliff = (candidate.scores or {}).get("cliffhanger")
        if isinstance(cliff, (int, float)) and cliff < rubric.min_cliffhanger:
            drop(
                candidate,
                "min_cliffhanger",
                f"cliffhanger {cliff} below floor {rubric.min_cliffhanger}; "
                f"the brief requires an unresolved ending",
                cliffhanger=cliff,
                floor=rubric.min_cliffhanger,
            )
            continue
        if candidate.weighted_score < rubric.min_score:
            drop(
                candidate,
                "min_score",
                f"weighted score {candidate.weighted_score} below floor "
                f"{rubric.min_score}; it cleared every gate, so this is a "
                f"judgement about quality and not about legality",
                weighted_score=candidate.weighted_score,
                floor=rubric.min_score,
            )
            continue
        kept.append(candidate)
    kept.sort(key=rank_key)

    deduped: list[Candidate] = []
    for candidate in kept:
        twin: Candidate | None = None
        overlap = 0.0
        for other in deduped:
            if other.episode != candidate.episode:
                continue
            fraction = overlap_fraction(other, candidate)
            if fraction >= DEDUP_OVERLAP:
                twin, overlap = other, fraction
                break
        if twin is not None:
            drop(
                candidate,
                "dedup",
                f"{overlap:.0%} of its runtime is shared with {twin.id} "
                f"(threshold {DEDUP_OVERLAP:.0%}), which ranked higher at "
                f"{twin.weighted_score} against {candidate.weighted_score}. "
                f"Two cuts of one beat, not two promos.",
                lost_to=twin.id,
                overlap=round(overlap, 3),
                threshold=DEDUP_OVERLAP,
            )
            continue
        deduped.append(candidate)

    # Two counters, not one: `place` must keep counting past the cap or every
    # candidate after the second would report itself as the third.
    kept_per_episode: Counter[int] = Counter()
    place_in_episode: Counter[int] = Counter()
    final: list[Candidate] = []
    for candidate in deduped:
        place_in_episode[candidate.episode] += 1
        place = place_in_episode[candidate.episode]
        if kept_per_episode[candidate.episode] >= rubric.max_promos_per_episode:
            drop(
                candidate,
                "episode_cap",
                f"ranked {place} within episode {candidate.episode}, which is "
                f"capped at {rubric.max_promos_per_episode}. It was outranked, "
                f"not judged weak - it scored {candidate.weighted_score}, above "
                f"the {rubric.min_score} floor.",
                place_in_episode=place,
                cap=rubric.max_promos_per_episode,
            )
            continue
        kept_per_episode[candidate.episode] += 1
        final.append(candidate)

    return final


# --- cost ----------------------------------------------------------------


def run_episode(
    episode: Episode,
    router: Router,
    *,
    rubric: Rubric | None = None,
    gates: gate_mod.Gates | None = None,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """The whole pipeline for one episode. Used by the demo's live tab.

    Same functions the batch run calls, in the same order, so what a grader
    sees in the demo is exactly what produced `outputs/`.
    """
    rubric = rubric or Rubric.load()
    gates = gates or gate_mod.Gates.from_rubric()

    raw = propose_candidates(episode, router)
    accepted, rejected = gate_episode(episode, raw, gates)
    score_all(accepted, {episode.number: episode}, router, rubric)
    promos = select([c for c in accepted if c.scores], rubric, dropped=rejected)
    return promos, rejected


def spend_from_log(log_path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Total real tokens and dollars out of llm.log. Not an estimate."""
    pricing = settings.get("pricing") or {}
    totals: dict[str, dict[str, float]] = {}
    calls = cached = 0

    if not log_path.is_file():
        return {"calls": 0, "cached_calls": 0, "by_model": {}, "usd_total": 0.0}

    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") not in {"ok", "cache_hit"}:
            continue
        calls += 1
        if rec.get("cached"):
            cached += 1
            continue  # a cache hit costs nothing - do not bill it
        model = str(rec.get("model", "?"))
        bucket = totals.setdefault(model, {"tokens_in": 0.0, "tokens_out": 0.0, "usd": 0.0})
        bucket["tokens_in"] += float(rec.get("tokens_in", 0) or 0)
        bucket["tokens_out"] += float(rec.get("tokens_out", 0) or 0)

    for model, bucket in totals.items():
        price = pricing.get(model) or {}
        bucket["usd"] = round(
            bucket["tokens_in"] / 1e6 * float(price.get("in", 0.0))
            + bucket["tokens_out"] / 1e6 * float(price.get("out", 0.0)),
            4,
        )

    return {
        "calls": calls,
        "cached_calls": cached,
        "by_model": totals,
        "usd_total": round(sum(b["usd"] for b in totals.values()), 4),
    }


# --- reporting -----------------------------------------------------------


def write_markdown(path: Path, promos: list[Candidate], summary: dict[str, Any]) -> None:
    """The human-readable ranking. Hook and cliffhanger lines only (D8)."""
    lines = [
        "# Promos, ranked",
        "",
        f"`{summary['profile']}` · {summary['n_episodes']} episodes · "
        f"{summary['n_promos']} promos · generated {summary['finished_at']}",
        "",
        "Timestamps are per-episode `MM:SS.ss`, computed from the parsed block",
        "table - the model returned block indices only.",
        "",
        "| # | Ep | Segments | Len | Score | Hook | Cuts on |",
        "|---|----|----------|-----|-------|------|---------|",
    ]
    for n, promo in enumerate(promos, start=1):
        segs = " + ".join(
            f"{s.to_dict()['start']}-{s.to_dict()['end']}" for s in promo.segments
        )
        hook = promo.hook.replace("|", "\\|")
        cliff = promo.cliffhanger.replace("|", "\\|")
        lines.append(
            f"| {n} | {promo.episode} | {segs} | {promo.duration_s:.0f}s | "
            f"{promo.weighted_score:.2f} | {hook} | {cliff} |"
        )

    lines += ["", "## Post these first", ""]
    for n, promo in enumerate(promos[:10], start=1):
        axes = " · ".join(f"{a.replace('_', ' ')} {promo.scores.get(a, 0)}" for a in AXES)
        segs = ", ".join(
            f"{s.to_dict()['start']}-{s.to_dict()['end']}" for s in promo.segments
        )
        lines += [
            f"**{n}. Episode {promo.episode}** — {segs} ({promo.duration_s:.0f}s) "
            f"· **{promo.weighted_score:.2f}**"
            + (f" +/-{promo.score_spread:.2f}" if promo.score_spread else ""),
            "",
            f"- **Hook:** {promo.hook}",
            f"- **Cliffhanger:** {promo.cliffhanger}",
            f"- **Why it works:** {promo.rank_why or promo.why}",
            f"- **Weakest point:** {promo.weakness or '(not reported)'}",
            f"- Axes: {axes}",
            "",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- the run -------------------------------------------------------------


def run(
    *,
    pack_dir: Path | str = DEFAULT_PACK,
    out_dir: Path | str = DEFAULT_OUT,
    profile: str | None = None,
    settings_path: Path | str = DEFAULT_SETTINGS_PATH,
    episode_numbers: list[int] | None = None,
    router: Router | None = None,
    rank_batch: int = RANK_BATCH,
    rank_passes: int = RANK_PASSES,
    verbose: bool = True,
) -> dict[str, Any]:
    started = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = load_settings_profile(profile, settings_path)
    router = router or Router(settings, job_dir=Path("."))
    rubric = Rubric.load()
    gates = gate_mod.Gates.from_rubric()

    if episode_numbers:
        episodes = [parse_episode(find_episode(n, pack_dir)) for n in episode_numbers]
    else:
        episodes = load_season(pack_dir)
    by_number = {e.number: e for e in episodes}

    if verbose:
        print(describe_profile(settings))
        if is_paid(settings):
            print("  !! this profile bills a paid API. Ctrl-C now if unintended.")
        print(f"  {len(episodes)} episodes, "
              f"{sum(len(e.blocks) for e in episodes)} blocks")

    accepted: list[Candidate] = []
    rejected: list[dict[str, Any]] = []
    failed_episodes: list[dict[str, str]] = []

    for episode in episodes:
        try:
            raw = propose_candidates(episode, router)
        except Exception as exc:
            failed_episodes.append({"episode": str(episode.number), "error": repr(exc)})
            if verbose:
                print(f"  ep{episode.number:>3}  CALL FAILED  {type(exc).__name__}")
            continue
        ok, bad = gate_episode(episode, raw, gates)
        accepted.extend(ok)
        rejected.extend(bad)
        if verbose:
            print(f"  ep{episode.number:>3}  proposed {len(raw):>2}  "
                  f"passed gates {len(ok):>2}  rejected {len(bad):>2}")

    if verbose:
        n_batches = len(rank_batches(accepted, rank_batch, 0))
        print(f"\nscoring {len(accepted)} candidates: {rank_passes} pass(es) over "
              f"{n_batches} batch(es) of up to {rank_batch}")

    def report_batch_failure(pass_index: int, n: int, exc: Exception) -> None:
        if verbose:
            print(f"  pass {pass_index + 1} batch {n} FAILED: {type(exc).__name__}")

    score_all(
        accepted,
        by_number,
        router,
        rubric,
        batch_size=rank_batch,
        passes=rank_passes,
        on_failure=report_batch_failure,
    )

    unscored = [c for c in accepted if not c.scores]
    selection_drops: list[dict[str, Any]] = []
    promos = select(
        [c for c in accepted if c.scores], rubric, dropped=selection_drops
    )

    gate_counts = Counter(
        f["gate"] for r in rejected for f in r.get("failures", [])
    )
    selection_counts = Counter(
        f["gate"] for r in selection_drops for f in r.get("failures", [])
    )
    declined = sorted(
        {e.number for e in episodes} - {p.episode for p in promos}
    )

    summary: dict[str, Any] = {
        "profile": describe_profile(settings),
        "paid": is_paid(settings),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "n_episodes": len(episodes),
        "n_candidates_proposed": len(accepted) + len(rejected),
        "n_passed_gates": len(accepted),
        "n_rejected_by_gates": len(rejected),
        "n_unscored": len(unscored),
        "n_promos": len(promos),
        "rejections_by_gate": dict(gate_counts.most_common()),
        "rank_passes": rank_passes,
        "rank_batch": rank_batch,
        # The ACCURACY.md #3 measurement, computed on every run from now on:
        # how far the same clip's weighted score moves between two scorings in
        # dissimilar batches. Small = the scores mean the same thing season-wide
        # and the ranking is trustworthy. Large = the ranking is partly an
        # artefact of how candidates were grouped, and must be reported as such.
        "score_spread": _spread_stats(accepted),
        "n_dropped_in_selection": len(selection_drops),
        "selection_drops_by_rule": dict(selection_counts.most_common()),
        "episodes_with_no_promo": declined,
        "n_episodes_with_no_promo": len(declined),
        "episode_call_failures": failed_episodes,
        "duration_repairs": sum(1 for c in accepted if c.adjustment),
        # D19. Editor-facing metadata, so this is reporting rather than
        # scoring: nothing downstream reads it. Two numbers are worth watching
        # and they mean different things. A high `other` rate says the
        # category list is wrong for this show. A high `unlabelled` rate says
        # the model is not returning the field at all - which is a provider or
        # prompt problem, not a taste problem. ACCURACY.md #6 is the reason
        # they are counted apart instead of collapsed into one bucket.
        "hook_types": dict(
            Counter(c.hook_type for c in promos if c.hook_type).most_common()
        ),
        "n_hooks_unlabelled": sum(1 for c in promos if not c.hook_type),
        # ACCURACY.md #6. A rank response that omits an axis has it silently
        # clamped to 1, which is indistinguishable from a judged 1 and means
        # the opposite thing. Counted over every scored candidate, not just
        # the shipped ones, because the ones it pushed under a floor are
        # exactly the ones that did not ship. **Non-zero here is a provider
        # or prompt bug to chase, never a taste problem.**
        "n_axes_missing": sum(len(c.missing_axes) for c in accepted),
        "candidates_with_a_missing_axis": sorted(
            c.id for c in accepted if c.missing_axes
        ),
        "spend": spend_from_log(Path("llm.log"), settings),
        "rubric": {
            "weights": rubric.weights,
            "min_score": rubric.min_score,
            "min_cliffhanger": rubric.min_cliffhanger,
            "max_promos_per_episode": rubric.max_promos_per_episode,
        },
    }

    (out_dir / "promos.json").write_text(
        json.dumps(
            {"summary": summary, "promos": [p.to_dict() for p in promos]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "rejected.json").write_text(
        json.dumps(
            {
                "note": (
                    "Every candidate the model proposed that a deterministic gate "
                    "threw out, plus the gate and the measured number. Kept on "
                    "purpose: these counts are the quality evidence."
                ),
                "by_gate": dict(gate_counts.most_common()),
                "rejected": rejected,
                "selection_note": (
                    "Candidates that passed every deterministic gate and were "
                    "then dropped during selection. Kept under a separate key "
                    "so the gate counts above stay a clean measure of the "
                    "gates. All four rules are recorded: min_cliffhanger and "
                    "min_score are absolute (a number against a floor), while "
                    "dedup and episode_cap are relative, so each of those "
                    "carries the candidate that beat it in `selection`. "
                    "Together with `rejected` above, every candidate the model "
                    "proposed is accounted for in exactly one place."
                ),
                "by_selection_rule": dict(selection_counts.most_common()),
                "dropped_in_selection": selection_drops,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_markdown(out_dir / "ranked.md", promos, summary)

    if verbose:
        print(f"\n{len(promos)} promos from {len(episodes)} episodes "
              f"({len(declined)} episodes produced none)")
        if gate_counts:
            print("rejections by gate: " + ", ".join(
                f"{g}={n}" for g, n in gate_counts.most_common()))
        if selection_counts:
            print("dropped in selection: " + ", ".join(
                f"{g}={n}" for g, n in selection_counts.most_common()))
        sp = summary["score_spread"]
        if sp.get("n_multi_pass"):
            print(f"score spread across {rank_passes} rank passes: "
                  f"median {sp['median']}  mean {sp['mean']}  max {sp['max']}  "
                  f"({sp['n_over_1_point']}/{sp['n_multi_pass']} moved >= 1.0)")
        spend = summary["spend"]
        print(f"calls {spend['calls']} ({spend['cached_calls']} cached)  "
              f"spend ${spend['usd_total']:.4f}")
        print(f"wrote {out_dir}/promos.json, rejected.json, ranked.md, run_summary.json")

    return summary


def main(argv: list[str] | None = None) -> int:
    # Before anything that needs a key: `.env` is documented as the place to
    # put one, so something has to read it. MISTAKES.md #11.
    load_env()
    ap = argparse.ArgumentParser(description="Find promos across the season.")
    ap.add_argument("--profile", choices=available_profiles(), default=None,
                    help="LLM profile from config/settings.yaml (default: free)")
    ap.add_argument("--episodes", type=int, nargs="+", default=None,
                    help="only these episode numbers")
    ap.add_argument("--skip-episodes", type=int, nargs="+", default=None,
                    help="exclude these episode numbers. Held the eval set "
                         "(1 44 36 17 29) back until it was labelled; D28 ran "
                         "it unlabelled, so nothing is held back now.")
    ap.add_argument("--rank-batch", type=int, default=RANK_BATCH,
                    help=f"candidates per rank call (default {RANK_BATCH}). "
                         "Vary it to measure the batch-composition effect.")
    ap.add_argument("--rank-passes", type=int, default=RANK_PASSES,
                    help=f"independent scorings per candidate, in dissimilar "
                         f"batches (default {RANK_PASSES}; 1 = old behaviour)")
    ap.add_argument("--pack", default=str(DEFAULT_PACK))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    episode_numbers = args.episodes
    if args.skip_episodes:
        skip = set(args.skip_episodes)
        pool = episode_numbers or [e.number for e in load_season(args.pack)]
        episode_numbers = [n for n in pool if n not in skip]

    run(
        pack_dir=args.pack,
        out_dir=args.out,
        profile=args.profile,
        episode_numbers=episode_numbers,
        rank_batch=args.rank_batch,
        rank_passes=args.rank_passes,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
