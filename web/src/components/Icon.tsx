/**
 * The whole icon set. Eleven glyphs, inline, no dependency.
 *
 * These exist because the interface used to signal with text characters -
 * `+` and `-` for a disclosure, `&rarr;` in the brand line, an em dash for a
 * number that had not loaded. Each of those is a typographic gamble: it
 * inherits the text font, so it shifts weight and baseline with the face,
 * and a face without the glyph draws a tofu box instead. A path in a 16px
 * box is the same shape everywhere.
 *
 * Rules they all follow, so a row of them reads as one family:
 *
 *   - 16x16 viewBox, 1.6 stroke, round caps and joins, no fill.
 *   - `currentColor`, never a hard-coded hue. The axis palette is reserved
 *     for data (see the stylesheet's rule 1) and an icon is never data.
 *   - `aria-hidden`. Every icon in this app sits next to its own label, or
 *     inside a control that carries an `aria-label`. None of them is the
 *     only thing conveying a meaning.
 *   - `width`/`height` come from CSS (`.pf-i`), not attributes, so a button
 *     can scale its icon with its own font size.
 */

export type IconName =
  | "settings"
  | "key"
  | "chevron-down"
  | "chevron-right"
  | "arrow-right"
  | "search"
  | "spark"
  | "refresh"
  | "document"
  | "check"
  | "close";

const PATHS: Record<IconName, JSX.Element> = {
  // Two sliders. A cog at 16px with a 1.6 stroke turns to mush; this reads
  // as "settings" at the size the rail actually draws it.
  settings: (
    <>
      <path d="M2.5 5h11" />
      <path d="M2.5 11h11" />
      <circle cx="6" cy="5" r="1.9" />
      <circle cx="10" cy="11" r="1.9" />
    </>
  ),
  key: (
    <>
      <circle cx="5.8" cy="10.2" r="3.1" />
      <path d="M8 8 13.5 2.5" />
      <path d="M11.3 4.7 12.8 6.2" />
    </>
  ),
  "chevron-down": <path d="M4 6.5 8 10.5l4-4" />,
  "chevron-right": <path d="M6.5 4 10.5 8l-4 4" />,
  "arrow-right": (
    <>
      <path d="M2.5 8h11" />
      <path d="M9.5 4.5 13 8l-3.5 3.5" />
    </>
  ),
  search: (
    <>
      <circle cx="7.2" cy="7.2" r="4.2" />
      <path d="M10.4 10.4 13.5 13.5" />
    </>
  ),
  // A cut point: the strip, and the frame chosen out of it.
  spark: (
    <>
      <path d="M2 4.5h12v7H2z" />
      <path d="M6 4.5v7" />
      <path d="M10 4.5v7" />
    </>
  ),
  refresh: (
    <>
      <path d="M13 8a5 5 0 1 1-1.6-3.7" />
      <path d="M13.2 2.6v2.6h-2.6" />
    </>
  ),
  document: (
    <>
      <path d="M4 2.5h5l3 3v8H4z" />
      <path d="M6 8.5h4" />
      <path d="M6 11h3" />
    </>
  ),
  check: <path d="M3.5 8.5 6.5 11.5 12.5 5" />,
  close: (
    <>
      <path d="M4 4l8 8" />
      <path d="M12 4l-8 8" />
    </>
  ),
};

export default function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="pf-i"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
