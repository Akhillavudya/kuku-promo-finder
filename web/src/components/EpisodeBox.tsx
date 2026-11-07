/**
 * One episode, boxed: its promos in full, and what it rejected to get there.
 *
 * Grouping by episode rather than listing 60 promos flat is the whole point
 * of this layout. The unit of work for someone cutting promos is an episode -
 * "what did we get out of episode 12" - and grouping also makes the two
 * honest facts visible that a flat ranked list hides: that some episodes
 * yielded two promos and some yielded none, and that every kept promo beat
 * several rejected candidates from the same episode.
 *
 * An episode that produced nothing still gets a box. It is a result, not a
 * gap, and the gate that stopped each of its candidates is the evidence for
 * that claim.
 */

import { useState } from "react";
import type { Promo, Rejection } from "../types";
import Icon from "./Icon";
import PromoCard from "./PromoCard";
import RejectionList from "./RejectionList";

interface Props {
  episode: number;
  /** Promos from this episode, each with its season-wide rank. */
  entries: { promo: Promo; rank: number }[];
  /** Candidates from this episode a deterministic gate stopped. */
  rejected: Rejection[];
  /** Candidates from this episode that were scored and still lost. */
  dropped: Rejection[];
}

export default function EpisodeBox({ episode, entries, rejected, dropped }: Props) {
  const [open, setOpen] = useState(false);

  const kept = entries.length;
  const considered = kept + rejected.length + dropped.length;
  const duration = entries[0]?.promo.episode_duration_s ?? null;
  const declined = kept === 0;

  return (
    <section className={`pf-epbox${declined ? " is-declined" : ""}`}>
      <header className="pf-epbox-head">
        <h2 className="pf-epbox-id">
          Episode <span className="pf-epbox-n">{episode}</span>
        </h2>
        <div className="pf-epbox-meta">
          {duration !== null && (
            <span className="pf-tc pf-tc-dim">{duration.toFixed(0)}s</span>
          )}
          <span className="pf-epbox-tally">
            {declined ? (
              <span className="pf-epbox-zero">no promo kept</span>
            ) : (
              <>
                {kept} kept
                {considered > kept && <> of {considered} considered</>}
              </>
            )}
          </span>
        </div>
      </header>

      {declined ? (
        <div className="pf-epbox-body">
          <p className="pf-epbox-why">
            {considered === 0
              ? "The model proposed no candidate span for this episode."
              : `All ${considered} candidate${considered === 1 ? "" : "s"} from this episode were stopped before shipping. The gates and the rubric floor are allowed to decline an episode, and this is what that looks like.`}
          </p>
          {(rejected.length > 0 || dropped.length > 0) && (
            <RejectionList rejections={[...rejected, ...dropped]} />
          )}
        </div>
      ) : (
        <div className="pf-epbox-body">
          {entries.map(({ promo, rank }) => (
            <PromoCard key={promo.id} promo={promo} rank={rank} />
          ))}

          {(rejected.length > 0 || dropped.length > 0) && (
            <div className="pf-also">
              <button
                type="button"
                className="pf-disclosure"
                aria-expanded={open}
                onClick={() => setOpen((was) => !was)}
              >
                <span className="pf-disclosure-mark" data-open={open}>
                  <Icon name="chevron-right" />
                </span>
                Also considered and not kept (
                {rejected.length + dropped.length})
              </button>
              {open && <RejectionList rejections={[...rejected, ...dropped]} />}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
