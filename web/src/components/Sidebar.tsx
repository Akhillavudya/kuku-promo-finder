/**
 * The left rail: navigation, the run's headline numbers, the season behind a
 * picker, and the live runs you have already made.
 *
 * It used to end in a 51-row episode list, which made the rail itself the
 * tallest column on the page and the only one that scrolled. Two changes
 * fixed that, and both are visible here:
 *
 *   - The season goes behind `EpisodePicker`, a closed-by-default dropdown.
 *     The rail now fits a laptop viewport with the provider line and the
 *     rights note still on screen, which is where they belong - they are the
 *     two things a reader of this assignment should not have to scroll for.
 *   - Live runs are kept, so the rail carries a short history instead of
 *     being purely outbound navigation. Clicking one restores its result
 *     without a model call.
 *
 * The live-runs group only appears once there is something in it. An empty
 * "Live runs (0)" group would be chrome advertising a feature rather than
 * showing state.
 */

import Icon from "./Icon";
import EpisodePicker from "./EpisodePicker";
import type { HealthResponse, ProfileInfo, RunSummary } from "../types";
import { runTime, type LiveRun } from "../history";
import { ALL_EPISODES, type EpisodeEntry, type ViewId } from "../nav";

// Declared in ../nav so EpisodePicker can import them without the two files
// importing each other. Re-exported because App imports them from here.
export { ALL_EPISODES } from "../nav";
export type { EpisodeEntry, ViewId } from "../nav";

const NAV: { id: ViewId; label: string; hint: string }[] = [
  { id: "season", label: "Season", hint: "All 50 episodes, ranked" },
  { id: "live", label: "Run live", hint: "Paste one episode" },
  { id: "method", label: "Method and limits", hint: "How it decides, where it fails" },
];

interface Props {
  view: ViewId;
  onView: (view: ViewId) => void;
  episodes: EpisodeEntry[];
  episode: number | typeof ALL_EPISODES;
  onEpisode: (episode: number | typeof ALL_EPISODES) => void;
  summary: RunSummary;
  health: HealthResponse | null;
  loading: boolean;
  runs: LiveRun[];
  /** Which stored run the Run live view currently has open, if any. */
  activeRun: string | null;
  onOpenRun: (run: LiveRun) => void;
  onDeleteRun: (id: string) => void;
  onClearRuns: () => void;
  /** The profile the live run will use, as `/api/profiles` described it. */
  selected: ProfileInfo | null;
  /** True when every provider that profile needs has a key - pasted here or
   *  already set on the server. */
  keyReady: boolean;
  /** Whether the key that makes `keyReady` true came from this browser. */
  keyFromBrowser: boolean;
  onOpenSettings: () => void;
}

const COST_LABEL: Record<ProfileInfo["cost"], string> = {
  free: "Free",
  paid: "Paid",
  local: "Local",
};

/** A number that has not arrived yet: a dimmed bar, never an em dash. */
function Pending() {
  return <span className="pf-skel" role="img" aria-label="loading" />;
}

export default function Sidebar({
  view,
  onView,
  episodes,
  episode,
  onEpisode,
  summary,
  health,
  loading,
  runs,
  activeRun,
  onOpenRun,
  onDeleteRun,
  onClearRuns,
  selected,
  keyReady,
  keyFromBrowser,
  onOpenSettings,
}: Props) {
  const kept = summary.n_promos ?? 0;
  const total = summary.n_episodes ?? episodes.length;
  const withPromos = episodes.filter((entry) => entry.promos > 0).length;
  const spend = summary.spend?.usd_total ?? 0;

  // The rail names the *profile*, not the model: 272px of rail truncates
  // `gemini-3.5-flash-lite` to an ellipsis, and a half-printed model id is
  // worse than none. The models are one hover away in the title, and spelt
  // out in full in the dialog and beside the Find promos button.
  const models = [...new Set((selected?.tiers ?? []).map((tier) => tier.model))];
  const modelTitle = models.join("  +  ");
  const profileLine = selected?.id ?? (health ? "default profile" : "loading");
  const keyLine = !selected
    ? ""
    : selected.keys.length === 0
      ? "no key needed"
      : keyFromBrowser
        ? "your key"
        : keyReady
          ? "server key"
          : "no key yet";

  return (
    <aside className="pf-rail">
      <div className="pf-rail-brand">
        <span className="pf-mark" aria-hidden="true">
          <span className="pf-mark-track">
            <span className="pf-mark-seg" />
          </span>
        </span>
        <span className="pf-brand-text">
          <span className="pf-brand-name">Promo finder</span>
          <span className="pf-brand-sub">
            Screenplays <Icon name="arrow-right" /> 20&#8211;60s cuts
          </span>
        </span>
      </div>

      <div className="pf-rail-scroll">
        <nav className="pf-nav" aria-label="Views">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pf-nav-item${item.id === view ? " is-on" : ""}`}
              aria-current={item.id === view ? "page" : undefined}
              onClick={() => onView(item.id)}
            >
              <span className="pf-nav-label">{item.label}</span>
              <span className="pf-nav-hint">{item.hint}</span>
            </button>
          ))}
        </nav>

        {/*
          These group labels are deliberately not headings. The rail sits
          before <main> in the document, so an h2 here would land above the
          page's h1 and put the heading outline out of order for a screen
          reader. They are field-group labels; the groups they name carry
          their own accessible names instead.
        */}
        <div className="pf-rail-group">
          <p className="pf-rail-h">Episodes</p>
          <EpisodePicker
            episodes={episodes}
            episode={episode}
            onEpisode={onEpisode}
            kept={kept}
            loading={loading}
          />
        </div>

        <div className="pf-rail-group">
          <p className="pf-rail-h">This run</p>
          <dl className="pf-railstats" aria-label="Run totals">
            <div className="pf-railstat">
              <dt>Promos kept</dt>
              <dd>{loading ? <Pending /> : kept}</dd>
            </div>
            <div className="pf-railstat">
              <dt>Episodes used</dt>
              <dd>{loading ? <Pending /> : `${withPromos} of ${total}`}</dd>
            </div>
            <div className="pf-railstat">
              <dt>Model spend</dt>
              <dd>{loading ? <Pending /> : `$${spend.toFixed(2)}`}</dd>
            </div>
            <div className="pf-railstat">
              <dt>Wall clock</dt>
              <dd>{loading ? <Pending /> : `${(summary.elapsed_s ?? 0).toFixed(0)}s`}</dd>
            </div>
          </dl>
        </div>

        {runs.length > 0 && (
          <div className="pf-rail-group">
            <div className="pf-rail-grouphead">
              <p className="pf-rail-h">Live runs</p>
              <button type="button" className="pf-textbtn" onClick={onClearRuns}>
                Clear
              </button>
            </div>
            <ul className="pf-runs" aria-label="Live runs you have made">
              {runs.map((run) => {
                const on = run.id === activeRun && view === "live";
                const stamp = runTime(run.at);
                return (
                  <li className="pf-run" key={run.id}>
                    <button
                      type="button"
                      className={`pf-run-open${on ? " is-on" : ""}`}
                      aria-current={on ? "true" : undefined}
                      onClick={() => onOpenRun(run)}
                    >
                      <span className="pf-run-name">{run.label}</span>
                      <span className="pf-run-meta">
                        <span className="pf-run-at">{stamp}</span>
                        {run.result.ok ? (
                          <span className="pf-run-tally">
                            {run.kept} of {run.considered}
                          </span>
                        ) : (
                          <span className="pf-run-failed">failed</span>
                        )}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="pf-iconbtn pf-run-del"
                      aria-label={"Forget the " + run.label.toLowerCase() + " from " + stamp}
                      onClick={() => onDeleteRun(run.id)}
                    >
                      <Icon name="close" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {/*
        The foot is the account row's job in most apps; here the thing worth
        showing in that slot is which model a live run would call and what it
        costs. The Free/Paid/Local tag is not decorative - it is read from
        the chosen profile's providers (`is_paid` in promo/config.py), so
        picking Claude turns the rail red-tagged Paid without anything here
        knowing what Claude is.
      */}
      <div className="pf-rail-foot">
        <div className="pf-account">
          <span className="pf-avatar" data-cost={selected?.cost ?? "free"} aria-hidden="true">
            <Icon name="spark" />
          </span>
          <span className="pf-account-text">
            <span className="pf-account-name" title={modelTitle}>
              {profileLine}
            </span>
            <span className="pf-account-sub">
              <span className="pf-tag" data-cost={selected?.cost ?? "free"}>
                {selected ? COST_LABEL[selected.cost] : "Free"}
              </span>
              <span className="pf-account-key">{keyLine}</span>
            </span>
          </span>
          <button
            type="button"
            className="pf-btn pf-btn-pill"
            onClick={onOpenSettings}
            aria-label="Settings: choose the model and paste an API key"
          >
            <Icon name="settings" />
            Settings
          </button>
        </div>
        <p className="pf-rail-note">
          Hook and cliffhanger lines are quoted from the pack. The screenplays
          themselves are neither committed nor deployed.
        </p>
      </div>
    </aside>
  );
}
