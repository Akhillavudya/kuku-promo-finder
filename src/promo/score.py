"""The weighted sum, computed in Python from the model's raw axis scores.

Hard rule 4: **keep every raw per-axis score.** A weighted total alone tells
you the tool picked badly; the four numbers behind it tell you *which axis*
it misjudged, which is the difference between "it was wrong" and "it
systematically overrates hooks that open on a shout". The eval section of the
write-up is built on that distinction.

The model never sees the weights and never returns a total (D10a). That keeps
the weights tunable against the hand-labelled eval set without touching a
prompt, and it keeps the scoring honest: a model asked for an overall score
anchors on its own first impression and reverse-engineers the axes to match.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from promo.schemas import AXES

DEFAULT_RUBRIC_PATH = Path("config/rubric.yaml")

#: Scores outside this range are clamped rather than rejected - a model that
#: returns 11 meant "the top", and failing the whole episode over it is worse.
SCORE_MIN, SCORE_MAX = 1, 10


@dataclass(slots=True)
class Rubric:
    """Weights and thresholds, from ``config/rubric.yaml``."""

    weights: dict[str, float] = field(default_factory=dict)
    min_score: float = 6.0
    #: Floor on the cliffhanger axis alone. A weighted total can hide a failed
    #: brief requirement; this cannot. See notes/ACCURACY.md #2.
    min_cliffhanger: int = 5
    max_promos_per_episode: int = 2

    @classmethod
    def load(cls, path: Path | str = DEFAULT_RUBRIC_PATH) -> Rubric:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        weights = {axis: float(raw.get("weights", {}).get(axis, 0.0)) for axis in AXES}
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"rubric weights must sum to 1.0, got {total:.3f} from {path}"
            )
        return cls(
            weights=weights,
            min_score=float(raw.get("min_score", 6.0)),
            min_cliffhanger=int(raw.get("min_cliffhanger", 5)),
            max_promos_per_episode=int(raw.get("max_promos_per_episode", 2)),
        )

    def weighted(self, axis_scores: dict[str, Any]) -> float:
        """Weighted total on the same 1-10 scale as the axes."""
        total = 0.0
        for axis, weight in self.weights.items():
            total += weight * clamp(axis_scores.get(axis))
        return round(total, 2)

    def axis_table(self, axis_scores: dict[str, Any]) -> dict[str, int]:
        """The four raw scores, cleaned but never collapsed. Rule 4."""
        return {axis: clamp(axis_scores.get(axis)) for axis in AXES}

    def consolidate(
        self, passes: list[dict[str, int]]
    ) -> tuple[dict[str, float], float, float]:
        """Average several independent scorings of the same candidate.

        Returns `(mean_axes, weighted_total, spread)`, where `spread` is the
        gap between the highest and lowest weighted total across the passes.

        Why average at all: a rank call sees a *batch*, and a batch is an
        arbitrary slice of the season. The same clip scored beside different
        neighbours came back 1.7 points apart, four times the sampling noise
        (notes/ACCURACY.md #3). Scoring each candidate in two deliberately
        dissimilar batches and averaging cuts that in half, and `spread`
        reports what is left instead of hiding it - a measured error bar on
        every number in the ranking.

        Rule 4 is not weakened by this: every pass's raw per-axis integers are
        kept on the candidate and written to the output. These means are an
        additional figure, not a replacement.
        """
        if not passes:
            return ({axis: 0.0 for axis in AXES}, 0.0, 0.0)

        mean_axes = {
            axis: round(sum(p.get(axis, SCORE_MIN) for p in passes) / len(passes), 2)
            for axis in AXES
        }
        totals = [
            round(sum(self.weights[axis] * p.get(axis, SCORE_MIN) for axis in AXES), 2)
            for p in passes
        ]
        weighted = round(
            sum(self.weights[axis] * mean_axes[axis] for axis in AXES), 2
        )
        return (mean_axes, weighted, round(max(totals) - min(totals), 2))


def clamp(value: Any) -> int:
    """Coerce a model's axis score into 1-10. Missing or junk becomes 1.

    See `missing_axes` for why that collapse is reported rather than removed.
    """
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return SCORE_MIN
    return max(SCORE_MIN, min(SCORE_MAX, number))


def missing_axes(axis_scores: Mapping[str, Any] | dict[str, Any]) -> list[str]:
    """The axes this response did not actually answer. ACCURACY.md #6.

    `clamp` turns a missing or unparseable axis into a 1, which is
    indistinguishable from a model that judged the clip a 1 - and the two mean
    opposite things. A judged 1 is information. An absent axis is a provider
    or prompt fault, and it is not harmless: `emotional_charge` carries 0.15,
    so one silent 1 moves the weighted total by up to ~1.35 and can push a
    good promo under the 6.0 floor, or a cliffhanger under its own floor, for
    a reason that was never a judgement at all.

    **Reporting rather than repairing, deliberately.** The arithmetic is left
    exactly as it was, so nothing about the ranking changes and this fix
    cannot be confused with the span fix measured alongside it. What changes
    is that the collapse is now *visible*: `run_summary.json` carries
    `n_axes_missing`, and a non-zero value there is a bug to chase in the
    provider, not a taste problem to argue about. It is the same reasoning as
    `n_hooks_unlabelled` under D19 - count the two cases apart instead of
    letting one value carry two meanings.

    Rejecting the candidate outright was the alternative and was not taken: a
    transient malformed response would then silently cost a promo, which
    trades a visible defect for an invisible one.
    """
    out: list[str] = []
    for axis in AXES:
        value = axis_scores.get(axis)
        try:
            float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.append(axis)
    return out


def _field(promo: Any, name: str, default: Any = 0) -> Any:
    """Read a field off either a Candidate object or an output dict."""
    if isinstance(promo, Mapping):
        return promo.get(name, default)
    return getattr(promo, name, default)


def rank_key(promo: Any) -> tuple[float, float, float, float]:
    """Sort key for the season-wide ranking. Highest first.

    Accepts a ``Candidate`` or a loaded ``promos.json`` record, so the demo
    can re-sort precomputed output with the identical rule the pipeline used.

    The weighted score decides it. Ties - which are common, because the axes
    are integers - break on cliffhanger, then hook, then the shorter clip,
    in that order: between two equally scored promos the one that cuts harder
    on an unresolved beat is the one to post, and a 32-second clip outperforms
    a 58-second one at equal quality.
    """
    axes = _field(promo, "scores", {}) or {}
    return (
        -float(_field(promo, "weighted_score", 0.0) or 0.0),
        -float(axes.get("cliffhanger", 0) or 0),
        -float(axes.get("hook_strength", 0) or 0),
        float(_field(promo, "duration_s", 0.0) or 0.0),
    )


__all__ = [
    "DEFAULT_RUBRIC_PATH",
    "SCORE_MAX",
    "SCORE_MIN",
    "missing_axes",
    "Rubric",
    "clamp",
    "rank_key",
]
