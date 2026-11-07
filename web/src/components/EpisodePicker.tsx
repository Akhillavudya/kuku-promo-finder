/**
 * The episode selector: one button, and all 50 episodes behind it.
 *
 * It replaced a 51-row list that lived permanently in the rail. That list was
 * the only reason the rail scrolled, and a scrolling rail cost two things
 * that matter here: the run's headline numbers and the provider line got
 * pushed below the fold on a laptop, and the list itself scrolled *inside* a
 * scrolling column, which is the worst kind of nested scroll to hit with a
 * trackpad. Closed by default, the whole rail now fits any viewport taller
 * than about 620px with nothing cut off.
 *
 * What the menu does not do is hide the declines. Every one of the 50 is a
 * cell, and an episode that shipped nothing reads "none" rather than being
 * omitted - 16 of 50 declined, and a picker that listed only the 34 would
 * make a 34-episode season look like the whole thing. That was the original
 * list's one good property and it survives the move.
 *
 * Why the panel is `position: fixed` and measured rather than absolutely
 * positioned inside the rail: the rail is a scroll container, and a scroll
 * container clips its descendants. An absolute panel would be cut off at the
 * rail's right edge, which caps it at 224px - too narrow for three columns,
 * and three columns are what keep 51 cells to roughly one screen instead of
 * the long scroll this was meant to remove. So it is anchored off the
 * button's own rect, and re-anchored on resize and on scroll.
 *
 * ARIA: this is a disclosure button over a group of buttons, not a
 * `listbox`. A listbox owes the user arrow-key roving focus and typeahead,
 * and claiming the role without implementing them is worse than not claiming
 * it. As plain buttons every cell is reachable by Tab, the filter narrows
 * them, and Escape closes - all of which actually works.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { ALL_EPISODES, type EpisodeEntry } from "../nav";

interface Props {
  episodes: EpisodeEntry[];
  episode: number | typeof ALL_EPISODES;
  onEpisode: (episode: number | typeof ALL_EPISODES) => void;
  /** Promos in the run, shown against the "All episodes" row. */
  kept: number;
  loading: boolean;
}

/** Panel geometry. Kept here rather than in CSS because JS does the maths. */
const GAP = 6;
const MAX_W = 440;
const MARGIN = 12;

export default function EpisodePicker({
  episodes,
  episode,
  onEpisode,
  kept,
  loading,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [box, setBox] = useState<{ top: number; left: number; width: number } | null>(
    null,
  );
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLInputElement>(null);

  /** Put the panel under the button, pulled left if it would run off-screen. */
  const anchor = useCallback(() => {
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(MAX_W, window.innerWidth - MARGIN * 2);
    const left = Math.min(
      Math.max(MARGIN, rect.left),
      Math.max(MARGIN, window.innerWidth - width - MARGIN),
    );
    setBox({ top: rect.bottom + GAP, left, width });
  }, []);

  useLayoutEffect(() => {
    if (open) anchor();
  }, [open, anchor]);

  /** Escape closes, an outside click closes, and resize or scroll re-anchors. */
  useEffect(() => {
    if (!open) return;

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    function onDown(event: MouseEvent) {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", anchor);
    // Capture, so a scroll inside the rail re-anchors too, not just the page.
    window.addEventListener("scroll", anchor, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", anchor);
      window.removeEventListener("scroll", anchor, true);
    };
  }, [open, anchor]);

  /** Opening puts the caret in the filter, which is where typing should go. */
  useEffect(() => {
    if (open) field.current?.focus();
    else setQuery("");
  }, [open]);

  const needle = query.replace(/\D/g, "");
  const shown = needle
    ? episodes.filter((entry) => String(entry.number).startsWith(needle))
    : episodes;

  const label = episode === ALL_EPISODES ? "All episodes" : `Episode ${episode}`;
  const withPromos = episodes.filter((entry) => entry.promos > 0).length;
  const blocked = loading && episodes.length === 0;

  function choose(next: number | typeof ALL_EPISODES) {
    onEpisode(next);
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <div className="pf-pick" ref={wrap}>
      <button
        ref={trigger}
        type="button"
        className={`pf-pick-btn${open ? " is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        disabled={blocked}
      >
        <span className="pf-pick-btn-text">
          <span className="pf-pick-btn-label">{label}</span>
          <span className="pf-pick-btn-sub">
            {blocked
              ? "loading the run"
              : `${withPromos} of ${episodes.length} shipped a promo`}
          </span>
        </span>
        <span className="pf-pick-caret" data-open={open}>
          <Icon name="chevron-down" />
        </span>
      </button>

      {open && box && (
        <div
          className="pf-pick-menu"
          style={{ top: box.top, left: box.left, width: box.width }}
        >
          <div className="pf-pick-search">
            <span className="pf-pick-search-i">
              <Icon name="search" />
            </span>
            <input
              ref={field}
              type="text"
              className="pf-pick-input"
              inputMode="numeric"
              autoComplete="off"
              placeholder="Jump to an episode number"
              aria-label="Filter episodes by number"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {query.length > 0 && (
              <button
                type="button"
                className="pf-iconbtn"
                aria-label="Clear the filter"
                onClick={() => {
                  setQuery("");
                  field.current?.focus();
                }}
              >
                <Icon name="close" />
              </button>
            )}
          </div>

          <div className="pf-pick-scroll">
            {needle.length === 0 && (
              <button
                type="button"
                className={`pf-ep pf-ep-all${episode === ALL_EPISODES ? " is-on" : ""}`}
                onClick={() => choose(ALL_EPISODES)}
              >
                <span className="pf-ep-tick">
                  {episode === ALL_EPISODES && <Icon name="check" />}
                </span>
                <span className="pf-ep-name">All episodes</span>
                <span className="pf-ep-count">{kept}</span>
              </button>
            )}

            <div className="pf-pick-grid">
              {shown.map((entry) => {
                const on = episode === entry.number;
                const none = entry.promos === 0;
                return (
                  <button
                    key={entry.number}
                    type="button"
                    className={`pf-ep${on ? " is-on" : ""}${none ? " is-none" : ""}`}
                    onClick={() => choose(entry.number)}
                  >
                    <span className="pf-ep-tick">{on && <Icon name="check" />}</span>
                    <span className="pf-ep-name">
                      Ep <span className="pf-ep-n">{entry.number}</span>
                    </span>
                    {none ? (
                      <span className="pf-ep-none">none</span>
                    ) : (
                      <>
                        <span className="pf-ep-best">{entry.best?.toFixed(2)}</span>
                        <span className="pf-ep-count">{entry.promos}</span>
                      </>
                    )}
                  </button>
                );
              })}
            </div>

            {shown.length === 0 && (
              <p className="pf-pick-empty">No episode numbered {needle}.</p>
            )}
          </div>

          <p className="pf-pick-foot">
            A cell reading <strong>none</strong> is a result: the gates and the
            rubric floor declined every candidate from that episode. The other
            number is the episode's best weighted score.
          </p>
        </div>
      )}
    </div>
  );
}
