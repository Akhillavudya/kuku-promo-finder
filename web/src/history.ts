/**
 * The live-run history: the last few runs, kept so clicking one back costs
 * nothing.
 *
 * Two reasons this is worth the ~60 lines. A live run is two model calls on a
 * free tier, so re-running the same paste to look at it again is a few
 * seconds and a quota hit for an answer already in hand. And switching to the
 * Season view and back used to clear the textarea and the result outright,
 * which made the view feel like it had failed.
 *
 * Where it lives: `localStorage`, so it survives a reload, and only in the
 * reader's own browser. It never reaches the server, and the server never
 * writes it. That matters because a run's `text` is a screenplay someone
 * pasted - under hard rule 5 the pack is never committed and never deployed,
 * and a key in the reader's own browser is neither.
 *
 * Every read and write is wrapped. `localStorage` throws outright in a
 * private window with site data blocked, and `setItem` throws on quota, so
 * both have to be survivable: a failed read yields an empty history and a
 * failed write drops the oldest entry and tries once more. Nothing here is
 * load-bearing - the app works identically with the history permanently
 * empty.
 */

import type { RunResponse } from "./types";

const KEY = "pf.liveruns.v2";

/** Past this many, the oldest is dropped. Twelve is more than a demo needs. */
const CAP = 12;

/**
 * A long paste is kept only up to this, because the whole history shares one
 * ~5MB origin quota and a 120k-character episode times twelve would not fit.
 * A truncated entry still restores its result in full; only re-running it
 * from the restored textarea would be short, so `truncated` says so and the
 * UI warns.
 */
const MAX_TEXT = 24000;

export interface LiveRun {
  id: string;
  /** "Sample episode" or "Pasted episode" - what the row reads. */
  label: string;
  source: "sample" | "paste";
  /** Epoch ms. Formatted at render time, in the reader's own locale. */
  at: number;
  text: string;
  truncated: boolean;
  /** Denormalised so a row shows its tally without walking the result. */
  kept: number;
  considered: number;
  result: RunResponse;
}

function newId(): string {
  // randomUUID is absent on http:// origins in some browsers, so this falls
  // back rather than throwing on a LAN preview.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `r${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function loadRuns(): LiveRun[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Anything in storage is untrusted: it may be from an older shape.
    return parsed.filter(
      (entry): entry is LiveRun =>
        !!entry &&
        typeof entry === "object" &&
        typeof (entry as LiveRun).id === "string" &&
        typeof (entry as LiveRun).at === "number" &&
        !!(entry as LiveRun).result,
    );
  } catch {
    return [];
  }
}

function save(runs: LiveRun[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(runs));
  } catch {
    // Almost always quota. Shed the older half and accept losing it.
    try {
      localStorage.setItem(KEY, JSON.stringify(runs.slice(0, 3)));
    } catch {
      /* storage is unavailable; the history is in memory only this session */
    }
  }
}

export function recordRun(
  runs: LiveRun[],
  input: { text: string; source: "sample" | "paste"; result: RunResponse },
): LiveRun[] {
  const kept = input.result.promos?.length ?? 0;
  const considered = kept + (input.result.rejected?.length ?? 0);
  const entry: LiveRun = {
    id: newId(),
    label: input.source === "sample" ? "Sample episode" : "Pasted episode",
    source: input.source,
    at: Date.now(),
    text: input.text.slice(0, MAX_TEXT),
    truncated: input.text.length > MAX_TEXT,
    kept,
    considered,
    result: input.result,
  };
  const next = [entry, ...runs].slice(0, CAP);
  save(next);
  return next;
}

export function removeRun(runs: LiveRun[], id: string): LiveRun[] {
  const next = runs.filter((run) => run.id !== id);
  save(next);
  return next;
}

export function clearRuns(): LiveRun[] {
  save([]);
  return [];
}

/** "14:02" in the reader's locale, or the date once it is not today. */
export function runTime(at: number): string {
  const when = new Date(at);
  const today = new Date();
  const sameDay =
    when.getFullYear() === today.getFullYear() &&
    when.getMonth() === today.getMonth() &&
    when.getDate() === today.getDate();
  return sameDay
    ? when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : when.toLocaleDateString([], { month: "short", day: "numeric" });
}
