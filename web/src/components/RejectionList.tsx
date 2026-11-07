/**
 * Candidates that did not ship, each with the measured number that stopped
 * it.
 *
 * Two populations share this list and are labelled apart, because conflating
 * them would be the dishonest version. A **gate** rejection never reached a
 * scorer at all - it failed a deterministic rule in Python, so there is no
 * opinion in it. A **selection** drop passed every gate, was scored, and
 * still lost: to the rubric floor, to a near-duplicate, or to the
 * per-episode cap. The first is the tool working; the second is the tool
 * choosing, and only the second is arguable.
 *
 * Kept on screen rather than hidden in a JSON file: a tool that cannot say
 * why it declined is not auditable.
 */

import type { Rejection, SelectionDrop } from "../types";

const RULE_LABEL: Record<SelectionDrop["rule"], string> = {
  min_cliffhanger: "below the cliffhanger floor",
  min_score: "below the rubric floor",
  dedup: "near-duplicate of a better pick",
  episode_cap: "over the per-episode cap",
};

function selectionDetail(drop: SelectionDrop): string {
  switch (drop.rule) {
    case "min_cliffhanger":
      return `cliffhanger scored ${drop.cliffhanger?.toFixed(1) ?? "?"}, floor is ${drop.floor ?? "?"}`;
    case "min_score":
      return `weighted ${drop.weighted_score?.toFixed(2) ?? "?"}, floor is ${drop.floor ?? "?"}`;
    case "dedup":
      return `${((drop.overlap ?? 0) * 100).toFixed(0)}% overlap with ${drop.lost_to ?? "a better pick"}, threshold ${((drop.threshold ?? 0) * 100).toFixed(0)}%`;
    case "episode_cap":
      return `ranked ${drop.place_in_episode ?? "?"} in this episode, cap is ${drop.cap ?? "?"}`;
    default:
      return "";
  }
}

export default function RejectionList({ rejections }: { rejections: Rejection[] }) {
  if (rejections.length === 0) {
    return <p className="pf-empty">No candidate was rejected.</p>;
  }

  return (
    <ul className="pf-rejects">
      {rejections.map((rejection) => {
        const drop = rejection.selection;
        return (
          <li className={`pf-reject${drop ? " is-selection" : ""}`} key={rejection.id}>
            <div className="pf-reject-head">
              <code className="pf-reject-id">{rejection.id}</code>
              {rejection.duration_s !== undefined && (
                <span className="pf-tc pf-tc-dim">
                  {rejection.duration_s.toFixed(1)}s
                </span>
              )}
              {rejection.weighted_score !== undefined && (
                <span className="pf-reject-score">
                  {rejection.weighted_score.toFixed(2)}
                </span>
              )}
              <span className={`pf-reject-kind${drop ? " is-selection" : ""}`}>
                {drop ? "scored, then lost" : "stopped by a gate"}
              </span>
            </div>

            {rejection.hook ? (
              <p className="pf-reject-hook">{rejection.hook}</p>
            ) : null}

            <ul className="pf-reject-fails">
              {drop ? (
                <li>
                  <code className="pf-reject-gate">{drop.rule}</code>
                  <span className="pf-reject-detail">
                    {RULE_LABEL[drop.rule]} &mdash; {selectionDetail(drop)}
                  </span>
                </li>
              ) : (
                rejection.failures.map((failure, i) => (
                  <li key={`${failure.gate}-${i}`}>
                    <code className="pf-reject-gate">{failure.gate}</code>
                    <span className="pf-reject-detail">{failure.detail}</span>
                  </li>
                ))
              )}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}
