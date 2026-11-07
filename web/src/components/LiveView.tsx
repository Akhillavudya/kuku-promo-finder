/**
 * The live run. Paste one episode, get promos back.
 *
 * Calls POST /api/run, which runs **the same functions in the same order** as
 * `python -m promo.run`: propose candidates, deterministic gates, score,
 * select. It is not a reimplementation for the demo, it is
 * promo.run.run_episode - which is the only reason the numbers on this view
 * can be trusted to match the ones on the Season view.
 *
 * The promos here carry no rank badge. The ordering is within one pasted
 * episode, so a season-wide "#1" would be a lie.
 *
 * The sample episode is **synthetic**, written for this demo so the view
 * works for anyone, including a reader without the screenplays. No real
 * episode is ever served here.
 *
 * This view owns no state any more. The textarea, the result and which
 * stored run is open all live in `App`, because the rail lists the history
 * and the rail is a sibling. The practical effect is that switching to the
 * Season view and back no longer throws away a run that cost two model
 * calls.
 */

import { fetchSample } from "../api";
import type { ProfileInfo, RunResponse } from "../types";
import type { LiveRun } from "../history";
import Icon from "./Icon";
import Notice from "./Notice";
import PromoCard from "./PromoCard";
import RejectionList from "./RejectionList";

interface Props {
  /** The profile the run will use, chosen in the sidebar's Settings. */
  selected: ProfileInfo | null;
  /** Every provider it needs has a key, here or on the server. */
  keyReady: boolean;
  onOpenSettings: () => void;
  text: string;
  onText: (text: string, source: "sample" | "paste") => void;
  running: boolean;
  onRun: () => void;
  result: RunResponse | null;
  /** The stored run currently on screen, if this result came from history. */
  restored: LiveRun | null;
  showRejects: boolean;
  onShowRejects: (open: boolean) => void;
  onClear: () => void;
}

export default function LiveView({
  selected,
  keyReady,
  onOpenSettings,
  text,
  onText,
  running,
  onRun,
  result,
  restored,
  showRejects,
  onShowRejects,
  onClear,
}: Props) {
  async function onSample() {
    const sample = await fetchSample();
    if (sample) onText(sample, "sample");
  }

  const episode = result?.episode;

  return (
    <>
      {/*
        The key warning names the provider the *chosen* profile needs, not a
        fixed one: selecting Claude and being told about GEMINI_API_KEY would
        send a reader to fix the wrong thing. `keyReady` mirrors the check in
        POST /api/run, which is the one that actually stops the call.
      */}
      {selected && !keyReady && (
        <Notice kind="warn">
          No API key for{" "}
          <strong>
            {selected.keys
              .filter((need) => !need.on_server)
              .map((need) => need.provider)
              .join(", ")}
          </strong>
          , so a live run on the <code>{selected.id}</code> profile will stop
          before it calls a model. Paste one under{" "}
          <button type="button" className="pf-linkbtn" onClick={onOpenSettings}>
            Settings
          </button>{" "}
          in the sidebar, or set the environment variable on the server. The
          Season view needs no key at all.
        </Notice>
      )}

      {restored && (
        <Notice>
          Showing the <strong>{restored.label.toLowerCase()}</strong> you ran
          earlier, restored from this browser. No model was called.
          {restored.truncated && (
            <>
              {" "}
              The stored copy of the text was trimmed to fit, so re-running it
              would not use the whole episode.
            </>
          )}
        </Notice>
      )}

      <section className="pf-panel">
        <h2 className="pf-panel-h">
          Paste one episode
          <span className="pf-panel-sub">
            each block is a <code>**HEADER:**</code> line, then{" "}
            <code>Start: (MM:SS.ss) | End: (MM:SS.ss)</code>
          </span>
        </h2>

        <label className="pf-field pf-field-block">
          <span className="pf-label">Screenplay text</span>
          <textarea
            className="pf-textarea"
            value={text}
            rows={12}
            spellCheck={false}
            onChange={(event) => onText(event.target.value, "paste")}
            placeholder={
              '**NADIA (Flat, unsurprised):**\nStart: (00:04.30) | End: (00:07.80)\n"Third one this month. You people do not knock."'
            }
          />
        </label>

        <div className="pf-controls">
          <button
            type="button"
            className="pf-btn pf-btn-primary"
            onClick={onRun}
            disabled={running || text.trim().length === 0}
          >
            {running ? (
              <>
                <span className="pf-spin" aria-hidden="true" />
                Finding promos
              </>
            ) : (
              <>
                <Icon name="spark" />
                Find promos
              </>
            )}
          </button>
          <button
            type="button"
            className="pf-btn"
            onClick={onSample}
            disabled={running}
          >
            <Icon name="document" />
            Load sample episode
          </button>
          {(text.length > 0 || result) && (
            <button
              type="button"
              className="pf-btn pf-btn-quiet"
              onClick={onClear}
              disabled={running}
            >
              <Icon name="close" />
              Clear
            </button>
          )}
          <span className="pf-hint">
            {text.length > 0 ? `${text.length.toLocaleString()} characters` : ""}
          </span>
          {selected && (
            <button
              type="button"
              className="pf-runmodel"
              onClick={onOpenSettings}
              aria-label={`Model: ${selected.id}. Open settings to change it.`}
            >
              <Icon name="settings" />
              <span>
                {[...new Set(selected.tiers.map((tier) => tier.model))].join(" + ")}
              </span>
              <span className="pf-tag" data-cost={selected.cost}>
                {selected.cost === "paid"
                  ? "Paid"
                  : selected.cost === "local"
                    ? "Local"
                    : "Free"}
              </span>
            </button>
          )}
        </div>
      </section>

      {running && (
        <Notice>
          Two model calls: one proposes candidate spans as block indices, one
          scores the survivors on four axes. On a free tier this takes a few
          seconds.
        </Notice>
      )}

      {result && !result.ok && <Notice kind="warn">{result.error}</Notice>}

      {result?.ok && episode && (
        <Notice>
          Parsed <strong>{episode.n_blocks}</strong> blocks (
          {episode.n_content_blocks} dialogue or ACTION, the only kinds the 3s
          hook gate accepts) spanning {episode.duration_s.toFixed(0)}s. The model
          proposed {result.promos.length + result.rejected.length} candidates;{" "}
          {result.rejected.length} failed a deterministic gate;{" "}
          {result.promos.length} survived scoring and the rubric floor.
          {result.profile && (
            <>
              {" "}
              Ran on <code>{result.profile}</code>.
            </>
          )}
        </Notice>
      )}

      {result?.ok && result.promos.length === 0 && (
        <Notice kind="warn">
          No promo from this episode cleared the gates and the rubric floor.
          That is a real answer, not a failure: open the rejections below to
          see which gate stopped each candidate.
        </Notice>
      )}

      {result?.ok && result.promos.length > 0 && (
        <section className="pf-epbox">
          <header className="pf-epbox-head">
            <h2 className="pf-epbox-id">
              {restored ? restored.label : "Pasted episode"}
            </h2>
            <div className="pf-epbox-meta">
              <span className="pf-epbox-tally">
                {result.promos.length} kept of{" "}
                {result.promos.length + result.rejected.length} considered
              </span>
            </div>
          </header>
          <div className="pf-epbox-body">
            {result.promos.map((promo) => (
              <PromoCard key={promo.id} promo={promo} />
            ))}
          </div>
        </section>
      )}

      {result?.ok && result.rejected.length > 0 && (
        <section className="pf-panel">
          <button
            type="button"
            className="pf-disclosure"
            aria-expanded={showRejects}
            onClick={() => onShowRejects(!showRejects)}
          >
            <span className="pf-disclosure-mark" data-open={showRejects}>
              <Icon name="chevron-right" />
            </span>
            Candidates that did not ship ({result.rejected.length})
          </button>
          {showRejects && <RejectionList rejections={result.rejected} />}
        </section>
      )}
    </>
  );
}
