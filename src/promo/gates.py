"""The deterministic gates. Pure Python, no model, no prompt.

This is D4, and it is the project's main point of difference. The brief asks
directly what you handed to a model and what you kept as code. "I put the
3-second hook rule in the prompt" is unverifiable - the model will simply
assert that it complied. Here the rule is arithmetic on the block table:

    a DIALOGUE or ACTION block must START within 3.0s of the promo's start,
    and a CAMERA block never counts

CAMERA is 47% of all blocks and communicates nothing to a scrolling viewer, so
a promo whose first three seconds are camera language has no hook even if the
model insists it does.

Every rejection carries the gate it failed and the measured number, because
the rejection counts are evidence for the write-up's quality-checking section,
not debug output. Thresholds live in ``config/rubric.yaml`` - never here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from promo.parse import Episode

DEFAULT_RUBRIC_PATH = Path("config/rubric.yaml")


@dataclass(frozen=True, slots=True)
class Gates:
    """Thresholds, loaded from ``config/rubric.yaml``."""

    min_duration_s: float = 20.0
    max_duration_s: float = 60.0
    hook_deadline_s: float = 3.0
    max_segments: int = 3
    min_segment_s: float = 3.0

    @classmethod
    def from_rubric(cls, rubric: dict[str, Any] | Path | str = DEFAULT_RUBRIC_PATH) -> Gates:
        if not isinstance(rubric, dict):
            rubric = yaml.safe_load(Path(rubric).read_text(encoding="utf-8")) or {}
        cfg = rubric.get("gates") or {}
        return cls(
            min_duration_s=float(cfg.get("min_duration_s", 20.0)),
            max_duration_s=float(cfg.get("max_duration_s", 60.0)),
            hook_deadline_s=float(cfg.get("hook_deadline_s", 3.0)),
            max_segments=int(cfg.get("max_segments", 3)),
            min_segment_s=float(cfg.get("min_segment_s", 3.0)),
        )


@dataclass(slots=True)
class Segment:
    """One continuous stretch, resolved from block indices to seconds."""

    start_block: int
    end_block: int
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return round(self.end_s - self.start_s, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_block": self.start_block,
            "end_block": self.end_block,
            "start": fmt_timestamp(self.start_s),
            "end": fmt_timestamp(self.end_s),
            "start_s": round(self.start_s, 2),
            "end_s": round(self.end_s, 2),
            "duration_s": self.duration_s,
        }


@dataclass(slots=True)
class GateFailure:
    """Why a candidate was thrown out, with the number that did it."""

    gate: str
    detail: str

    def __str__(self) -> str:
        return f"{self.gate}: {self.detail}"


@dataclass(slots=True)
class GateReport:
    """The verdict on one candidate."""

    ok: bool
    segments: list[Segment] = field(default_factory=list)
    failures: list[GateFailure] = field(default_factory=list)
    duration_s: float = 0.0
    hook_block: int | None = None  # the block that satisfied the 3s gate
    hook_offset_s: float | None = None  # how far into the promo it starts

    @property
    def gates_failed(self) -> list[str]:
        return [f.gate for f in self.failures]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.ok,
            "duration_s": round(self.duration_s, 2),
            "segments": [s.to_dict() for s in self.segments],
            "hook_block": self.hook_block,
            "hook_offset_s": self.hook_offset_s,
            "failures": [{"gate": f.gate, "detail": f.detail} for f in self.failures],
        }


def fmt_timestamp(seconds: float) -> str:
    """``MM:SS.ss`` - the same format the input pack uses."""
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{rest:05.2f}"


def resolve_segments(
    episode: Episode, pairs: list[tuple[int, int]]
) -> tuple[list[Segment], list[GateFailure]]:
    """Turn model-returned block index pairs into timed segments.

    Hard rule 1 lives here: the only route from a model's answer to a
    timestamp runs through the parsed block table.
    """
    segments: list[Segment] = []
    failures: list[GateFailure] = []
    last = len(episode.blocks) - 1

    for i, (start_block, end_block) in enumerate(pairs):
        if not (0 <= start_block <= last and 0 <= end_block <= last):
            failures.append(
                GateFailure(
                    "block_out_of_range",
                    f"segment {i + 1} is ({start_block}, {end_block}); "
                    f"episode {episode.number} has blocks 0..{last}",
                )
            )
            continue
        if end_block < start_block:
            failures.append(
                GateFailure(
                    "segment_inverted",
                    f"segment {i + 1} ends at block {end_block} "
                    f"before it starts at {start_block}",
                )
            )
            continue
        start_s, end_s = episode.span_seconds(start_block, end_block)
        segments.append(Segment(start_block, end_block, start_s, end_s))

    return segments, failures


def find_hook(
    episode: Episode, first: Segment, deadline_s: float
) -> tuple[int, float] | None:
    """The 3-second hook check. Returns (block index, offset) or None.

    A DIALOGUE or ACTION block must *start* within ``deadline_s`` of the
    promo's start. CAMERA and SOUND FX never qualify: a camera direction is
    not something a viewer hears or sees as a beat.
    """
    for block in episode.blocks[first.start_block : first.end_block + 1]:
        if not block.is_content:
            continue
        offset = round(block.start_s - first.start_s, 2)
        if offset <= deadline_s:
            return block.index, max(0.0, offset)
    return None


def check(
    episode: Episode,
    pairs: list[tuple[int, int]],
    gates: Gates,
) -> GateReport:
    """Run every gate against one candidate. Collects *all* failures.

    Deliberately does not short-circuit: knowing a candidate failed both the
    duration gate and the hook gate is more useful than knowing it failed the
    first one checked.
    """
    report = GateReport(ok=False)

    if not pairs:
        report.failures.append(GateFailure("no_segments", "candidate has no segments"))
        return report

    if len(pairs) > gates.max_segments:
        report.failures.append(
            GateFailure(
                "too_many_segments",
                f"{len(pairs)} segments, maximum is {gates.max_segments}",
            )
        )

    segments, failures = resolve_segments(episode, pairs)
    report.segments = segments
    report.failures.extend(failures)

    if not segments:
        return report

    # Segments must be in order and must not overlap: "ordered segment
    # timestamps" in the brief means a viewer watches them back to back.
    for prev, nxt in zip(segments, segments[1:]):
        if nxt.start_block <= prev.end_block:
            report.failures.append(
                GateFailure(
                    "segments_overlap",
                    f"segment starting at block {nxt.start_block} overlaps the "
                    f"one ending at block {prev.end_block}",
                )
            )

    for i, seg in enumerate(segments, start=1):
        if seg.duration_s < gates.min_segment_s:
            report.failures.append(
                GateFailure(
                    "segment_too_short",
                    f"segment {i} is {seg.duration_s:.2f}s, "
                    f"minimum is {gates.min_segment_s:.1f}s",
                )
            )

    report.duration_s = round(sum(s.duration_s for s in segments), 2)
    if report.duration_s < gates.min_duration_s:
        report.failures.append(
            GateFailure(
                "too_short",
                f"{report.duration_s:.2f}s total, minimum is {gates.min_duration_s:.0f}s",
            )
        )
    elif report.duration_s > gates.max_duration_s:
        report.failures.append(
            GateFailure(
                "too_long",
                f"{report.duration_s:.2f}s total, maximum is {gates.max_duration_s:.0f}s",
            )
        )

    # --- the 3-second hook gate (D4) ---
    hook = find_hook(episode, segments[0], gates.hook_deadline_s)
    if hook is None:
        first = segments[0]
        opener = episode.block(first.start_block)
        report.failures.append(
            GateFailure(
                "no_hook_in_3s",
                f"no dialogue or ACTION beat starts within "
                f"{gates.hook_deadline_s:.1f}s of {fmt_timestamp(first.start_s)}; "
                f"the promo opens on {opener.kind}",
            )
        )
    else:
        report.hook_block, report.hook_offset_s = hook

    report.ok = not report.failures
    return report


def fit_to_window(
    episode: Episode,
    pairs: list[tuple[int, int]],
    gates: Gates,
) -> tuple[list[tuple[int, int]], str | None]:
    """Trim an over-long candidate into the duration window, in Python.

    **It only ever shortens.** The repair moves the end of the last segment
    *earlier*, never later, and never touches the start. A clip that comes back
    too short is returned unchanged and rejected by the `too_short` gate.

    Why trimming is allowed. The model is shown each block's duration but not
    the clock, so it overshoots. Rejecting a 63-second span that becomes a good
    57-second one by dropping its final camera block throws away a real promo
    for an arithmetic reason. And cutting *earlier* than the model asked is the
    safe direction: `rank.md` says outright that "a beat too early is a much
    smaller mistake than a beat too late".

    Why lengthening is not. The brief specifies a 20-60 second clip, so a span
    under 20 seconds is not a promo that needs repairing - it is not a promo.
    Both ways of inflating one were built and measured, and both spend
    something the brief asked for:

    - **advancing the tail** (the original, D14) protected the 3-second hook by
      construction and played on past the beat the model named as its
      cliffhanger. 34 of 81 shipped promos, one of them 4.9s -> 20.5s with
      seven unscored blocks glued on after the payoff.
    - **retreating the head** kept the closing beat intact and opened the clip
      through blocks the scorer never saw, 10 of which the hook gate then had
      to reject outright.

    Neither is a repair of a near-miss; both are the construction of a
    different clip. See `notes/ACCURACY.md` #0 for the measurements and for
    what was given up by removing them.

    Returns the adjusted pairs and a note describing what moved, or the input
    and ``None`` when nothing did. Every adjustment is recorded in the output;
    this is a deterministic repair, not a silent one.
    """
    if not pairs:
        return pairs, None

    def total(ps: list[tuple[int, int]]) -> float:
        segs, failures = resolve_segments(episode, ps)
        return -1.0 if failures or not segs else sum(s.duration_s for s in segs)

    start, original_end = pairs[-1]
    duration = total(pairs)
    if duration < 0:
        return pairs, None
    if gates.min_duration_s <= duration <= gates.max_duration_s:
        return pairs, None

    if duration < gates.min_duration_s:
        # Too short is not repaired. The brief asks for a 20-60 second clip;
        # a 5-second span is not a near-miss to be nudged, and every way of
        # inflating one spends either the cliffhanger or the hook. Hand it
        # back untouched and let the `too_short` gate reject it. ACCURACY.md #0.
        return pairs, None

    # Too long: retreat the tail block by block while it stays legal.
    end = original_end
    while end > start:
        trial = pairs[:-1] + [(start, end - 1)]
        trial_duration = total(trial)
        if trial_duration < gates.min_duration_s:
            break
        end -= 1
        if trial_duration <= gates.max_duration_s:
            break

    if end == original_end:
        return pairs, None

    adjusted = pairs[:-1] + [(start, end)]
    note = (
        f"trimmed final segment from block {original_end} to {end} "
        f"({duration:.1f}s -> {total(adjusted):.1f}s)"
    )
    return adjusted, note


__all__ = [
    "DEFAULT_RUBRIC_PATH",
    "GateFailure",
    "GateReport",
    "Gates",
    "Segment",
    "check",
    "find_hook",
    "fit_to_window",
    "fmt_timestamp",
    "resolve_segments",
]
