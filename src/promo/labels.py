"""The hand-labelled eval set: resolve block indices to seconds, then check.

**Hard rule 1, applied to the human.** The rule says the only route from an
answer to a timestamp runs through `parse.py`'s block table - the model is
never trusted to write `00:42.50`. The person labelling the eval set is no
better at that arithmetic than the model is, and has less patience for it.
So `labels.json` is written in **block indices**, exactly like the model's
answer, and this module resolves them with `Episode.span_seconds` - the same
function, on the same table, that turns the model's indices into seconds.

**Why this module exists** (`notes/MISTAKES.md`, same class as #12/D24).
`compare.py`'s `_spans` reads `start_s` and `end_s` and nothing else. A label
carrying only `start_block`/`end_block` resolved to an empty span, and the
episode was reported as *"label has no segments - skipped"*. The eval would
have run, printed a clean-looking report, and silently scored nothing - the
second time in this project that a quality measure was dead on arrival while
still looking like evidence. The first was `rejected[].segments`.

It also removes the only part of labelling that is clerical rather than
editorial. The human decides *which beat* opens the promo and *which* unresolved
moment it cuts on. Python works out that blocks 3-36 run 51.0 seconds, whether
that clears the 20-60s window, and whether a dialogue or ACTION beat lands
inside the first 3 seconds. Judgement stays with the person; arithmetic does
not.

**This does not weaken D7.** Resolution reads the screenplay's own block table
and never reads `outputs/`. Nothing here can see what the tool picked, so a
label cannot be bent towards it. `tool_had_been_run` is still the flag that
guards the ordering, and `compare.py` still refuses to run when it is true.

    python -m promo.labels                 # check labels.json, print a report
    python -m promo.labels --write         # also fill in the resolved seconds
    python -m promo.labels --template      # check the template is fillable
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from promo import gates as gate_mod
from promo.parse import DEFAULT_PACK, Episode, load_season

DEFAULT_LABELS = Path("eval/labels.json")

#: A resolved second and a hand-written one may disagree by this much before
#: it is worth reporting. Two decimal places of rounding, nothing more.
SECONDS_TOLERANCE = 0.05


@dataclass(slots=True)
class Problem:
    """One thing wrong with a label, and where."""

    episode: int
    where: str
    message: str
    fatal: bool = True

    def __str__(self) -> str:
        mark = "ERROR" if self.fatal else "note "
        return f"  {mark}  ep{self.episode:03d} {self.where}: {self.message}"


def _resolve_segment(
    episode: Episode, seg: dict[str, Any], where: str, problems: list[Problem]
) -> bool:
    """Fill ``start_s``/``end_s`` from the block indices. True if resolved."""
    start_block, end_block = seg.get("start_block"), seg.get("end_block")

    if start_block is None or end_block is None:
        if seg.get("start_s") is not None and seg.get("end_s") is not None:
            # Seconds without indices: usable, but it skipped the block table,
            # which is the one path this project trusts.
            problems.append(
                Problem(
                    episode.number,
                    where,
                    "has seconds but no block indices - left as written, but "
                    "block indices are the checkable form",
                    fatal=False,
                )
            )
            return True
        problems.append(
            Problem(episode.number, where, "is empty - no block indices filled in")
        )
        return False

    last = len(episode.blocks) - 1
    if not (0 <= int(start_block) <= last and 0 <= int(end_block) <= last):
        problems.append(
            Problem(
                episode.number,
                where,
                f"blocks ({start_block}, {end_block}) are outside 0..{last}",
            )
        )
        return False
    if int(end_block) < int(start_block):
        problems.append(
            Problem(
                episode.number,
                where,
                f"end_block {end_block} comes before start_block {start_block}",
            )
        )
        return False

    start_s, end_s = episode.span_seconds(int(start_block), int(end_block))

    for key, resolved in (("start_s", start_s), ("end_s", end_s)):
        written = seg.get(key)
        if written is not None and abs(float(written) - resolved) > SECONDS_TOLERANCE:
            problems.append(
                Problem(
                    episode.number,
                    where,
                    f"{key} was written as {float(written):.2f} but blocks "
                    f"{start_block}-{end_block} resolve to {resolved:.2f} - "
                    "the block table wins (hard rule 1)",
                    fatal=False,
                )
            )
        seg[key] = round(resolved, 2)

    return True


def resolve(
    labels: dict[str, Any], episodes: dict[int, Episode]
) -> list[Problem]:
    """Resolve every segment in ``labels`` in place. Returns what is wrong.

    Mutates ``labels``: every segment that carries block indices gets
    ``start_s``/``end_s``, and every top-level label gets ``duration_s``.
    """
    problems: list[Problem] = []

    for label in labels.get("labels", []):
        try:
            number = int(label["episode"])
        except (KeyError, TypeError, ValueError):
            problems.append(Problem(0, "label", "has no usable `episode` number"))
            continue

        episode = episodes.get(number)
        if episode is None:
            problems.append(
                Problem(number, "label", "no such episode in the pack")
            )
            continue

        pick = label.get("segments") or []
        resolved = [
            seg
            for i, seg in enumerate(pick, start=1)
            if _resolve_segment(episode, seg, f"segments[{i}]", problems)
        ]

        for j, rejected in enumerate(label.get("rejected") or [], start=1):
            for i, seg in enumerate(rejected.get("segments") or [], start=1):
                _resolve_segment(
                    episode, seg, f"rejected[{j}].segments[{i}]", problems
                )

        if not resolved:
            problems.append(
                Problem(
                    number,
                    "segments",
                    "no segment resolved, so compare.py will skip this episode "
                    "entirely - this is the measure silently reporting nothing",
                )
            )
            continue

        label["duration_s"] = round(
            sum(seg["end_s"] - seg["start_s"] for seg in resolved), 2
        )

    return problems


def check_against_gates(
    labels: dict[str, Any], episodes: dict[int, Episode], gates: gate_mod.Gates
) -> list[Problem]:
    """Run the tool's own gates over the human's picks.

    Not to reject them - a human label is ground truth and outranks the gates.
    It is to tell the labeller *now* that their 14-second pick can never be
    matched by a tool that is forbidden to return anything under 20 seconds,
    so they can widen it while the episode is still in their head rather than
    discover it in the report.
    """
    problems: list[Problem] = []

    for label in labels.get("labels", []):
        number = int(label.get("episode", 0))
        episode = episodes.get(number)
        if episode is None:
            continue
        pairs = [
            (int(s["start_block"]), int(s["end_block"]))
            for s in label.get("segments") or []
            if s.get("start_block") is not None and s.get("end_block") is not None
        ]
        if not pairs:
            continue

        report = gate_mod.check(episode, pairs, gates)
        for failure in report.failures:
            problems.append(
                Problem(
                    number,
                    f"your pick ({failure.gate})",
                    f"{failure.detail} - the tool can never return this span, "
                    "so it will score as a disagreement",
                    fatal=False,
                )
            )
        if report.ok:
            problems.append(
                Problem(
                    number,
                    "your pick",
                    f"{report.duration_s:.1f}s, hook at block "
                    f"{report.hook_block} (+{report.hook_offset_s:.1f}s) - legal",
                    fatal=False,
                )
            )

    return problems


def blanks(labels: dict[str, Any]) -> list[Problem]:
    """Prose fields left empty or still holding the template's instructions."""
    problems: list[Problem] = []
    placeholder_words = ("the line or beat", "the unresolved thing", "one line - why",
                         "the other span you considered")

    for label in labels.get("labels", []):
        number = int(label.get("episode", 0))
        for field in ("in_one_sentence", "hook", "cliffhanger", "why"):
            value = str(label.get(field) or "").strip()
            if not value:
                problems.append(
                    Problem(number, field, "is empty", fatal=False)
                )
            elif any(word in value.lower() for word in placeholder_words):
                problems.append(
                    Problem(
                        number,
                        field,
                        "still holds the template's instruction text",
                        fatal=False,
                    )
                )
        if str(label.get("confidence") or "").strip() not in {"high", "medium", "low"}:
            problems.append(
                Problem(
                    number,
                    "confidence",
                    "should be exactly one of high / medium / low",
                    fatal=False,
                )
            )
    return problems


def render(
    labels: dict[str, Any], problems: list[Problem], *, path: Path
) -> str:
    """The report printed to the labeller."""
    fatal = [p for p in problems if p.fatal]
    notes = [p for p in problems if not p.fatal]
    n = len(labels.get("labels", []))
    resolved = sum(1 for l in labels.get("labels", []) if l.get("duration_s"))

    lines = [
        f"{path}: {n} labelled episodes, {resolved} with a resolved span",
        "",
    ]
    if labels.get("tool_had_been_run"):
        lines += [
            "  ERROR  tool_had_been_run is true. compare.py will refuse these "
            "labels (D7).",
            "",
        ]
    if fatal:
        lines.append(f"{len(fatal)} problem(s) that would break the report:")
        lines += [str(p) for p in fatal]
        lines.append("")
    if notes:
        lines.append(f"{len(notes)} note(s):")
        lines += [str(p) for p in notes]
        lines.append("")
    if not fatal and not labels.get("tool_had_been_run"):
        lines.append("No blocking problems. These labels will produce a real report.")
    else:
        lines.append("Fix the errors above before trusting the eval report.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Resolve and check the hand-labelled eval set."
    )
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--pack", default=str(DEFAULT_PACK))
    ap.add_argument(
        "--write",
        action="store_true",
        help="write the resolved start_s/end_s back into the labels file",
    )
    ap.add_argument(
        "--rubric", default=str(gate_mod.DEFAULT_RUBRIC_PATH),
    )
    args = ap.parse_args(argv)

    path = Path(args.labels)
    if not path.is_file():
        print(
            f"{path} not found.\n"
            f"  cp eval/labels.template.json {path}\n"
            "then fill in the block indices. Protocol: eval/README.md."
        )
        return 2

    labels = json.loads(path.read_text(encoding="utf-8"))
    episodes = {e.number: e for e in load_season(args.pack)}
    gates = gate_mod.Gates.from_rubric(Path(args.rubric))

    problems = resolve(labels, episodes)
    problems += check_against_gates(labels, episodes, gates)
    problems += blanks(labels)

    print(render(labels, problems, path=path))

    if args.write:
        path.write_text(
            json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nresolved seconds written to {path}")

    return 1 if any(p.fatal for p in problems) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DEFAULT_LABELS",
    "Problem",
    "SECONDS_TOLERANCE",
    "blanks",
    "check_against_gates",
    "render",
    "resolve",
]
