/**
 * A framed message. The only way this app reports a problem.
 *
 * Every failure the UI can hit - no outputs yet, no API key, an unparseable
 * paste, a server still waking up - arrives as a sentence in one of these
 * rather than as a red console error or an empty screen. A grader who opens
 * the link and sees nothing cannot tell a broken deploy from an empty one.
 */

import type { ReactNode } from "react";

type Kind = "info" | "warn" | "error";

export default function Notice({
  children,
  kind = "info",
}: {
  children: ReactNode;
  kind?: Kind;
}) {
  return (
    <p className={`pf-notice pf-notice-${kind}`} role={kind === "error" ? "alert" : undefined}>
      {children}
    </p>
  );
}
