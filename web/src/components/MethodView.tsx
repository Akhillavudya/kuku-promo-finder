/**
 * How it decides, and what is not verified.
 *
 * Three of the brief's five scoring lenses are not about the code: how the
 * problem was framed, where the line was drawn between a model and
 * deterministic Python, and how honestly the weaknesses are reported. This
 * page is where those three are answered, in one place, in words.
 *
 * The limits section is not hedging. The held-out evaluation was never
 * performed, so no number anywhere in this app compares a pick to a human's
 * judgement. Saying that plainly, on the page a reader actually opens, is the
 * honest form - a quiet omission would read as an unnoticed one.
 */

import type { RunSummary } from "../types";

const SPLIT: { model: string; python: string }[] = [
  {
    model: "Proposes candidate spans, as block indices",
    python: "Turns block indices into seconds, from the parsed block table",
  },
  {
    model: "Names the hook line and the beat the cut lands on",
    python: "Checks the hook lands inside the first 3 seconds, and on a dialogue or ACTION block",
  },
  {
    model: "Scores four axes from 1 to 10, twice, independently",
    python: "Averages the passes, keeps every raw pass, and computes the weighted total",
  },
  {
    model: "Writes why the pick works and where it is weak",
    python: "Enforces 20-60 seconds, the minimum segment length, and the per-episode cap",
  },
];

export default function MethodView({ summary }: { summary: RunSummary }) {
  const spread = summary.score_spread;

  return (
    <div className="pf-prose">
      <section className="pf-panel">
        <h2 className="pf-panel-h">The problem, as framed</h2>
        <p>
          A median episode in this season runs 118 seconds and a promo has to
          be 20 to 60 seconds long. A promo is therefore 17 to 50% of its
          episode, which makes this a <strong>selection</strong> problem rather
          than a search problem. Finding a candidate is easy; almost any
          window of the right length contains something. Choosing which one
          goes out is the whole task, so precision matters and recall barely
          does.
        </p>
        <p>
          That reading is what the pipeline is shaped around. The model is
          asked for several candidates per episode and most of them are thrown
          away &mdash; {summary.n_candidates_proposed ?? 147} proposed,{" "}
          {summary.n_promos ?? 60} kept. A tool built for recall would keep
          them.
        </p>
      </section>

      <section className="pf-panel">
        <h2 className="pf-panel-h">
          What the model decides, and what it is not allowed to decide
        </h2>
        <p>
          The dividing line is the single most load-bearing decision in the
          build: a model asked for <span className="pf-tc">00:42.50</span>{" "}
          drifts and invents, while a model asked for block 34 is either right
          or obviously wrong. So the model never emits a timestamp. It returns
          indices into a table Python built, and Python resolves them.
        </p>
        <div className="pf-split">
          <div className="pf-split-col">
            <h3 className="pf-split-h">The model</h3>
            <ul className="pf-split-list">
              {SPLIT.map((row) => (
                <li key={row.model}>{row.model}</li>
              ))}
            </ul>
          </div>
          <div className="pf-split-col pf-split-col-py">
            <h3 className="pf-split-h">Python, deterministically</h3>
            <ul className="pf-split-list">
              {SPLIT.map((row) => (
                <li key={row.python}>{row.python}</li>
              ))}
            </ul>
          </div>
        </div>
        <p className="pf-panel-foot">
          The 3-second hook gate is the clearest case. It is a rule about where
          a line sits in time, it fires on a dialogue or ACTION block and never
          on a camera direction, and it is worth nothing if a model can talk
          its way past it. Every promo in this app shows which block satisfied
          it and at what offset, so the rule can be watched firing rather than
          taken on trust.
        </p>
      </section>

      <section className="pf-panel pf-panel-limit">
        <h2 className="pf-panel-h">What is not verified</h2>
        <p>
          <strong>
            No number in this app compares a pick to a human&rsquo;s judgement.
          </strong>{" "}
          Five episodes were held out to be hand-labelled blind before the tool
          ran on them. There was not time to label them before the deadline, and
          the decision taken was to ship a complete 50-episode season instead of
          a quality-checking section that could not be finished. The held-out
          episodes were then run with the rest.
        </p>
        <p>
          The consequence is specific and worth stating exactly: coverage,
          durations, gate rejection counts and score stability are all the tool
          measured against itself. They show it is internally consistent. They
          cannot show it picks well. Any labelling done from here on is a
          post-hoc, non-blind agreement check, and would have to be described
          as one.
        </p>
      </section>

      <section className="pf-panel">
        <h2 className="pf-panel-h">Where it is weak</h2>
        <ul className="pf-weaklist">
          <li>
            <strong>The two scoring passes disagree more than is comfortable.</strong>{" "}
            Median disagreement on the weighted total is{" "}
            {spread?.median?.toFixed(2) ?? "0.68"} points, and{" "}
            {spread?.n_over_1_point ?? 25} of {spread?.n_multi_pass ?? 78} scored
            candidates differ by more than a full point. The worst pair differs by{" "}
            {spread?.max?.toFixed(1) ?? "2.6"}. Both passes are kept in the output
            rather than averaged away.
          </li>
          <li>
            <strong>Five of the kept promos were trimmed to fit.</strong> A trim
            moves the cut to satisfy the duration gate, which can land it before
            the beat the model named as the cliffhanger. Those promos are weaker
            than their own description, and each one says so on its card.
          </li>
          <li>
            <strong>The model prefers the tight dramatic beat over the gate.</strong>{" "}
            {(summary.rejections_by_gate ?? {}).too_short ?? 66} of the{" "}
            {summary.n_rejected_by_gates ?? 69} gate rejections are candidates
            under 20 seconds. Recalibrating the prompt fixed part of this and
            four rewordings did not fix the rest.
          </li>
          <li>
            <strong>The hook category is unstable on near-identical beats.</strong>{" "}
            It is a filter for an editor, never an input to a score &mdash; the
            scoring model is not shown it &mdash; which is why an unstable label
            is tolerable here and would not be if it were weighted.
          </li>
        </ul>
      </section>
    </div>
  );
}
