/**
 * One promo, in full: everything the brief asks to output for a pick, laid
 * out so it can be read rather than decoded.
 *
 * Two columns on a wide screen. The left is the writing - the hook, the beat
 * it cuts on, why it works, and the weakest point the model named about its
 * own pick. The right is the measurement - four raw axis scores and the
 * deterministic gate evidence. Keeping them apart matters: the left is a
 * model's prose and the right is Python's arithmetic, and a reader should
 * never have to guess which one they are looking at.
 *
 * The hook is set as a quotation because it is one - a line of dialogue
 * someone says on screen. The cliffhanger is the tool's description of a
 * beat, not a quote, so it is set as prose. That difference is why the two
 * are typeset differently.
 *
 * `rank` is omitted on the live view, where the ordering is within one pasted
 * episode and a season-wide "#1" would be a lie.
 */

import type { Promo } from "../types";
import AxisBars from "./AxisBars";
import Timeline from "./Timeline";

interface Props {
  promo: Promo;
  rank?: number;
}

export default function PromoCard({ promo, rank }: Props) {
  const segments = promo.segments?.length ?? 0;
  const gated = promo.hook_block !== null && promo.hook_offset_s !== null;
  const spread = promo.score_spread ?? 0;
  const passes = promo.score_passes?.length ?? 0;

  return (
    <article className="pf-promo">
      <header className="pf-promo-head">
        {rank !== undefined && (
          <span
            className={`pf-rank${rank <= 3 ? " is-top" : ""}`}
            aria-label={`Season rank ${rank}`}
          >
            #{rank}
          </span>
        )}
        <span className="pf-promo-dur">
          <span className="pf-tc pf-tc-lg">{(promo.duration_s ?? 0).toFixed(1)}s</span>
          <span className="pf-promo-segs">
            {segments} segment{segments === 1 ? "" : "s"}
          </span>
        </span>
        <span
          className="pf-promo-score"
          aria-label={`Weighted score ${(promo.weighted_score ?? 0).toFixed(2)} out of 10`}
        >
          <span className="pf-score-v">{(promo.weighted_score ?? 0).toFixed(2)}</span>
          {spread > 0 && (
            <span className="pf-spread" title={`Range across ${passes} rank passes`}>
              &plusmn;{spread.toFixed(2)}
            </span>
          )}
        </span>
      </header>

      <Timeline promo={promo} />

      <div className="pf-promo-body">
        <div className="pf-lines">
          <section className="pf-line">
            <h3 className="pf-line-h">
              Hook
              {promo.hook_type && (
                <span
                  className="pf-tag"
                  title="Hook category. Metadata for filtering - the scoring model never sees it and it cannot move a score."
                >
                  {promo.hook_type}
                </span>
              )}
            </h3>
            <blockquote className="pf-quote">
              {promo.hook || "No hook line reported"}
            </blockquote>
          </section>

          <section className="pf-line">
            <h3 className="pf-line-h">Cuts on</h3>
            <p className="pf-line-b">
              {promo.cliffhanger || "No cliffhanger reported"}
            </p>
          </section>

          <section className="pf-line">
            <h3 className="pf-line-h">Why it works</h3>
            <p className="pf-line-b">{promo.why || "Not reported"}</p>
          </section>

          <section className="pf-line">
            <h3 className="pf-line-h pf-line-h-weak">Weakest point</h3>
            <p className="pf-line-b pf-line-b-weak">{promo.weakness || "Not reported"}</p>
          </section>

          {promo.needs_to_know ? (
            <section className="pf-line">
              <h3 className="pf-line-h pf-line-h-weak">Needs to know</h3>
              <p className="pf-line-b pf-line-b-weak">{promo.needs_to_know}</p>
            </section>
          ) : null}
        </div>

        <aside className="pf-promo-side">
          <AxisBars
            scores={promo.scores}
            passes={passes}
            missing={promo.missing_axes ?? []}
          />

          <div className="pf-gate">
            <h3 className="pf-gate-h">Gate evidence</h3>
            {gated ? (
              <p className="pf-gate-line pf-gate-ok">
                <span className="pf-gate-flag" aria-hidden="true">
                  &#10003;
                </span>
                <span>
                  Hook lands inside 3s &mdash; block {promo.hook_block} starts{" "}
                  <span className="pf-tc">+{(promo.hook_offset_s ?? 0).toFixed(2)}s</span>{" "}
                  into the cut
                </span>
              </p>
            ) : (
              <p className="pf-gate-line pf-gate-bad">
                <span className="pf-gate-flag" aria-hidden="true">
                  &#33;
                </span>
                <span>No hook gate evidence on this record</span>
              </p>
            )}

            {/*
             * Not "repaired". A trim moves the cut point to satisfy the
             * duration gate, which means the clip can end *before* the beat
             * the model named as the cliffhanger - so the pick is weaker than
             * its own description, not fixed. Five of the 60 shipped promos
             * are in this state and the wording has to say so.
             */}
            {promo.duration_adjustment ? (
              <p className="pf-gate-line pf-gate-warn">
                <span className="pf-gate-flag" aria-hidden="true">
                  &#9650;
                </span>
                <span>
                  Trimmed to fit the duration gate, so the cut may land before the
                  beat described above &mdash; {promo.duration_adjustment}
                </span>
              </p>
            ) : null}
          </div>
        </aside>
      </div>
    </article>
  );
}
