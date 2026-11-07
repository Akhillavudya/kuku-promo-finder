"""D27a guards: the candidates prompt shows a clock, and nothing else changed.

Four assertions, each one load-bearing for a different part of D27:

1. the candidates rendering really does carry the absolute clock;
2. the answer schema still cannot express a timestamp, which is the
   *structural* reason showing one is safe rather than merely argued;
3. the prompt carries no pack-specific calibration constant, the shape of
   claim that caused the defect (ACCURACY.md #1);
4. the **scoring** prompt is unchanged, so the re-run moves one variable.

    python -m pytest tests/test_prompt_clock.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from promo import gates as gate_mod  # noqa: E402
from promo import run as run_mod  # noqa: E402
from promo.parse import Block  # noqa: E402
from promo.run import Candidate, load_prompt  # noqa: E402
from promo.schemas import SEGMENT  # noqa: E402

#: `[34] 00:42.50-00:44.60 ` - the clock, immediately after the index.
CLOCK_LINE = re.compile(r"^\[\d+\] \d\d:\d\d\.\d\d-\d\d:\d\d\.\d\d ")

#: Any MM:SS.ss anywhere in a string.
ANY_STAMP = re.compile(r"\d\d:\d\d\.\d\d")


def _blocks() -> list[Block]:
    """A dialogue block and a CAMERA block, hand-built - no pack needed."""
    return [
        Block(
            index=34,
            kind="DIALOGUE",
            start_s=42.5,
            end_s=44.6,
            text='"Gerald is waiting for me."',
            speaker="Juliana",
            mood="Desperate",
        ),
        Block(
            index=35,
            kind="ACTION",
            start_s=44.6,
            end_s=48.0,
            text="Gerald pulls his hand away.",
        ),
        Block(
            index=36,
            kind="CAMERA",
            start_s=48.0,
            end_s=50.0,
            text="Close-up on Juliana's face.",
        ),
    ]


def test_rendered_blocks_carry_the_clock() -> None:
    for block in _blocks():
        line = block.as_line()
        assert CLOCK_LINE.match(line), f"{block.kind} block has no clock: {line!r}"
        # The per-block duration survives alongside it: it is still what tells
        # the model a 2.1s line is a short one.
        assert f"({block.duration_s:.1f}s)" in line

    dialogue = _blocks()[0]
    assert dialogue.as_line() == (
        '[34] 00:42.50-00:44.60 (2.1s) Juliana (Desperate): "Gerald is waiting for me."'
    )
    # And it is a parameter, not unconditional.
    assert not ANY_STAMP.search(dialogue.as_line(show_clock=False))


def test_the_schema_still_cannot_express_a_timestamp() -> None:
    """The structural half of D27a. If this fails, showing a clock is unsafe.

    Hard rule 1 survives a model that has *seen* a clock only because there is
    nowhere in the answer to put one. Anyone adding a seconds field to SEGMENT
    breaks that argument, and must break this test first.
    """
    assert set(SEGMENT["properties"]) == {"start_block", "end_block"}
    for name, spec in SEGMENT["properties"].items():
        assert spec["type"] == "integer", f"{name} is not an integer"
    assert sorted(SEGMENT["required"]) == ["end_block", "start_block"]


def test_the_prompt_states_no_calibration_constant() -> None:
    """No "a total of X lands about Y real seconds" may come back.

    That sentence shape is the defect: it was measured on a pre-D22 sweep, it
    went stale when D22 changed which blocks may end a span, and it could
    never have transferred to a pasted episode from another show.
    """
    prompt = load_prompt("candidates")
    for banned in ("about 36", "about 49", "lands the finished clip"):
        assert banned not in prompt, f"stale calibration constant back: {banned!r}"
    # The replacement must actually be there.
    assert "Aim for 35 to 45 seconds" in prompt
    assert "Do not add up the durations in brackets" in prompt


def test_the_scoring_prompt_has_no_clock() -> None:
    """The §3.1 trap: recall gets the clock, ranking does not.

    The scoring tier's error bar is already +/-0.75 weighted points
    (ACCURACY.md #3). Changing its input in the same run as the candidates
    prompt would mean the re-run measured two things at once.
    """
    # `candidate_card` slices `episode.blocks[start_block : end_block + 1]`,
    # so a block's index has to be its position in the list.
    blocks = _blocks()
    for position, block in enumerate(blocks):
        block.index = position

    class FakeEpisode:
        number = 7
        duration_s = 120.0

        def __init__(self) -> None:
            self.blocks = blocks

    candidate = Candidate(
        id="ep07-c1",
        episode=7,
        segments=[
            gate_mod.Segment(start_block=0, end_block=2, start_s=42.5, end_s=48.0)
        ],
        hook="Gerald pulls his hand away",
        cliffhanger="Does she go through with it?",
        why="A stranger wants to know if she is left at the altar.",
        needs_to_know="",
        duration_s=5.5,
    )

    card = run_mod.candidate_card(candidate, FakeEpisode())  # type: ignore[arg-type]
    assert not ANY_STAMP.search(card), f"a clock leaked into the scoring card:\n{card}"
    # It is still the right card, not an empty one.
    assert "Gerald pulls his hand away." in card
    assert "Juliana (Desperate)" in card
