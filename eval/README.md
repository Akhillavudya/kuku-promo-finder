# The eval set - do this BEFORE you run the tool

This is the highest-value hour in the assignment. The brief asks, in its own
words, where your tool picks badly. The only non-hand-waving answer is a set of
promos *you* chose, written down before the tool existed.

**Hard ordering rule: label first, run second.** If you label afterwards you
are not evaluating, you are justifying - and it reads that way.

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

## Protocol

For each episode, in order:

1. Read the whole episode. Not skim - read it.
2. **Before looking at any block timestamps**, decide in plain words what the
   best promo is. One sentence.
3. Now open the file and find the block indices and timestamps for it.
4. Fill in one object in `labels.json` (copy `labels.template.json`).
5. Write what you *rejected* and why - the `rejected` field. This is the part
   that makes the eval useful: if the tool picks the thing you consciously
   rejected, you learn something specific about the rubric rather than just
   "it was wrong".

Budget 10-12 minutes per episode. Do not optimise this step.

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
