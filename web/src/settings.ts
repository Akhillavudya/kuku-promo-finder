/**
 * Which model the live run uses, and the keys it needs. Browser-side only.
 *
 * Two values, both chosen in the sidebar's Settings dialog:
 *
 *   profile  a name from `GET /api/profiles`, which is a name from
 *            `config/settings.yaml`. Never a model id - see `types.ts`.
 *   keys     `{ provider: key }`, pasted by whoever is looking at the page.
 *
 * **Where a pasted key goes.** Into `localStorage` in this browser, and into
 * the body of `POST /api/run`. That is the whole list. The server uses it for
 * that one request, holds it in a throwaway environment variable with a
 * random name for the length of the call, and deletes it in a `finally`
 * (see `_inject_keys` in `api/main.py`). It is never written to disk, never
 * logged, never put in a response, and never assigned to the real
 * `ANTHROPIC_API_KEY`-style variable, which would hand it to every later
 * request the process serves.
 *
 * **Why `localStorage` and not a cookie or the URL.** A cookie rides along on
 * every request to the origin, including the static asset fetches, and a
 * query string lands in browser history, proxy logs and a shared screenshot.
 * `localStorage` is read only by this page's own script, and only on this
 * device.
 *
 * It is still the viewer's own browser: anyone with the machine can read it
 * from the console, which is why the dialog shows a masked key with a
 * "Forget" button rather than pretending the value is a secret the page is
 * keeping. The honest framing is "paste it once per device", not "vault".
 *
 * Every read and write is wrapped, the same as `history.ts`: `localStorage`
 * throws outright in a private window with site data blocked. A failure here
 * costs the remembered choice, never the app.
 */

const KEY = "pf.modelsettings.v1";

export interface ModelSettings {
  /** A profile id, or "" for whatever the server's `default_profile` is. */
  profile: string;
  /** `{ provider: api key }`. Absent provider = nothing pasted for it. */
  keys: Record<string, string>;
}

export const EMPTY: ModelSettings = { profile: "", keys: {} };

export function loadSettings(): ModelSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<ModelSettings>;
    const keys: Record<string, string> = {};
    for (const [provider, value] of Object.entries(parsed.keys ?? {})) {
      if (typeof value === "string" && value.trim()) keys[provider] = value.trim();
    }
    return {
      profile: typeof parsed.profile === "string" ? parsed.profile : "",
      keys,
    };
  } catch {
    return { ...EMPTY };
  }
}

export function saveSettings(settings: ModelSettings): ModelSettings {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    // Private window, or quota. The choice still applies for this session.
  }
  return settings;
}

export function forgetKeys(settings: ModelSettings): ModelSettings {
  return saveSettings({ ...settings, keys: {} });
}

/**
 * `sk-ant-api03-abcd...WXYZ` -> `sk-ant-api03-ab...WXYZ`. Enough to tell two
 * keys apart, not enough to use one. Nothing ever renders the raw value.
 */
export function maskKey(key: string): string {
  const trimmed = key.trim();
  if (trimmed.length <= 12) return "•".repeat(Math.max(trimmed.length, 4));
  return `${trimmed.slice(0, 6)}…${trimmed.slice(-4)}`;
}
