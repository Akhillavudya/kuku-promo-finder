/**
 * The precomputed season. **Makes no model call of any kind.**
 *
 * This is the view that is open when the link is clicked, and the reason it
 * is first: it reads outputs/*.json off the server's disk, so there is no
 * key, no quota, no cold model and nothing to warm up. It cannot fail in
 * front of a reader beyond the server itself being asleep.
 *
 * Everything here is client-side. The whole payload is one season and a round
 * trip per control change would buy nothing - and keeping all of it in memory
 * is what lets a promo keep its **season-wide** rank when you filter to one
 * episode, instead of being renumbered from 1. The badge means the same thing
 * in both views, which is the only way a ranking is worth printing.
 */

import { useMemo, useState } from "react";
import { ALL_EPISODES } from "./Sidebar";
import type { Promo, Rejection, SeasonResponse } from "../types";
import EpisodeBox from "./EpisodeBox";
import Notice from "./Notice";
import SummaryPanel from "./SummaryPanel";

type SortId = "rank" | "episode";

interface Props {
  data: SeasonResponse | null;
  loading: boolean;
  episode: number | typeof ALL_EPISODES;
}

function groupByEpisode<T extends { episode: number }>(items: T[]): Map<number, T[]> {
  const map = new Map<number, T[]>();
  for (const item of items) {
    const bucket = map.get(item.episode);
    if (bucket) bucket.push(item);
    else map.set(item.episode, [item]);
  }
  return map;
}

export default function SeasonView({ data, loading, episode }: Props) {
  const [sort, setSort] = useState<SortId>("rank");
  const [showDeclined, setShowDeclined] = useState(true);

  // promos.json is written in season rank order, so the index *is* the rank.
  const ranked = useMemo(
    () => (data?.promos ?? []).map((promo: Promo, i) => ({ promo, rank: i + 1 })),
    [data],
  );

  const promosByEpisode = useMemo(() => {
    const map = new Map<number, { promo: Promo; rank: number }[]>();
    for (const entry of ranked) {
      const bucket = map.get(entry.promo.episode);
      if (bucket) bucket.push(entry);
      else map.set(entry.promo.episode, [entry]);
    }
    return map;
  }, [ranked]);

  const rejectedByEpisode = useMemo(
    () => groupByEpisode<Rejection>(data?.rejected ?? []),
    [data],
  );
  const droppedByEpisode = useMemo(
    () => groupByEpisode<Rejection>(data?.dropped_in_selection ?? []),
    [data],
  );

  /** Every episode number that has anything to say, promos or not. */
  const allEpisodes = useMemo(() => {
    const total = data?.summary?.n_episodes ?? 0;
    if (total > 0) return Array.from({ length: total }, (_, i) => i + 1);
    const seen = new Set<number>([
      ...promosByEpisode.keys(),
      ...rejectedByEpisode.keys(),
      ...droppedByEpisode.keys(),
    ]);
    return [...seen].sort((a, b) => a - b);
  }, [data, promosByEpisode, rejectedByEpisode, droppedByEpisode]);

  const visible = useMemo(() => {
    let numbers =
      episode === ALL_EPISODES ? allEpisodes : allEpisodes.includes(episode) ? [episode] : [];

    if (episode === ALL_EPISODES && !showDeclined) {
      numbers = numbers.filter((n) => (promosByEpisode.get(n)?.length ?? 0) > 0);
    }

    if (sort === "rank") {
      // Best pick first; episodes that shipped nothing go last, in order.
      return [...numbers].sort((a, b) => {
        const bestA = promosByEpisode.get(a)?.[0]?.rank ?? Infinity;
        const bestB = promosByEpisode.get(b)?.[0]?.rank ?? Infinity;
        if (bestA !== bestB) return bestA - bestB;
        return a - b;
      });
    }
    return numbers;
  }, [episode, allEpisodes, showDeclined, sort, promosByEpisode]);

  if (loading) {
    return <Notice>Reading the precomputed season from outputs/&hellip;</Notice>;
  }

  if (!data || !data.ok) {
    return (
      <Notice kind="warn">{data?.error ?? "The season could not be loaded."}</Notice>
    );
  }

  const shownPromos = visible.reduce(
    (sum, n) => sum + (promosByEpisode.get(n)?.length ?? 0),
    0,
  );

  return (
    <>
      <SummaryPanel summary={data.summary} />

      <div className="pf-toolbar">
        <p className="pf-toolbar-count">
          {episode === ALL_EPISODES ? (
            <>
              <strong>{shownPromos}</strong> promos across{" "}
              <strong>{visible.length}</strong> episodes
            </>
          ) : (
            <>
              Episode <strong>{episode}</strong> only &mdash; ranks are still
              season-wide
            </>
          )}
        </p>

        <div className="pf-toolbar-controls">
          <label className="pf-field">
            <span className="pf-label">Order</span>
            <select
              className="pf-select"
              value={sort}
              onChange={(event) => setSort(event.target.value as SortId)}
            >
              <option value="rank">Best promo first</option>
              <option value="episode">Episode order</option>
            </select>
          </label>

          {episode === ALL_EPISODES && (
            <label className="pf-check">
              <input
                type="checkbox"
                checked={showDeclined}
                onChange={(event) => setShowDeclined(event.target.checked)}
              />
              <span>Show episodes that kept nothing</span>
            </label>
          )}
        </div>
      </div>

      {visible.length === 0 ? (
        <Notice kind="warn">
          Nothing to show for this filter. Pick another episode in the rail.
        </Notice>
      ) : (
        visible.map((number) => (
          <EpisodeBox
            key={number}
            episode={number}
            entries={promosByEpisode.get(number) ?? []}
            rejected={rejectedByEpisode.get(number) ?? []}
            dropped={droppedByEpisode.get(number) ?? []}
          />
        ))
      )}
    </>
  );
}
