# Decision ledger

Every real choice in this project, with the trade-off exposed. **You are
making these, not Claude.** The ones marked DECIDED were settled on
2026-11-05 and the reasoning is written down so you can overturn them with
your eyes open. The ones marked OPEN are waiting on you.

Keep this file updated as you go - the Kuku brief scores "approach and
scale" and "quality checking", and a decision log with reasons *is* the
evidence for both. Paste the short version into the 2-page PDF.

---

## D1 - Where the code lives · DECIDED

A new folder with a fresh `git init`, not a clone of shorts-clipper and not a
branch of it.

**Why:** a clone brings 186 unrelated files you would immediately delete, and
it drags shorts-clipper's history along, so the PS1 commit log would open with
"Phases 1-6: the web UI, the durable queue and the supervisor". Files were
copied in by hand (`src/promo/llm/`, `config/settings.yaml`) so the borrowing
is visible and deliberate.

---

## D2 - What the LLM is allowed to return · DECIDED

**Block indices. Never timestamps.** The model returns
`{"start_block": 12, "end_block": 34}` and Python looks the times up from the
parsed block table.

**Why:** this is shorts-clipper's hard rule 2 ("the LLM never emits cut
points - it returns word *indices*") and it transfers to this domain perfectly,
with blocks standing in for words. A model asked for `00:42.50` will drift and
invent. A model asked for block 34 is either right or obviously wrong, and the
timestamps it produces are exact by construction.

**Cost of the alternative:** letting it emit seconds is maybe 20 minutes
faster to write and throws away the strongest thing you have to say about the
design.

---

## D3 - One span or several · DECIDED

Up to **3 segments**, each at least **3 seconds**. Configured in
`config/rubric.yaml` under `gates`, not hard-coded.

**Why:** the brief asks for "ordered segment start/end timestamps" - plural,
so multi-segment is invited, and real promos do cut. The cap and the floor
exist so it cannot return incoherent confetti.

---

## D4 - The 3-second hook: prompt or code · DECIDED

**Code.** A deterministic gate: a dialogue or `ACTION` block must *start*
within `gates.hook_deadline_s` (3.0s) of the promo's start, measured off the
block table. Fails the gate -> rejected, with the reason recorded. The model
does not get a vote.

**Why:** this is the single highest-value 30 minutes in the project. The brief
asks directly what you kept as code or simple rules versus what you handed to
a model, and most submissions will answer "I put it in the prompt", which is
unverifiable - the model will simply assert that it complied. Note the gate
fires on dialogue/ACTION and **never on CAMERA**: 47% of all blocks are camera
directions and they communicate nothing to a viewer.

---

## D5 - The cliffhanger axis is INVERTED from shorts-clipper · DECIDED

shorts-clipper's `rerank.system.md` says, verbatim: *"payoff - does the tension
resolve inside the clip? A setup whose answer lands after the end is a 2,
however interesting the setup."*

This assignment wants **exactly the opposite**. Unresolved at the cut is the
goal.

**Therefore: write the prompts from scratch.** Do not open the old file to
"adapt" it - the old framing leaks through in the wording even when the rule is
flipped. `config/rubric.yaml` carries this warning too.

---

## D6 - Per-episode, or season-wide · DECIDED

Two passes: **candidates** (one call per episode, 50 cheap parallel cacheable
calls) then **rank** (one season-wide pass over the shortlist).

**Why:** the brief wants promos *and* a ranking across them. This is
structurally shorts-clipper's recall -> rerank, which means the architecture
genuinely carries over and you can say so without overclaiming. Per-episode
calls are cacheable and individually re-runnable; one giant call is neither.

---

## D7 - The eval, and its ordering constraint · DECIDED, NOT YET DONE

Hand-label **5 episodes before running the tool even once.** Protocol and
template in `eval/README.md`.

**Why the ordering is not negotiable:** the brief asks point-blank where your
tool picks badly. Label afterwards and you are not evaluating, you are
rationalising - and you will know it, which means a grader will too. Labelling
first is also the only way you will notice the tool being *right in a way you
did not expect*, which is the more interesting finding.

---

## D8 - Confidentiality · DECIDED

- `pack/` and `brief/` are **gitignored and never committed.** The brief says:
  *"please don't publish or share it."*
- Outputs may quote **the hook line and the cliffhanger line only** - short
  quotes, defensible as necessary to show the work.
- Full episode text never leaves this folder, and never reaches the deployed
  demo.
- Raw outputs go in a link-visible Google Drive folder, because the brief
  requires links that open for anyone.

Say all of this in the write-up. The brief creates the tension itself -
"links must open for anyone" against "don't publish the pack" - so showing
you noticed is a point in your favour, and resolving it silently is a wasted one.

---

## D9 - Demo shape · DECIDED

Two tabs. **Tab 1 renders precomputed `outputs/*.json` with zero API calls.**
Tab 2 runs live on a pasted screenplay.

**Why:** tab 1 cannot fail in front of a grader - no quota, no cold start, no
key. Tab 2 is what you drive in the interview when they ask you to run it on
something new. Gradio on Hugging Face Spaces, free tier.

---

## D10 - OPEN · Scoring: does the model see the rubric numerically?

Two options, pick one when you write the rank prompt:

- **(a)** model returns 1-10 per axis, Python computes the weighted sum from
  `config/rubric.yaml`. Shorts-clipper does this. Weights become tunable
  without touching a prompt, and you keep the raw per-axis scores forever.
- **(b)** model returns one overall score and a reason. Simpler, one less thing
  to explain, but you cannot retune and you lose the per-axis signal.

**Recommendation: (a).** It costs nothing extra and the raw per-axis scores are
what let you say *which* axis the tool misjudges in your eval section, rather
than just "it picked badly".

---

## D11 - OPEN · What happens when an episode has no valid promo

Some of the 70-second episodes may have no 20s span that passes the hook gate.
Options: emit nothing for that episode; emit the best failing candidate
labelled with the gate it failed; or relax the gate for short episodes.

**Recommendation: emit nothing, and report the count.** "The tool declined on
4 of 50 episodes, here is why" is a *stronger* answer to the quality-checking
lens than a forced output, and it is honest. But decide it yourself and write
the reason here.

---

## D12 - OPEN · Does ranking happen within an episode, across the season, or both

The brief says rank the promos. Within-episode ranking is nearly free (you
already score every candidate). Season-wide ranking is the more interesting
artefact - "if you can only cut 10 promos for this series, cut these ten" -
and it is cheap because the season fits in one context.

**Recommendation: both, and lead with the season-wide top 10** in the write-up.
