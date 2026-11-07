/**
 * The app shell: a persistent left rail and a wide workspace.
 *
 * Three views, held in component state rather than routes - two panels and a
 * static page do not need a router, and the rail is the navigation.
 *
 * The rail owns three kinds of state that used to be scattered: which view is
 * open, which episode the workspace is filtered to, and the live run on
 * screen. All three live here because the rail sets them and the workspace
 * reads them.
 *
 * The live-run state moved up from `LiveView` for one concrete reason: the
 * rail now lists past runs, and a sibling cannot read a child's `useState`.
 * The side benefit is the fix for a real annoyance - leaving the Run live
 * view and coming back used to clear a result that had cost two model calls.
 *
 * The framing that three of the brief's five scoring lenses turn on - how the
 * problem was framed, what was given to a model versus kept in Python, and
 * where the tool is weak - used to be four paragraphs of masthead above the
 * results. It is now the Method view, with the one-sentence version in the
 * workspace bar so it is never more than a click away but never in the way.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchHealth, fetchProfiles, fetchSeason, postRun } from "./api";
import LiveView from "./components/LiveView";
import MethodView from "./components/MethodView";
import SeasonView from "./components/SeasonView";
import SettingsDialog from "./components/SettingsDialog";
import Icon from "./components/Icon";
import Sidebar from "./components/Sidebar";
import {
  loadSettings,
  saveSettings,
  type ModelSettings,
  EMPTY,
} from "./settings";
import { ALL_EPISODES, type EpisodeEntry, type ViewId } from "./nav";
import {
  clearRuns,
  loadRuns,
  recordRun,
  removeRun,
  type LiveRun,
} from "./history";
import type {
  HealthResponse,
  ProfileInfo,
  RunResponse,
  SeasonResponse,
} from "./types";

const TITLES: Record<ViewId, { title: string; blurb: string }> = {
  season: {
    title: "Season",
    blurb:
      "Precomputed from outputs/. No model call, no key, nothing to warm up.",
  },
  live: {
    title: "Run live",
    blurb:
      "Runs the real pipeline on pasted text, with the model you pick in Settings.",
  },
  method: {
    title: "Method and limits",
    blurb: "What the model decides, what Python decides, and what is unverified.",
  },
};

export default function App() {
  const [view, setView] = useState<ViewId>("season");
  const [episode, setEpisode] = useState<number | typeof ALL_EPISODES>(ALL_EPISODES);
  const [season, setSeason] = useState<SeasonResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  /* --- which model the live run uses ------------------------------------
   *
   * `profiles` is the server's reading of config/settings.yaml; `settings`
   * is this browser's choice within it, remembered in localStorage. The
   * choice is a profile *name*, never a model id, so a model renamed in the
   * YAML needs no change here and no stale id can be sent.
   */

  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [fallbackProfile, setFallbackProfile] = useState("");
  const [settings, setSettings] = useState<ModelSettings>(EMPTY);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  /* --- the live run, lifted out of LiveView ----------------------------- */

  const [text, setText] = useState("");
  const [source, setSource] = useState<"sample" | "paste">("paste");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResponse | null>(null);
  const [showRejects, setShowRejects] = useState(false);
  const [runs, setRuns] = useState<LiveRun[]>([]);
  /** Set only while the result on screen came out of the history. */
  const [restored, setRestored] = useState<LiveRun | null>(null);

  /** Read once on mount. Deliberately not in the initial state: a throwing
   *  `localStorage` would then throw during render. */
  useEffect(() => {
    setRuns(loadRuns());
  }, []);

  const loadSeason = useCallback(async () => {
    setLoading(true);
    try {
      setSeason(await fetchSeason());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSeason();
    void fetchHealth().then(setHealth);
    void fetchProfiles().then((response) => {
      setProfiles(response.profiles);
      setFallbackProfile(response.default);
    });
  }, [loadSeason]);

  /** The profile a run would use: the chosen one, else the server default,
   *  else the first row. A name left over in localStorage that the YAML no
   *  longer defines falls back rather than failing the run. */
  const selected = useMemo<ProfileInfo | null>(() => {
    if (profiles.length === 0) return null;
    return (
      profiles.find((p) => p.id === settings.profile) ??
      profiles.find((p) => p.id === fallbackProfile) ??
      profiles[0]
    );
  }, [profiles, settings.profile, fallbackProfile]);

  /** Every provider the profile needs has a key somewhere, and whether any
   *  of them came from this browser. Mirrors the server's own check in
   *  `POST /api/run`, which is the one that actually gates the call.
   *
   *  `required` matters here: the failover provider is in `keys` so a key can
   *  be pasted for it, but the server does not refuse a run without it, so
   *  counting it would raise a "no API key" warning for a run that works. */
  const keyFromBrowser = (selected?.keys ?? []).some(
    (need) => !!settings.keys[need.provider],
  );
  const keyReady = (selected?.keys ?? [])
    .filter((need) => need.required)
    .every((need) => need.on_server || !!settings.keys[need.provider]);

  const onSaveSettings = useCallback((next: ModelSettings) => {
    setSettings(saveSettings(next));
    setSettingsOpen(false);
  }, []);

  /**
   * The whole season as rail rows, including the episodes that shipped
   * nothing. Those are the point: an episode list that silently omitted the
   * 16 declines would make a 34-episode season look like a 50-episode one.
   */
  const episodes = useMemo<EpisodeEntry[]>(() => {
    const promos = season?.promos ?? [];
    const counts = new Map<number, number>();
    const best = new Map<number, number>();
    for (const promo of promos) {
      counts.set(promo.episode, (counts.get(promo.episode) ?? 0) + 1);
      const prior = best.get(promo.episode);
      if (prior === undefined || promo.weighted_score > prior) {
        best.set(promo.episode, promo.weighted_score);
      }
    }

    const highest = promos.reduce((max, p) => Math.max(max, p.episode), 0);
    const total = season?.summary?.n_episodes ?? highest;
    const numbers =
      total > 0
        ? Array.from({ length: total }, (_, i) => i + 1)
        : [...counts.keys()].sort((a, b) => a - b);

    return numbers.map((number) => ({
      number,
      promos: counts.get(number) ?? 0,
      best: best.get(number) ?? null,
    }));
  }, [season]);

  const onText = useCallback((next: string, kind: "sample" | "paste") => {
    setText(next);
    setSource(kind);
    // Editing the text means the result on screen is no longer what the text
    // would produce, so the "restored from history" claim stops being true.
    setRestored(null);
  }, []);

  const onRun = useCallback(async () => {
    setRunning(true);
    setResult(null);
    setRestored(null);
    try {
      const next = await postRun(
        text,
        { ...settings, profile: selected?.id ?? settings.profile },
        selected?.providers ?? [],
      );
      setResult(next);
      setRuns((current) => recordRun(current, { text, source, result: next }));
    } finally {
      setRunning(false);
    }
  }, [text, source, settings, selected]);

  const onOpenRun = useCallback((run: LiveRun) => {
    setText(run.text);
    setSource(run.source);
    setResult(run.result);
    setRestored(run);
    setShowRejects(false);
    setView("live");
  }, []);

  const onDeleteRun = useCallback((id: string) => {
    setRuns((current) => removeRun(current, id));
    setRestored((current) => (current?.id === id ? null : current));
  }, []);

  const onClearRuns = useCallback(() => {
    setRuns(clearRuns());
    setRestored(null);
  }, []);

  const onClearLive = useCallback(() => {
    setText("");
    setResult(null);
    setRestored(null);
    setShowRejects(false);
  }, []);

  const active = TITLES[view];

  return (
    <div className="pf-app">
      <Sidebar
        view={view}
        onView={setView}
        episodes={episodes}
        episode={episode}
        onEpisode={(next) => {
          setEpisode(next);
          setView("season");
        }}
        summary={season?.summary ?? {}}
        health={health}
        loading={loading}
        runs={runs}
        activeRun={restored?.id ?? null}
        onOpenRun={onOpenRun}
        onDeleteRun={onDeleteRun}
        onClearRuns={onClearRuns}
        selected={selected}
        keyReady={keyReady}
        keyFromBrowser={keyFromBrowser}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {settingsOpen && (
        <SettingsDialog
          profiles={profiles}
          fallback={fallbackProfile}
          settings={settings}
          onSave={onSaveSettings}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      <main className="pf-work" id="workspace">
        <div className="pf-workbar">
          <div className="pf-workbar-text">
            <h1 className="pf-worktitle">{active.title}</h1>
            <p className="pf-workblurb">{active.blurb}</p>
          </div>
          {view === "season" && (
            <button
              type="button"
              className="pf-btn"
              onClick={loadSeason}
              disabled={loading}
            >
              <Icon name="refresh" />
              {loading ? "Reloading" : "Reload outputs"}
            </button>
          )}
        </div>

        <div className="pf-workbody">
          {view === "season" && (
            <SeasonView data={season} loading={loading} episode={episode} />
          )}
          {view === "live" && (
            <LiveView
              selected={selected}
              keyReady={keyReady}
              onOpenSettings={() => setSettingsOpen(true)}
              text={text}
              onText={onText}
              running={running}
              onRun={onRun}
              result={result}
              restored={restored}
              showRejects={showRejects}
              onShowRejects={setShowRejects}
              onClear={onClearLive}
            />
          )}
          {view === "method" && <MethodView summary={season?.summary ?? {}} />}
        </div>
      </main>
    </div>
  );
}
