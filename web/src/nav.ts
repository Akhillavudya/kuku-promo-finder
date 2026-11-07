/**
 * What the rail selects, and what the workspace reads.
 *
 * These three live in their own module rather than in `Sidebar.tsx` because
 * `EpisodePicker` needs them and `Sidebar` renders `EpisodePicker`. Declaring
 * them in the parent made the two files import each other - which happens to
 * work here, since nothing is read at module-evaluation time, but an import
 * cycle that works by luck is one refactor away from a `ReferenceError` at
 * load. A leaf module both can import has no such edge.
 */

/** The "no filter" sentinel. A string so it can never collide with an
 *  episode number, and a const so the type is the literal, not `string`. */
export const ALL_EPISODES = "all" as const;

export type ViewId = "season" | "live" | "method";

export interface EpisodeEntry {
  number: number;
  promos: number;
  /** The episode's best weighted score, or null if it shipped nothing. */
  best: number | null;
}
