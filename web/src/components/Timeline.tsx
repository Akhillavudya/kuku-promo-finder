/**
 * The episode strip: the whole episode as a track, the promo as bright blocks
 * on it, and the 3-second hook gate drawn at actual scale.
 *
 * This is the one component a table cannot replace. The project's claim is
 * that a promo is a *selected* 17-50% of a 118-second episode and that the
 * hook has to land inside the first 3 seconds of the cut. Both of those are
 * claims about position, and this is what they look like: the gate window is
 * a genuine sliver - 3 seconds of a 138-second episode is 2% of the strip -
 * and drawing it to scale is the honest way to show how little room the rule
 * leaves, rather than an oversized badge that flatters it.
 *
 * Nothing here computes a timestamp. start_s, end_s and hook_offset_s were
 * all resolved from the parsed block table in Python (hard rule 1); this file
 * divides by the episode length to get a percentage and does no other
 * arithmetic on time.
 */

import type { Promo } from "../types";

/** Mirrors the hook gate in config/rubric.yaml, for drawing only - the gate
 *  itself fires in promo.gates, and this value never decides anything. */
const HOOK_GATE_S = 3;

/** Median episode length from notes/FORMAT.md, for records written before
 *  episode_duration_s existed. Only ever a display scale. */
const FALLBACK_EPISODE_S = 118;

function episodeSeconds(promo: Promo): number {
  if (promo.episode_duration_s && promo.episode_duration_s > 0) {
    return promo.episode_duration_s;
  }
  const ends = promo.segments.map((s) => s.end_s);
  return Math.max(...ends, FALLBACK_EPISODE_S);
}

function pct(value: number): string {
  return `${Math.min(100, Math.max(0, value)).toFixed(3)}%`;
}

export default function Timeline({ promo }: { promo: Promo }) {
  const total = episodeSeconds(promo);
  const segments = promo.segments ?? [];
  const first = segments[0];

  const spoken =
    segments.map((s, i) => `segment ${i + 1} from ${s.start} to ${s.end}`).join(", ") ||
    "no segments";

  const caretAt =
    first && promo.hook_offset_s !== null && promo.hook_offset_s !== undefined
      ? first.start_s + promo.hook_offset_s
      : null;

  return (
    <div className="pf-strip">
      <div
        className="pf-strip-track"
        role="img"
        aria-label={`Episode timeline, ${total.toFixed(0)} seconds total: ${spoken}`}
      >
        {segments.map((segment, i) => (
          <span
            key={`${segment.start_block}-${segment.end_block}-${i}`}
            className="pf-strip-seg"
            style={{
              left: pct((segment.start_s / total) * 100),
              width: pct(((segment.end_s - segment.start_s) / total) * 100),
            }}
          >
            <span className="pf-strip-segn">{i + 1}</span>
          </span>
        ))}

        {/* The gate's own window, to scale, at the head of the first segment. */}
        {first && (
          <span
            className="pf-strip-gate"
            style={{
              left: pct((first.start_s / total) * 100),
              width: pct((HOOK_GATE_S / total) * 100),
            }}
          />
        )}

        {caretAt !== null && (
          <span className="pf-strip-caret" style={{ left: pct((caretAt / total) * 100) }}>
            <span className="pf-strip-caret-head" />
          </span>
        )}
      </div>

      <div className="pf-strip-rail" aria-hidden="true">
        {segments.map((segment, i) => (
          <span
            key={`t-${i}`}
            className="pf-strip-tick"
            style={{ left: pct((segment.start_s / total) * 100) }}
          />
        ))}
        {segments.map((segment, i) => (
          <span
            key={`te-${i}`}
            className="pf-strip-tick"
            style={{ left: pct((segment.end_s / total) * 100) }}
          />
        ))}
      </div>

      <div className="pf-strip-legend">
        <span className="pf-tc pf-tc-dim">00:00.00</span>
        <span className="pf-strip-ranges">
          {segments.length > 0 ? (
            segments.map((segment, i) => (
              <span className="pf-strip-range" key={`r-${i}`}>
                <span className="pf-tc">{segment.start}</span>
                <span className="pf-strip-dash" aria-hidden="true" />
                <span className="pf-tc">{segment.end}</span>
              </span>
            ))
          ) : (
            // No segments at all: the same dimmed bar every other absent
            // number in the app uses, rather than an em dash standing in for
            // a timecode in a row that otherwise only holds timecodes.
            <span className="pf-strip-range">
              <span className="pf-skel" role="img" aria-label="no segments" />
            </span>
          )}
        </span>
        <span className="pf-tc pf-tc-dim">{total.toFixed(0)}s</span>
      </div>
    </div>
  );
}
