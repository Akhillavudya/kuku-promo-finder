# START HERE

Kuku AI Generalist Assignment — **Problem 1: Find the Promos**.
Everything you need is in this folder. Nothing is blocked.

---

## 1. The deadline

| | |
|---|---|
| Input pack landed in Downloads | **Wed 5 Nov 2026, 17:57 IST** |
| Brief landed two minutes later | 17:59 IST |
| 48 hours from then | **Sat 7 Nov 2026, ~17:57 IST** |
| Folder set up | Thu 6 Nov, 00:15 IST — ~41.7 h left at that moment |

Subtract 8 hours for sleep and the real working budget is about **30 hours**,
against an assignment the brief says should take **2–3 hours**. You are not
short of time. You are at risk of over-building — which is the thing that cost
you on the clipper, and which this brief explicitly scores under "approach and
scale".

**Target: finish the build by Friday evening, spend Saturday morning on the
write-up, submit with hours to spare.**

---

## 2. What the task actually is

Read the screenplay, return promos of **20–60 seconds** that:

- **hook in the first 3 seconds**
- **end on an unresolved cliffhanger** — cut while the tension is live
- **stand alone** — make sense to someone who has seen none of the series

For each promo output: episode · ordered segment start/end timestamps · the
hook · the cliffhanger · one line on why it works. Then **rank them**. Then say
**where your tool picks badly** — the brief asks this directly and most
submissions will dodge it.

Five scoring lenses: problem choice and framing · approach and scale · quality
checking · the prototype · communication. Note that three of the five are not
about the code.

---

## 3. What is already in this folder

| Path | What it is | Status |
|---|---|---|
| `START_HERE.md` | this file | done |
| `CLAUDE.md` | project rules — next session's Claude reads this automatically | done |
| `DECISIONS.md` | **the decision ledger. 9 settled, 3 open and waiting on you** | done |
| `notes/FORMAT.md` | the input format, measured off all 50 files, not guessed | done |
| `notes/stats.py` | re-derives every number in FORMAT.md — `python -I notes/stats.py` | done |
| `pack/` | **the 50 episodes.** Gitignored forever | done |
| `brief/` | the assignment PDF. Gitignored | done |
| `config/settings.yaml` | LLM tiers, providers, rate limits | done |
| `config/rubric.yaml` | the 4 scoring weights + the deterministic gates | done |
| `src/promo/llm/` | the router, cache, rate limiter, failover — borrowed, working | done |
| `eval/README.md` | the hand-label protocol, and which 5 episodes | done |
| `eval/labels.template.json` | copy to `labels.json` and fill in | done |
| `.gitignore` `.env.example` `requirements.txt` | | done |
| `outputs/` | empty, waiting | — |

**Not created yet — this is your build list:**

| File | Does what | Est. |
|---|---|---|
| `.env` | copy `.env.example`, paste your `GEMINI_API_KEY` | 2 min |
| `eval/labels.json` | **your 5 hand-labelled episodes. DO THIS FIRST** | 1 h |
| `src/promo/parse.py` | screenplay to block table. Two regexes, both in FORMAT.md | 45 min |
| `src/promo/gates.py` | the 3s hook check, duration, segment count — pure Python | 30 min |
| `src/promo/prompts/candidates.md` | pass 1 system prompt. **Write fresh** (D5) | 30 min |
| `src/promo/prompts/rank.md` | pass 2 system prompt. **Write fresh** (D5) | 30 min |
| `src/promo/run.py` | parse to candidates to gates to rank, into `outputs/` | 1 h |
| `src/promo/compare.py` | tool output vs `labels.json`, the four measures | 30 min |
| `app.py` | Gradio, two tabs (D9) | 1 h |
| `SOLUTION.md` to PDF | the 2-page deliverable | 1.5 h |

Roughly **8 hours of work.** You have 30. The slack is deliberate.

---

## 4. How to proceed

### Step 0 — before anything (15 min)

Read `DECISIONS.md` end to end. Settle **D10, D11, D12** and write your
reasons into the file. They change what you build, so they come first.

### Step 1 — the eval set (1 h) · DO NOT SKIP OR REORDER

`eval/README.md`. Hand-label episodes **1, 44, 36, 17, 29**. Write down what
you *rejected* and why, not just what you picked.

> Label first, run second. Afterwards it is not an eval, it is a
> rationalisation — and that reads clearly to someone marking 50 of these.

### Step 2 — the parser (45 min)

`parse.py`. Episode file to an ordered list of blocks, each with: index, kind
(`CAMERA` / `ACTION` / `SOUND FX` / speaker name), mood parenthetical, start_s,
end_s, body text. Plus the episode's logline and continuity notes, which are
free context — use them for the standalone axis.

Sanity check that must pass: **3,727 blocks across 50 files, 0 parse failures.**
If you get a different number, the parser is wrong, not the data.

Add the ~15-line speaker alias map here (`JULIANA` and `LADY JULIANA` are the
same person — see FORMAT.md).

### Step 3 — the gates (30 min)

`gates.py`, pure Python, no model: duration in 20–60s, at most 3 segments, each
at least 3s, and **a dialogue or ACTION block starting within 3.0s of the promo
start**. Never a CAMERA block. Each rejection returns the gate it failed, and
you keep those — the rejection counts go in the write-up.

### Step 4 — the prompts (1 h)

Written fresh. Pass 1 returns **block indices** and is told to favour coverage
over taste. Pass 2 scores 1–10 on the four axes in `config/rubric.yaml` and
Python computes the weighted sum.

### Step 5 — run it (30 min + waiting)

Start with **3 episodes**, read the output with your own eyes, then run all 50.
The cache means a re-run costs nothing, so there is no reason to go wide early.

### Step 6 — compare (30 min)

`compare.py` against `labels.json`. Overlap, hook agreement, cliffhanger
agreement, rejected-candidate hits. **These numbers are the best part of your
submission.** Do not round them in your favour.

### Step 7 — the demo (1 h)

Gradio, two tabs. Tab 1 reads precomputed `outputs/` with no API call and
therefore cannot fail in front of a grader. Tab 2 runs live on pasted text.
Push to a Hugging Face Space, free tier, `GEMINI_API_KEY` as a repo secret.

### Step 8 — write it up (1.5 h)

Two pages, no more. Structure that fits the five lenses:

1. **How I framed it** — a promo is 17–50% of a 118-second episode, so this is
   a *selection* problem, not a search problem. Recall is easy; precision is
   everything.
2. **What is code and what is a model** — the 3s hook gate, the duration and
   segment gates, and the weighted sum are all deterministic Python. The model
   proposes spans and scores four axes. It never emits a timestamp.
3. **Where it picks badly** — the real numbers from step 6, including the
   episodes where it declined to produce anything.
4. **Cost and scale** — pull the actual token counts out of `llm.log`, which is
   JSONL with one record per call carrying `tokens_in` and `tokens_out`. Sum
   them, state the per-50-episode cost, extrapolate to a real catalogue.
5. **What I would do with another week** — short, specific, no promises.

Two or three lines at the end on shorts-clipper, with the GitHub link, framed
as *where the architecture came from* — not as a second submission.

---

## 5. Deliverables checklist

- [ ] 2-page PDF solution doc
- [ ] Prototype link (Hugging Face Space)
- [ ] Raw outputs folder, link-visible to anyone
- [ ] Optional: walkthrough video, **3 minutes maximum**

**The confidentiality trap:** the brief wants links that open for anyone *and*
says do not publish the pack. So: code and outputs public; the 50 screenplays
never committed and never in the deployed demo; outputs quote only the hook and
cliffhanger lines. **State this decision in the doc** — the brief creates the
tension itself, and showing you noticed is a point in your favour.

---

## 6. The five things most likely to go wrong

1. **Over-building.** You have 30 hours and the brief wants 2–3. Every hour
   past the plan is spent against a lens that rewards restraint. If you find
   yourself adding a queue, a database or a second UI, stop.
2. **Labelling after running.** It destroys the most valuable section of the
   write-up and you cannot undo it.
3. **Copying the old prompt.** shorts-clipper scores *resolved* tension as good.
   This assignment wants the opposite. Open that file and the framing follows
   you in. See D5.
4. **Committing `pack/`.** Check `git status` before every commit. The
   `.gitignore` is right — do not add an exception.
5. **Burning Friday on the demo.** Tab 1 is precomputed JSON and a table. It
   does not need to be beautiful; it needs to open and be correct.

---

## 7. Where things came from

shorts-clipper lives at `C:\Users\91888\OneDrive\Desktop\New systems\shorts-clipper`
and at **github.com/Akhillavudya/shorts-clipper** (public, 186 files, 934 tests
passing). `src/promo/llm/` and the shape of `config/settings.yaml` came from
there; the honest overlap is about **20%**, and the write-up should say 20%.
`CLAUDE.md` has the full account of what was borrowed and what was deliberately
left behind.
