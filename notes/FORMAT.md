# The input pack, measured

Everything here was measured off the real 50 files on 2026-11-05, not assumed.
Re-derive it with `python -I notes/stats.py` if you touch the parser.

## Shape

```
pack/I Married a Broken Soldier. He was a Duke/
  episode-001-Episode 1671703.txt
  ... through ...
  episode-050-Episode 1671752.txt
```

50 files, 636 KB total, UTF-8, LF. One series, one season.

## Per-file layout

```
EPISODE NUMBER: Episode 1
EPISODE LOGLINE: <one sentence - a free summary, use it>
CONTINUITY NOTES: <what a viewer needs to know - use it for standalone scoring>

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CATHEDRAL - DAY
Scene start: 00:00.00
Scene end: 02:18.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:04.80)
Symmetrical framing on the heavy church doors...

**LADY JULIANA (Confused, Breathless):**
Start: (00:13.50) | End: (00:14.30)
"Why?"

--- SCRIPT END ---
```

A **block** is: a `**HEADER:**` line, then a `Start: (MM:SS.ss) | End: (MM:SS.ss)`
line, then one or more body lines. That is the only structure there is, and it
is completely regular.

## Numbers

| | |
|---|---|
| Episodes | 50 |
| Total runtime | 102.7 min |
| Episode duration | min 70.5s · **median 117.8s** · max 200.8s |
| Timed blocks | **3,727** · median 73/episode (37-121) |
| Scenes per episode | 1-8, median 2 |
| Dialogue blocks | 1,487 (40%) · median 28/episode |
| **Header lines that failed to parse** | **0 / 3,727** |

Two regexes do the whole job:

```python
HDR = re.compile(r'^\*\*(.+?):\*\*\s*$')
TS  = re.compile(r'^Start:\s*\((\d+):(\d+(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d+):(\d+(?:\.\d+)?)\)')
```

Timestamps are **per-episode**, starting at 00:00, format `MM:SS.ss`.

## Block kinds - only three are technical

| Count | Kind | |
|---|---|---|
| 1,754 | `CAMERA` | **47% of all blocks, and not content** |
| 372 | `ACTION` | physical beats, often the real hook |
| 114 | `SOUND FX` | |
| 1,487 | 64 distinct speaker names | dialogue, always in `"quotes"` |

Dialogue headers carry a parenthetical mood: `**LADY JULIANA (Confused, Breathless):**`.
Split on `(` to get the speaker; keep the mood, it is a free emotion signal.

**Nearly half the script is camera directions.** A promo span chosen by text
volume will be mostly camera language, which communicates nothing to a viewer.
Weight dialogue and ACTION; treat CAMERA as context, not substance. The
3-second hook gate should fire on a dialogue or ACTION block, never a CAMERA one.

## Speaker names are not normalized

Same character, different labels:

| Character | Labels seen |
|---|---|
| Juliana | `JULIANA` (352), `LADY JULIANA` (110) |
| Catherine | `CATHERINE` (187), `LADY CATHERINE` (9) |
| Clarissa | `CLARISSA` (17), `LADY CLARISSA` (11) |
| Gerald | `GERALD` (32), `THE FORMER GROOM` (16) |
| the stranger | `MYSTERIOUS BEARDED MAN` (28), `THE BEARDED STRANGER` (15), `SCARRED BEARDED MAN` (1) |
| the matriarch | `MATRIARCH` (8), `NOBLE MATRIARCH` (11) |

An alias map is a ~15-line dict. It matters for the standalone axis: a promo
that introduces someone as "the former groom" reads differently from one that
says "Gerald".

## The fact that should shape the whole approach

**A median episode is 118 seconds. A promo is 20-60 seconds.**

So a promo is **17% to 50% of an entire episode** - not a needle in a haystack.
Finding *a* workable span is easy; nearly any contiguous 40 seconds of a
microdrama episode contains a confrontation. All the difficulty is in
**choosing** between spans and in **where exactly you cut**.

That is the opposite of a podcast clipper, where 95% of a 2-hour recording is
unusable and recall is the hard part. Say so in the write-up - it is the
framing most submissions will get wrong, because "screenplay" suggests length.

Corollary: the whole season is ~160K tokens and fits in one Gemini context, so
cross-episode ranking is genuinely cheap, not an aspiration.
