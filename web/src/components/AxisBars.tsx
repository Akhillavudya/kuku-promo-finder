/**
 * The four raw axis scores, side by side and never collapsed. Hard rule 4.
 *
 * A weighted total tells you the tool picked badly. These four numbers tell
 * you *which axis* it misjudged, which is the difference between "it was
 * wrong" and "it systematically overrates hooks that open on a shout".
 *
 * Four hues rather than one, because the question this component answers is a
 * comparison across axes - and these four are the only saturated colour on
 * the page, so colour here means data and never decoration. Every bar also
 * carries its number and its name as text: nothing is signalled by colour
 * alone.
 */

import { AXES, type Axis, type Promo } from "../types";

const HUE: Record<Axis, string> = {
  hook_strength: "var(--ax-hook)",
  cliffhanger: "var(--ax-cliff)",
  standalone: "var(--ax-stand)",
  emotional_charge: "var(--ax-charge)",
};

const LABEL: Record<Axis, string> = {
  hook_strength: "Hook strength",
  cliffhanger: "Cliffhanger",
  standalone: "Stands alone",
  emotional_charge: "Emotional charge",
};

/** Shown beside each name so the weighted total reads as arithmetic rather
 *  than magic. Display only - config/rubric.yaml is the source of truth and
 *  promo.score is what multiplies. */
const WEIGHT: Record<Axis, number> = {
  hook_strength: 0.3,
  cliffhanger: 0.3,
  standalone: 0.25,
  emotional_charge: 0.15,
};

interface Props {
  scores: Promo["scores"];
  /** How many rank passes produced these numbers. More than one means each
   *  value is a mean - say so rather than let an 8.5 look like a raw score. */
  passes?: number;
  /** Axes a rank response never answered, clamped to 1 (ACCURACY #6). A low
   *  number from a fault must not read as a low score. */
  missing?: Axis[];
}

export default function AxisBars({ scores, passes = 0, missing = [] }: Props) {
  return (
    <div className="pf-axes">
      <h3 className="pf-axes-h">
        Rubric axes
        {passes > 1 && <span className="pf-axes-passes">mean of {passes} passes</span>}
      </h3>

      {AXES.map((axis) => {
        const raw = scores?.[axis];
        const value = typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
        const absent = missing.includes(axis);
        return (
          <div className="pf-axis" key={axis}>
            <span className="pf-axis-l">
              {LABEL[axis]}
              <span className="pf-axis-w">&times;{WEIGHT[axis].toFixed(2)}</span>
            </span>
            <span className="pf-axis-bar" aria-hidden="true">
              <span
                className="pf-axis-fill"
                style={{
                  width: `${Math.min(100, Math.max(0, (value / 10) * 100))}%`,
                  background: HUE[axis],
                }}
              />
            </span>
            <span className={`pf-axis-v${absent ? " is-missing" : ""}`}>
              {absent ? "n/a" : value.toFixed(1)}
            </span>
          </div>
        );
      })}

      {missing.length > 0 && (
        <p className="pf-axes-note">
          {missing.length === 1 ? "One axis was" : `${missing.length} axes were`} never
          returned by the scorer and clamped to 1. That is a provider fault, not a low
          score.
        </p>
      )}
    </div>
  );
}
