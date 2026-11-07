# The eval set - do this BEFORE you run the tool

> **STATUS 2026-11-07: this ordering was not kept, by the user's decision.**
> Episodes 1, 44, 36, 17, 29 were run as part of the full 50-episode run before
> any label was written, because there was no time left to label and a complete
> season output was judged worth more. See **D28** in `DECISIONS.md` for the
> decision and what it costs.
>
> **What that means for anyone reading this file now:** everything below is
> still the right method, and it is no longer available in its strong form.
> `compare.py` will refuse `labels.json` while `tool_had_been_run` is true, and
> that flag is now honestly true. If labels are written from here on they are a
> **post-hoc, non-blind** agreement check, they must be described that way
> wherever they appear, and they cannot be called ground truth. The five
> worksheets in `eval/worksheets/` are unchanged and still usable for it.


This is the highest-value hour in the assignment. The brief asks, in its own
words, where your tool picks badly. The only non-hand-waving answer is a set of
promos *you* chose, written down before the tool existed.

**The ordering rule was: label first, run second.** If you label afterwards you
are not evaluating, you are justifying - and it reads that way. It is no longer
a hard rule in `CLAUDE.md`, because it can no longer be honoured here; it is a
stated limitation instead. It is still the right ordering for anyone running
this from scratch.

## The five episodes

Chosen for a duration spread, so you find out whether the tool degrades on
short episodes (where a 60s promo is most of the runtime) or long ones.

| Episode | Duration | Why this one |
|---|---|---|
| 1 | 138s | series opener - the only episode with no prior context at all |
| 44 | 70s | shortest in the season - a 60s promo is 86% of it |
| 36 | 201s | longest - most room to choose badly |
| 17 | 119s | median |
| 29 | 117s | median, second sample |

## You do not need the video. You need the screenplay.

The tool reads transcripts and nothing else. If you labelled from video you
would be judging it against information it never had, and every disagreement
would be unreadable - was the pick wrong, or did you just see a face it could
not? **The ground truth has to be in the same medium as the input.** Labelling
from the screenplay is the correct method here, not a compromise forced by a
missing asset.

The screenplay carries everything the judgement needs: every line of dialogue
with its speaker and mood, every ACTION beat, every CAMERA direction, and exact
start and end times for all of them.

## You do not need to do any arithmetic either

Write **block indices**. Python resolves them to seconds through the same block
table that turns the model's answers into timestamps - hard rule 1, applied to
you. Leave `start_s` and `end_s` as `null`; `promo.labels` fills them in.

## Protocol

First, print the episode as a worksheet:

```bash
PYTHONPATH=src python -m promo.parse 44
```

Then, for each of the five episodes, in order:

1. Read the whole episode. Not skim - read it.
2. **Before looking at any timestamps**, decide in plain words what the best
   promo is. One sentence, into `in_one_sentence`.
3. Now find the two block indices: the block your promo **opens on** and the
   block it **cuts on**. That is `start_block` and `end_block`. Two numbers.
4. Fill in one object in `labels.json` (copy `labels.template.json`, which is
   already scaffolded with all five episodes).
5. Write what you *rejected* and why - the `rejected` field, **including its
   block indices**. This is the part that makes the eval useful: if the tool
   picks the thing you consciously rejected, you learn something specific
   about the rubric rather than just "it was wrong". A rejected span with no
   indices is invisible to the report.

Budget 10-12 minutes per episode. Do not optimise this step.

## Check your labels before you run anything

```bash
PYTHONPATH=src python -m promo.labels --write
```

This resolves your block indices to seconds, writes them back, and tells you:

- any segment you left unfilled - which would otherwise make `compare.py`
  **skip that episode silently** and report a clean-looking nothing
- any span outside the tool's own 20-60s window, or with no dialogue/ACTION
  beat in its first 3 seconds. **Your label is still ground truth** - the tool
  is the thing being measured, not you - but a 14-second pick can never be
  matched by a tool forbidden to return anything under 20, so it is worth
  knowing now rather than reading it as a disagreement later.

It exits non-zero while anything is still broken. `compare.py` runs the same
resolution and refuses to score labels it cannot resolve.

## Then, after the tool runs

Compare on four things and put the numbers in the write-up:

| Measure | What it tells you |
|---|---|
| **Overlap** | seconds of intersection ÷ seconds of union, your span vs the tool's |
| **Hook agreement** | did it open on the same beat you did? yes/no |
| **Cliffhanger agreement** | did it cut at the same unresolved moment? yes/no |
| **Rejected-candidate hits** | did it pick something you had explicitly rejected? |

Overlap is the weak measure - two good promos can barely overlap. Hook and
cliffhanger agreement are the real ones, because those are the two things the
brief actually specifies.

Expect roughly 3 of 5 to agree on the hook. If you get 5 of 5 you have
probably mislabelled; if you get 0 of 5, check the parser before blaming the
model.
