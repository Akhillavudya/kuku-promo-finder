/**
 * Run-level numbers, including the unflattering ones.
 *
 * Four of these seven tiles are not achievements: candidates proposed,
 * candidates stopped by a gate, episodes that kept nothing, and the median
 * disagreement between two independent scoring passes. They sit in the same
 * row as "promos kept" on purpose. The brief asks for an honest account of
 * where the tool picks badly, and a summary that reported only the wins would
 * be answering a different question.
 *
 * Spend is read out of llm.log by Python - a measured number, not an
 * estimate.
 */

import type { RunSummary } from "../types";

/**
 * A tile's number, or a dimmed bar if the run did not report it.
 *
 * It used to be an em dash, which is the wrong signal twice: it reads as a
 * typographic glyph in a slot that otherwise only ever holds digits, and in a
 * face without the character it draws a tofu box, which looks like the app is
 * broken rather than like a number is absent.
 */
function Value({ value }: { value: string | number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="pf-skel pf-skel-lg" role="img" aria-label="not reported" />;
  }
  return <>{value}</>;
}

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number | null | undefined;
  hint?: string;
  tone?: "plain" | "caution";
}) {
  return (
    <div className={`pf-tile${tone === "caution" ? " is-caution" : ""}`}>
      <span className="pf-tile-v">
        <Value value={value} />
      </span>
      <span className="pf-tile-l">{label}</span>
      {hint ? <span className="pf-tile-h">{hint}</span> : null}
    </div>
  );
}

export default function SummaryPanel({ summary }: { summary: RunSummary }) {
  if (!summary || Object.keys(summary).length === 0) return null;

  const spend = summary.spend ?? {};
  const gates = Object.entries(summary.rejections_by_gate ?? {}).sort(
    (a, b) => b[1] - a[1],
  );
  const worstGate = gates[0]?.[1] ?? 0;
  const spread = summary.score_spread;

  return (
    <section className="pf-summary" aria-label="Run summary">
      <div className="pf-tiles">
        <Tile label="Episodes read" value={summary.n_episodes} />
        <Tile label="Promos kept" value={summary.n_promos} />
        <Tile
          label="Candidates proposed"
          value={summary.n_candidates_proposed}
          hint="by the model"
        />
        <Tile
          label="Stopped by a gate"
          value={summary.n_rejected_by_gates}
          hint="Python, before scoring"
          tone="caution"
        />
        <Tile
          label="Episodes with none"
          value={
            summary.n_episodes_with_no_promo ??
            (summary.episodes_with_no_promo ?? []).length
          }
          hint="declined on purpose"
          tone="caution"
        />
        <Tile
          label="Score disagreement"
          value={spread?.median !== undefined ? spread.median.toFixed(2) : null}
          hint={`median across ${summary.rank_passes ?? 2} passes`}
          tone="caution"
        />
        <Tile
          label="Model spend"
          value={`$${(spend.usd_total ?? 0).toFixed(2)}`}
          hint={`${spend.calls ?? 0} calls, ${spend.cached_calls ?? 0} cached`}
        />
      </div>

      {gates.length > 0 && (
        <div className="pf-gatechart">
          <h2 className="pf-panel-h">
            Which gate stopped a candidate
            <span className="pf-panel-sub">
              deterministic rules in Python, no model involved
            </span>
          </h2>
          <ul className="pf-gatebars">
            {gates.map(([gate, count]) => (
              <li className="pf-gatebar" key={gate}>
                <code className="pf-gatebar-name">{gate}</code>
                <span className="pf-gatebar-track" aria-hidden="true">
                  <span
                    className="pf-gatebar-fill"
                    style={{
                      width: `${worstGate > 0 ? (count / worstGate) * 100 : 0}%`,
                    }}
                  />
                </span>
                <span className="pf-gatebar-n">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
