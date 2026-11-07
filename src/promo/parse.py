"""Screenplay -> block table.

This is the foundation the whole tool stands on, because of hard rule 1: the
LLM never emits a timestamp. It returns *block indices*, and this module owns
the only mapping from an index back to seconds. If the table is right, every
timestamp in every output is exact by construction. If the table is wrong,
nothing downstream can save it - which is why the sanity check at the bottom
(`3,727 blocks across 50 files, 0 parse failures`) is an assertion and not a
comment.

The input format is completely regular; `notes/FORMAT.md` measured it off all
50 files. Two regexes do the whole job:

    **LADY JULIANA (Confused, Breathless):**     <- HDR
    Start: (00:13.50) | End: (00:14.30)          <- TS
    "Why?"                                       <- body

Run it on one episode to see the table:

    python -m promo.parse 1
    python -m promo.parse 1 --kind ACTION
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --- the two regexes from notes/FORMAT.md --------------------------------

HDR = re.compile(r"^\*\*(.+?):\*\*\s*$")
TS = re.compile(
    r"^Start:\s*\((\d+):(\d+(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d+):(\d+(?:\.\d+)?)\)"
)

SCENE = re.compile(r"^SCENE\s+(\d+)\s*$")
SCENE_HEADING = re.compile(r"^Scene heading:\s*(.+?)\s*$")
META = re.compile(r"^(EPISODE NUMBER|EPISODE LOGLINE|CONTINUITY NOTES):\s*(.*)$")
EPISODE_NO_IN_NAME = re.compile(r"episode-(\d+)")

#: The three non-dialogue header kinds. Everything else is a speaker name.
TECHNICAL_KINDS = {"CAMERA", "ACTION", "SOUND FX"}

#: Blocks a viewer actually perceives as content. CAMERA is 47% of the script
#: and communicates nothing to someone watching - it is context, not substance.
#: The 3-second hook gate keys off exactly this set (D4).
CONTENT_KINDS = {"DIALOGUE", "ACTION"}

DEFAULT_PACK = Path("pack/I Married a Broken Soldier. He was a Duke")

#: Speaker aliases. Same character, different labels - measured in FORMAT.md.
#: This matters for the standalone axis: a promo that introduces someone as
#: "the former groom" reads differently from one that says "Gerald".
ALIASES: dict[str, str] = {
    "JULIANA": "Juliana",
    "LADY JULIANA": "Juliana",
    "CATHERINE": "Catherine",
    "LADY CATHERINE": "Catherine",
    "CLARISSA": "Clarissa",
    "LADY CLARISSA": "Clarissa",
    "GERALD": "Gerald",
    "THE FORMER GROOM": "Gerald",
    "MYSTERIOUS BEARDED MAN": "The Bearded Stranger",
    "THE BEARDED STRANGER": "The Bearded Stranger",
    "SCARRED BEARDED MAN": "The Bearded Stranger",
    "MATRIARCH": "The Matriarch",
    "NOBLE MATRIARCH": "The Matriarch",
}


def _fmt(seconds: float) -> str:
    """``MM:SS.ss``. Defined above `Block` because `Block.as_line` calls it.

    Deliberately not imported from `gates.fmt_timestamp`: `gates` imports
    `parse`, so that direction would be an import cycle.
    """
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


class ParseError(Exception):
    """A header line that does not fit the format. Should never fire."""


def canonical_speaker(raw: str) -> str:
    """Map a raw header speaker onto a canonical character name."""
    key = raw.strip().upper()
    if key in ALIASES:
        return ALIASES[key]
    return raw.strip().title()


@dataclass(slots=True)
class Block:
    """One timed unit of screenplay. The atom the model points at."""

    index: int
    kind: str  # CAMERA | ACTION | SOUND FX | DIALOGUE
    start_s: float
    end_s: float
    text: str
    speaker: str | None = None  # canonical, dialogue only
    raw_speaker: str | None = None  # as written in the file
    mood: str | None = None  # the free parenthetical, e.g. "Cold, Commanding"
    scene: int = 0
    scene_heading: str = ""

    @property
    def duration_s(self) -> float:
        return round(self.end_s - self.start_s, 2)

    @property
    def is_content(self) -> bool:
        """Does a viewer perceive this? Dialogue and ACTION yes, CAMERA no."""
        return self.kind in CONTENT_KINDS

    def label(self) -> str:
        """Short human label, e.g. ``Juliana (Desperate)`` or ``ACTION``."""
        if self.kind == "DIALOGUE":
            return f"{self.speaker} ({self.mood})" if self.mood else str(self.speaker)
        return self.kind

    def as_line(
        self,
        *,
        truncate: int | None = None,
        show_duration: bool = True,
        show_clock: bool = True,
    ) -> str:
        """One-line rendering used in prompts and the CLI dump.

        Can show the block's absolute start and end time as well as its own
        duration. **D27a:** hard rule 1 governs what the model *emits*, not
        what it reads. `SEGMENT` in `schemas.py` accepts two integers and
        nothing else, so a model that has seen a clock still cannot return
        one, and `Episode.span_seconds` remains the only route from an index
        to a second.

        Showing it is what makes the length instruction exact. The previous
        version hid the clock and asked the model to infer length from a sum
        of per-block durations, which overlap - measured at a median 1.67x
        the true span (ACCURACY.md #1). An exact subtraction of two printed
        numbers replaces a proxy and a pack-specific calibration constant,
        which is also what makes it work on arbitrary pasted input.

        `show_clock=False` is not a leftover: the **scoring** prompt
        (`run.candidate_block`) deliberately keeps the old rendering, so that
        D27's re-run changes the recall stage and nothing else. Scoring is
        handed `duration_s` directly and has no use for a clock.
        """
        text = self.text
        if truncate and len(text) > truncate:
            text = text[: truncate - 1].rstrip() + "…"
        clock = f" {_fmt(self.start_s)}-{_fmt(self.end_s)}" if show_clock else ""
        stamp = f" ({self.duration_s:.1f}s)" if show_duration else ""
        return f"[{self.index}]{clock}{stamp} {self.label()}: {text}"


@dataclass(slots=True)
class Episode:
    """One parsed episode file."""

    number: int
    path: Path
    logline: str = ""
    continuity: str = ""
    blocks: list[Block] = field(default_factory=list)
    scene_headings: dict[int, str] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return max((b.end_s for b in self.blocks), default=0.0)

    @property
    def dialogue(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "DIALOGUE"]

    @property
    def speakers(self) -> list[str]:
        seen: dict[str, None] = {}
        for b in self.dialogue:
            if b.speaker:
                seen[b.speaker] = None
        return list(seen)

    def block(self, index: int) -> Block:
        """Look up by the index the model returned. Raises on out of range."""
        if not 0 <= index < len(self.blocks):
            raise IndexError(
                f"episode {self.number}: block {index} out of range "
                f"(0..{len(self.blocks) - 1})"
            )
        return self.blocks[index]

    def span_seconds(self, start_block: int, end_block: int) -> tuple[float, float]:
        """**The whole point of this module.** Indices in, exact seconds out.

        Span end is the latest end in the range rather than the last block's
        own end, because blocks overlap: a `CAMERA` directive often runs past
        the dialogue nested inside it, so `hi.end_s` is not reliably the
        maximum.

        **But only content blocks are allowed to set it** (ACCURACY.md #5).
        A `SOUND FX` bell cue or a `CAMERA` hold can be 22 seconds long, and
        letting one of those decide where the clip ends pushed the promo past
        the last beat a viewer actually perceives - past the cliffhanger the
        model named and the scorer judged.

        This makes the rule consistent with D4, which is the argument for it:
        **content blocks decide the hook and the end; `CAMERA` and `SOUND FX`
        decide neither.** It was incoherent for `SOUND FX` to be unable to
        satisfy the 3-second hook gate while still being able to extend the
        span, and that was the only remaining path by which a shipped promo
        could run past its own closing beat.

        If a range contains no content block at all the old behaviour stands -
        every block counts - because such a span has no perceivable end to
        prefer and the gates will reject it on the hook rule anyway.
        """
        if end_block < start_block:
            raise ValueError(f"end_block {end_block} precedes start_block {start_block}")
        lo = self.block(start_block)
        in_range = self.blocks[start_block : end_block + 1]
        content = [b for b in in_range if b.is_content]
        return (lo.start_s, max(b.end_s for b in (content or in_range)))

    def render(
        self,
        *,
        truncate_camera: int | None = 110,
        include_camera: bool = True,
    ) -> str:
        """The block listing handed to the model. Indices plus a clock.

        The model points at blocks by index and never writes a time (hard
        rule 1); it *reads* each block's start and end so that segment length
        is one subtraction rather than a guess. See `Block.as_line` and D27a.

        CAMERA blocks are included but truncated: they carry the visual beat
        (a slap, a reveal) that often *is* the hook, but at full length they
        would be half the prompt for a signal the viewer never hears.
        """
        out: list[str] = []
        current_scene = -1
        for b in self.blocks:
            if b.kind == "CAMERA" and not include_camera:
                continue
            if b.scene != current_scene:
                current_scene = b.scene
                heading = self.scene_headings.get(b.scene, "")
                out.append(f"\n--- SCENE {b.scene:02d}: {heading} ---")
            out.append(
                b.as_line(truncate=truncate_camera if b.kind == "CAMERA" else None)
            )
        return "\n".join(out).strip()

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "file": self.path.name,
            "logline": self.logline,
            "continuity": self.continuity,
            "duration_s": self.duration_s,
            "n_blocks": len(self.blocks),
            "blocks": [asdict(b) for b in self.blocks],
        }


def _to_seconds(minutes: str, seconds: str) -> float:
    return round(int(minutes) * 60 + float(seconds), 2)


def parse_episode(path: Path | str) -> Episode:
    """Parse one episode file into an ordered block table."""
    path = Path(path)
    match = EPISODE_NO_IN_NAME.search(path.name)
    return parse_text(
        path.read_text(encoding="utf-8"),
        number=int(match.group(1)) if match else 0,
        path=path,
    )


def parse_text(text: str, *, number: int = 0, path: Path | str = "<pasted>") -> Episode:
    """Parse screenplay text that is not on disk - the demo's live tab.

    Same code path as :func:`parse_episode`, so what the demo runs is exactly
    what the batch run runs.
    """
    lines = text.splitlines()
    episode = Episode(number=number, path=Path(path))

    scene = 0
    pending: tuple[str, str] | None = None  # (raw_header, kind) awaiting a TS line
    block: Block | None = None

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        if meta := META.match(stripped):
            key, value = meta.group(1), meta.group(2).strip()
            if key == "EPISODE NUMBER" and not episode.number:
                digits = re.search(r"(\d+)", value)
                if digits:
                    episode.number = int(digits.group(1))
            elif key == "EPISODE LOGLINE":
                episode.logline = value
            elif key == "CONTINUITY NOTES":
                episode.continuity = value
            continue

        if scene_match := SCENE.match(stripped):
            scene = int(scene_match.group(1))
            block = None
            continue

        if heading := SCENE_HEADING.match(stripped):
            episode.scene_headings[scene] = heading.group(1)
            continue

        if header := HDR.match(stripped):
            raw = header.group(1).strip()
            kind = raw if raw in TECHNICAL_KINDS else "DIALOGUE"
            pending = (raw, kind)
            block = None
            continue

        if ts := TS.match(stripped):
            if pending is None:
                raise ParseError(
                    f"{episode.path.name}:{lineno}: timestamps with no header above"
                )
            raw, kind = pending
            pending = None

            raw_speaker: str | None = None
            mood: str | None = None
            speaker: str | None = None
            if kind == "DIALOGUE":
                # "LADY JULIANA (Confused, Breathless)" -> name + free mood signal
                name, _, rest = raw.partition("(")
                raw_speaker = name.strip()
                speaker = canonical_speaker(raw_speaker)
                mood = rest.rstrip(")").strip() or None

            block = Block(
                index=len(episode.blocks),
                kind=kind,
                start_s=_to_seconds(ts.group(1), ts.group(2)),
                end_s=_to_seconds(ts.group(3), ts.group(4)),
                text="",
                speaker=speaker,
                raw_speaker=raw_speaker,
                mood=mood,
                scene=scene,
                scene_heading=episode.scene_headings.get(scene, ""),
            )
            episode.blocks.append(block)
            continue

        # Anything else is body text for the block we are inside, if any.
        if block is not None and stripped:
            block.text = f"{block.text} {stripped}".strip()

    if pending is not None:
        raise ParseError(
            f"{episode.path.name}: header {pending[0]!r} had no timestamp line"
        )

    # Scene headings can appear after the first block of a scene is created.
    for b in episode.blocks:
        if not b.scene_heading:
            b.scene_heading = episode.scene_headings.get(b.scene, "")

    return episode


def episode_paths(pack_dir: Path | str = DEFAULT_PACK) -> list[Path]:
    """Every episode file in the pack, in episode order."""
    pack_dir = Path(pack_dir)
    if not pack_dir.is_dir():
        raise FileNotFoundError(
            f"pack directory not found: {pack_dir}\n"
            "pack/ is gitignored (D8) - it must be copied in locally."
        )
    return sorted(pack_dir.glob("episode-*.txt"))


def load_season(pack_dir: Path | str = DEFAULT_PACK) -> list[Episode]:
    """Parse every episode in the pack."""
    return [parse_episode(p) for p in episode_paths(pack_dir)]


def find_episode(ref: str | int, pack_dir: Path | str = DEFAULT_PACK) -> Path:
    """Resolve ``1``, ``"001"`` or a full path to an episode file."""
    as_path = Path(str(ref))
    if as_path.is_file():
        return as_path
    number = int(ref)
    for path in episode_paths(pack_dir):
        if EPISODE_NO_IN_NAME.search(path.name) and int(
            EPISODE_NO_IN_NAME.search(path.name).group(1)  # type: ignore[union-attr]
        ) == number:
            return path
    raise FileNotFoundError(f"no episode {ref} in {pack_dir}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse one episode and dump its block table.")
    ap.add_argument("episode", nargs="?", help="episode number or path; omit to check all 50")
    ap.add_argument("--pack", default=str(DEFAULT_PACK))
    ap.add_argument("--kind", help="only show blocks of this kind, e.g. ACTION")
    ap.add_argument("--prompt", action="store_true", help="show the model's view instead")
    args = ap.parse_args(argv)

    if args.episode is None:
        season = load_season(args.pack)
        total = sum(len(e.blocks) for e in season)
        print(f"{len(season)} episodes, {total} blocks, 0 parse failures")
        print(f"expected: 50 episodes, 3727 blocks (notes/FORMAT.md)")
        ok = len(season) == 50 and total == 3727
        print("MATCH" if ok else "MISMATCH - the parser is wrong, not the data")
        return 0 if ok else 1

    ep = parse_episode(find_episode(args.episode, args.pack))
    print(f"Episode {ep.number}  ({ep.path.name})")
    print(f"  duration {_fmt(ep.duration_s)}  blocks {len(ep.blocks)}  "
          f"dialogue {len(ep.dialogue)}  speakers {', '.join(ep.speakers)}")
    print(f"  logline: {ep.logline}")
    print()

    if args.prompt:
        print(ep.render())
        return 0

    for b in ep.blocks:
        if args.kind and b.kind != args.kind.upper():
            continue
        print(f"[{b.index:>3}] {_fmt(b.start_s)}-{_fmt(b.end_s)} "
              f"{b.label():<34} {b.text[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
