# CLAUDE.md

Guidance for working in this repo. Read `START_HERE.md` first for the plan and
the deadline, `DECISIONS.md` for why things are the way they are, and
`notes/FORMAT.md` for the measured shape of the input.

## What this is

Kuku AI Generalist Assignment, Problem 1: read a microdrama screenplay, find
20-60 second promos. Each promo needs a hook in the first 3 seconds, ends on an
unresolved cliffhanger, and makes sense to someone who has seen nothing else.
Output is episode + ordered segment timestamps + hook + cliffhanger + one line
on why it works, plus a ranking, plus an honest account of where it picks badly.

It is a 2-3 hour assignment with a 48-hour clock. **Scope discipline is being
scored.** Do not build a framework.

## Commands

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python -I notes/stats.py          # re-derive the input stats in FORMAT.md
python -m promo.parse <episode>   # (to build) parse one episode, dump blocks
python -m promo.run               # (to build) the whole season -> outputs/
python app.py                     # (to build) the Gradio demo
```

`src/` is not installed as a package yet; either add a `pyproject.toml` or run
with `PYTHONPATH=src`. Decide when you get there, don't pre-solve it.

## Hard rules

Four of these are carried over from shorts-clipper, where they were
load-bearing. They are still load-bearing.

1. **The LLM never emits timestamps.** It returns *block indices*; `parse.py`'s
   block table turns those into seconds. See D2. A model asked for `00:42.50`
   drifts and invents; a model asked for block 34 is either right or obviously
   wrong.
2. **Ask the router for a tier, never a model.** `router.complete("candidates", ...)`.
   Model IDs live only in `config/settings.yaml`. **No model string belongs in `src/`.**
3. **The 3-second hook gate is Python, not a prompt.** It fires on a dialogue or
   `ACTION` block and never on `CAMERA`. See D4 - this is the project's main
   point of difference.
4. **Keep every raw per-axis score.** Same reasoning as shorts-clipper's rule 8:
   the per-axis numbers are what let you say *which* axis the tool misjudges.
   A weighted total alone throws that away.
5. **`pack/` and `brief/` are never committed.** Kuku's content, shared for this
   assignment only. `.gitignore` covers them - do not add an exception "just to
   test CI". Outputs may quote the hook and cliffhanger lines only.
6. **The cliffhanger axis is inverted relative to shorts-clipper.** Its
   `rerank.system.md` scores tension that *resolves* inside the clip as good;
   here, unresolved at the cut is the goal. **Write the prompts fresh.** Do not
   open the old file to adapt it - the framing leaks through. See D5.
7. **Label the eval set before running the tool.** `eval/README.md`. Not
   negotiable; it is the difference between an eval and a rationalisation.

## What was borrowed, and what wasn't

Copied from shorts-clipper (`C:\Users\91888\OneDrive\Desktop\New systems\shorts-clipper`,
also at github.com/Akhillavudya/shorts-clipper):

- `src/promo/llm/` - the whole router: tier dispatch, token-bucket rate
  limiting, exponential backoff with jitter, provider failover, and the
  response cache. Renamed `clipper.llm` -> `promo.llm`, otherwise untouched.
  This is the part that makes 50 calls on a free tier survivable.
- `config/settings.yaml` - the tiers/providers/llm blocks, with the tier names
  changed to `candidates` and `rank`.

**Deliberately not borrowed:** the prompts (inverted axis, D5), the snapping
logic (`moments/snap.py` snaps cut points to silence gaps detected by ffmpeg -
there is no audio here, so half of it is dead), and everything in the pipeline
touching video, transcription, rights, rendering or upload. The honest overlap
with shorts-clipper is about 20%, and the write-up should say 20%, not 80%.

## The one thing to re-read when stuck

`notes/FORMAT.md`, the section called "The fact that should shape the whole
approach": a median episode is 118s and a promo is 20-60s, so a promo is 17-50%
of an episode. This is a *selection* problem, not a search problem. Recall is
easy here and precision is everything - the opposite of the podcast clipper.
