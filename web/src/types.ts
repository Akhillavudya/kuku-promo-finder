/**
 * The shapes `api/main.py` serves, which are the shapes `promo.run` writes.
 *
 * Mirrored by hand rather than generated: there are five of them, they are
 * settled, and a codegen step on a 48-hour assignment is the kind of
 * machinery the brief scores against. The one thing that must not drift is
 * `Promo` - it is `Candidate.to_dict()` in `src/promo/run.py`, field for
 * field, and `episode_duration_s` is what the timeline is scaled by.
 */

/** The four rubric axes, in `config/rubric.yaml` order. */
export const AXES = [
  "hook_strength",
  "cliffhanger",
  "standalone",
  "emotional_charge",
] as const;

export type Axis = (typeof AXES)[number];

/**
 * Hook categories, from `schemas.HOOK_TYPES` (D19). Editor-facing metadata:
 * never scored, never weighted, never gated, and not shown to the scoring
 * model at all. `""` means the model returned no label, which is tracked
 * separately from `"other"` on purpose.
 */
export const HOOK_TYPES = [
  "accusation",
  "reveal",
  "threat",
  "violence",
  "defiance",
  "anguish",
  "humiliation",
  "intrusion",
  "romance",
  "other",
] as const;

export type HookType = (typeof HOOK_TYPES)[number];

/** One continuous stretch, already resolved from block indices to seconds. */
export interface Segment {
  start_block: number;
  end_block: number;
  /** `MM:SS.ss`, formatted by Python. Never reformatted here. */
  start: string;
  end: string;
  start_s: number;
  end_s: number;
  duration_s: number;
}

/** `Candidate.to_dict()`. Every number here was computed in Python. */
export interface Promo {
  id: string;
  episode: number;
  duration_s: number;
  /** The episode's own length, so a timeline can be scaled without the pack. */
  episode_duration_s?: number;
  segments: Segment[];
  hook: string;
  /** A `HookType`, or `""` when the model returned no label. Not a score. */
  hook_type: HookType | "";
  cliffhanger: string;
  why: string;
  weakness: string;
  needs_to_know: string;
  scores: Partial<Record<Axis, number>>;
  weighted_score: number;
  /** Every raw axis table, one per rank pass (rule 4). `scores` is their mean. */
  score_passes?: Partial<Record<Axis, number>>[];
  /** Axes a rank response never answered, silently clamped to 1
   *  (ACCURACY #6). Normally empty; non-empty means a provider or
   *  prompt fault, not a low score. */
  missing_axes?: Axis[];
  /** Highest minus lowest weighted total across the passes: the error bar. */
  score_spread?: number;
  /** The block that satisfied the 3s hook gate, and how far in it starts. */
  hook_block: number | null;
  hook_offset_s: number | null;
  duration_adjustment: string | null;
}

export interface Spend {
  calls?: number;
  cached_calls?: number;
  usd_total?: number;
  by_model?: Record<string, { tokens_in: number; tokens_out: number; usd: number }>;
}

/** `run_summary.json`. The unflattering fields are not optional by accident. */
export interface RunSummary {
  profile?: string;
  finished_at?: string;
  elapsed_s?: number;
  n_episodes?: number;
  n_promos?: number;
  n_candidates_proposed?: number;
  n_passed_gates?: number;
  n_rejected_by_gates?: number;
  n_unscored?: number;
  rejections_by_gate?: Record<string, number>;
  episodes_with_no_promo?: number[];
  n_episodes_with_no_promo?: number;
  duration_repairs?: number;
  /** How many independent scoring passes ran per candidate. More than one is
   *  what makes `score_spread` meaningful. */
  rank_passes?: number;
  rank_batch?: number;
  /**
   * How far the independent rank passes disagreed, in weighted points. This
   * is the only stability number the run produces and it is not flattering,
   * so it is surfaced rather than filed: the median is the error bar to read
   * every individual score against.
   */
  score_spread?: {
    n_multi_pass?: number;
    median?: number;
    mean?: number;
    max?: number;
    n_over_1_point?: number;
    worst?: { id: string; spread: number; passes: Partial<Record<Axis, number>>[] }[];
  };
  spend?: Spend;
  rubric?: {
    weights?: Record<string, number>;
    min_score?: number;
    max_promos_per_episode?: number;
  };
}

export interface GateFailure {
  gate: string;
  detail: string;
}

/**
 * The four selection rules, and the numbers behind whichever one fired.
 *
 * `min_cliffhanger` and `min_score` are absolute: a score against a floor.
 * `dedup` and `episode_cap` are relative - the candidate was fine and simply
 * lost to a better one - so they carry the winner. Present only on a
 * selection drop; a gate rejection has no `selection` key at all.
 */
export interface SelectionDrop {
  rule: "min_cliffhanger" | "min_score" | "dedup" | "episode_cap";
  cliffhanger?: number;
  weighted_score?: number;
  floor?: number;
  lost_to?: string;
  overlap?: number;
  threshold?: number;
  place_in_episode?: number;
  cap?: number;
}

/**
 * One candidate that did not ship, with the measured number that stopped it.
 *
 * Two populations share this shape. A **gate** rejection never reached a
 * scorer; a **selection** drop passed every gate, was scored, and lost on
 * quality, duplication or the per-episode cap. The batch run keeps them under
 * separate keys in `rejected.json`; `POST /api/run` returns them in one list,
 * so `selection` is how a client tells them apart.
 */
export interface Rejection {
  id: string;
  episode: number;
  hook?: string;
  duration_s?: number;
  segments?: Segment[];
  duration_adjustment?: string | null;
  scores?: Record<string, number>;
  weighted_score?: number;
  failures: GateFailure[];
  selection?: SelectionDrop;
}

export interface SeasonResponse {
  ok: boolean;
  error?: string;
  kind?: string;
  summary: RunSummary;
  promos: Promo[];
  rejected_by_gate?: Record<string, number>;
  /** Gate rejections, per candidate. What an episode box shows when the
   *  episode shipped nothing: which gate stopped each candidate, and the
   *  number it measured. */
  rejected?: Rejection[];
  /** Candidates that passed every gate, were scored, and still lost - on the
   *  rubric floor, to a near-duplicate, or to the per-episode cap. A
   *  different population from `rejected`, kept separate on purpose. */
  dropped_in_selection?: Rejection[];
}

export interface HealthResponse {
  ok: boolean;
  has_key: boolean;
  has_outputs: boolean;
  profile: string;
  max_paste_chars: number;
}

export interface RunResponse {
  ok: boolean;
  error?: string;
  kind?: string;
  /** `describe_profile()` for the models that actually ran. Never a key. */
  profile?: string;
  /** The profile name, e.g. `free`. Absent on a failed or restored run. */
  profile_id?: string;
  promos: Promo[];
  rejected: Rejection[];
  episode?: {
    n_blocks: number;
    n_content_blocks: number;
    duration_s: number;
    logline: string;
    speakers: string[];
  };
}

/* --- the model picker ----------------------------------------------------
 *
 * Everything below is read out of `config/settings.yaml` by
 * `GET /api/profiles`. No model id is written down in the React app, for the
 * same reason none is written down in `src/`: the YAML is the one place a
 * model is named, and a selector that hardcoded its own list would quietly
 * become the second.
 */

/** What one tier of a profile resolves to. */
export interface ProfileTier {
  tier: string;
  provider: string;
  model: string;
}

/** A key a profile needs, and whether the server already has it. */
export interface ProfileKey {
  provider: string;
  /** The environment variable the server would read, e.g. `GEMINI_API_KEY`. */
  env: string;
  on_server: boolean;
}

/** One row of the model picker. */
export interface ProfileInfo {
  id: string;
  providers: string[];
  tiers: ProfileTier[];
  /** Drives the sidebar badge, and nothing else decides it. */
  cost: "free" | "paid" | "local";
  keys: ProfileKey[];
}

export interface ProfilesResponse {
  ok: boolean;
  error?: string;
  /** `default_profile` from the YAML - what runs when nothing is chosen. */
  default: string;
  profiles: ProfileInfo[];
}
