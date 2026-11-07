"""Tool output vs the hand-labelled eval set. The honest-failures report.

D7, and the only non-hand-waving answer to the brief's "where does your tool
pick badly". Reads `eval/labels.json` - written *before* the tool was ever
run - and `outputs/promos.json`, and reports the four measures from
`eval/README.md`:

  overlap                 seconds of intersection / seconds of union
  hook agreement          did it open on the same beat you did
  cliffhanger agreement   did it cut at the same unresolved moment
  rejected-candidate hits did it ship something you consciously rejected

Overlap is the weak measure: two genuinely good promos of the same scene can
barely overlap. Hook and cliffhanger agreement are the real ones, because
those are the two things the brief actually specifies.

This module **refuses to run** if `labels.json` says the tool had already been
run when the labels were written. Labelling after the fact is not an eval, and
a flag in a file is the only thing standing between the two.

    python -m promo.compare
    python -m promo.compare --tolerance 3.0
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from promo import labels as labels_mod
from promo.parse import DEFAULT_PACK, load_season
from promo.score import rank_key

DEFAULT_LABELS = Path("eval/labels.json")
DEFAULT_PROMOS = Path("outputs/promos.json")

#: Seconds of slack allowed when asking "did it start on the same beat".
#: 2.0s is roughly one line of dialogue: inside that, two editors would call
#: it the same cut point.
DEFAULT_TOLERANCE_S = 2.0

#: A tool promo overlapping a span the human explicitly rejected by at least
#: this much counts as a rejected-candidate hit.
REJECT_HIT_OVERLAP = 0.50


class LabelOrderError(RuntimeError):
    """The labels were written after the tool ran. See D7."""


@dataclass(slots=True)
class EpisodeResult:
    episode: int
    overlap: float | None = None
    hook_agree: bool | None = None
    cliff_agree: bool | None = None
    hook_delta_s: float | None = None
    cliff_delta_s: float | None = None
    rejected_hits: list[str] = field(default_factory=list)
    tool_declined: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "overlap": None if self.overlap is None else round(self.overlap, 3),
            "hook_agreement": self.hook_agree,
            "cliffhanger_agreement": self.cliff_agree,
            "hook_delta_s": self.hook_delta_s,
            "cliffhanger_delta_s": self.cliff_delta_s,
            "rejected_candidate_hits": self.rejected_hits,
            "tool_declined": self.tool_declined,
            "note": self.note,
        }


def _spans(segments: list[dict[str, Any]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for seg in segments or []:
        start, end = seg.get("start_s"), seg.get("end_s")
        if start is None or end is None:
            continue
        out.append((float(start), float(end)))
    return sorted(out)


def iou(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Intersection over union, in seconds."""
    if not a or not b:
        return 0.0
    inter = sum(
        max(0.0, min(ae, be) - max(as_, bs)) for as_, ae in a for bs, be in b
    )
    total_a = sum(e - s for s, e in a)
    total_b = sum(e - s for s, e in b)
    union = total_a + total_b - inter
    return inter / union if union > 0 else 0.0


def load_labels(path: Path | str = DEFAULT_LABELS) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Copy eval/labels.template.json to it and fill it "
            "in BEFORE running the tool - that ordering is the point (D7)."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("tool_had_been_run"):
        raise LabelOrderError(
            f"{path} has tool_had_been_run: true. These labels were written after "
            "the tool ran, which makes them a rationalisation rather than an "
            "eval. Report that honestly instead of scoring against them."
        )
    return data


def compare(
    labels: dict[str, Any],
    promos: list[dict[str, Any]],
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> dict[str, Any]:
    """Run all four measures over the labelled episodes."""
    by_episode: dict[int, list[dict[str, Any]]] = {}
    for promo in promos:
        by_episode.setdefault(int(promo["episode"]), []).append(promo)

    results: list[EpisodeResult] = []

    for label in labels.get("labels", []):
        number = int(label["episode"])
        result = EpisodeResult(episode=number)
        human = _spans(label.get("segments", []))

        if not human:
            result.note = "label has no segments - skipped"
            results.append(result)
            continue

        picks = sorted(by_episode.get(number, []), key=rank_key)
        if not picks:
            result.tool_declined = True
            result.note = "tool produced no promo for this episode"
            results.append(result)
            continue

        # Compare against the tool's *top* pick for the episode. Comparing
        # against its best-matching pick would flatter it: an editor reads
        # the ranking from the top.
        best = picks[0]
        tool = _spans(best.get("segments", []))

        result.overlap = iou(human, tool)
        result.hook_delta_s = round(tool[0][0] - human[0][0], 2)
        result.cliff_delta_s = round(tool[-1][1] - human[-1][1], 2)
        result.hook_agree = abs(result.hook_delta_s) <= tolerance_s
        result.cliff_agree = abs(result.cliff_delta_s) <= tolerance_s

        for rejected in label.get("rejected", []):
            spans = _spans(rejected.get("segments", []))
            if not spans:
                continue  # no block indices recorded - not comparable
            for pick in picks:
                if iou(spans, _spans(pick.get("segments", []))) >= REJECT_HIT_OVERLAP:
                    result.rejected_hits.append(
                        f"{pick['id']}: {rejected.get('what', '(unnamed)')}"
                    )
                    break

        results.append(result)

    scored = [r for r in results if r.overlap is not None]
    n = len(scored)
    summary = {
        "labelled_episodes": len(results),
        "comparable_episodes": n,
        "tool_declined_on": [r.episode for r in results if r.tool_declined],
        "tolerance_s": tolerance_s,
        "mean_overlap": round(sum(r.overlap or 0 for r in scored) / n, 3) if n else None,
        "hook_agreement": f"{sum(1 for r in scored if r.hook_agree)}/{n}" if n else "0/0",
        "cliffhanger_agreement": (
            f"{sum(1 for r in scored if r.cliff_agree)}/{n}" if n else "0/0"
        ),
        "rejected_candidate_hits": sum(len(r.rejected_hits) for r in results),
        "mean_hook_delta_s": (
            round(sum(r.hook_delta_s or 0 for r in scored) / n, 2) if n else None
        ),
        "mean_cliffhanger_delta_s": (
            round(sum(r.cliff_delta_s or 0 for r in scored) / n, 2) if n else None
        ),
    }
    return {"summary": summary, "episodes": [r.to_dict() for r in results]}


def render(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Tool vs hand labels",
        "",
        f"Labels written before the tool was run (D7). "
        f"Agreement tolerance +/-{s['tolerance_s']}s.",
        "",
        f"- **Hook agreement:** {s['hook_agreement']}",
        f"- **Cliffhanger agreement:** {s['cliffhanger_agreement']}",
        f"- **Mean overlap (IoU):** {s['mean_overlap']}",
        f"- **Rejected-candidate hits:** {s['rejected_candidate_hits']}",
        f"- **Tool declined on:** {s['tool_declined_on'] or 'none'}",
        f"- Mean hook delta: {s['mean_hook_delta_s']}s "
        f"(positive = tool starts later than the human)",
        f"- Mean cliffhanger delta: {s['mean_cliffhanger_delta_s']}s",
        "",
        "| Ep | Overlap | Hook | start delta | Cliff | end delta | Rejected hits |",
        "|----|---------|------|-------------|-------|-----------|---------------|",
    ]
    def yesno(value: bool | None) -> str:
        return "-" if value is None else ("yes" if value else "no")

    def num(value: float | None, places: int = 2) -> str:
        return "-" if value is None else f"{value:.{places}f}"

    for ep in report["episodes"]:
        cells = [
            str(ep["episode"]),
            num(ep["overlap"]),
            yesno(ep["hook_agreement"]),
            num(ep["hook_delta_s"], 1),
            yesno(ep["cliffhanger_agreement"]),
            num(ep["cliffhanger_delta_s"], 1),
            str(len(ep["rejected_candidate_hits"])),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    declined = [ep for ep in report["episodes"] if ep["tool_declined"]]
    if declined:
        lines += ["", "Declined (no promo produced): " + ", ".join(
            f"ep{ep['episode']}" for ep in declined)]

    hits = [h for ep in report["episodes"] for h in ep["rejected_candidate_hits"]]
    if hits:
        lines += ["", "## Picked something the human rejected", ""]
        lines += [f"- {h}" for h in hits]

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare tool output with hand labels.")
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--promos", default=str(DEFAULT_PROMOS))
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_S)
    ap.add_argument("--out", default="outputs/eval_report.md")
    ap.add_argument("--pack", default=str(DEFAULT_PACK))
    args = ap.parse_args(argv)

    try:
        labels = load_labels(args.labels)
    except (FileNotFoundError, LabelOrderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Resolve block indices to seconds before comparing anything. `_spans`
    # reads `start_s`/`end_s` and nothing else, so a label written in block
    # indices - the form the whole project insists on - would otherwise
    # resolve to an empty span and be *skipped*, printing a clean report that
    # measured nothing. Refusing is the point: a silently-zero measure looks
    # like evidence. See `promo/labels.py` and D24.
    episodes = {e.number: e for e in load_season(args.pack)}
    problems = labels_mod.resolve(labels, episodes)
    fatal = [p for p in problems if p.fatal]
    if fatal:
        print("ERROR: these labels cannot be compared:", file=sys.stderr)
        for problem in fatal:
            print(problem, file=sys.stderr)
        print(
            "\nRun `python -m promo.labels` for the full check, and `--write` "
            "to fill in the resolved seconds.",
            file=sys.stderr,
        )
        return 2

    promos_path = Path(args.promos)
    if not promos_path.is_file():
        print(f"ERROR: {promos_path} not found - run the tool first.", file=sys.stderr)
        return 2
    promos = json.loads(promos_path.read_text(encoding="utf-8")).get("promos", [])

    report = compare(labels, promos, tolerance_s=args.tolerance)
    text = render(report)
    print(text)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {out} and {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
