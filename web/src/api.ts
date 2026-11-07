/**
 * The whole network layer. Five calls, no client library.
 *
 * `api/main.py` answers user-level problems - no key, unparseable paste - as
 * HTTP 200 with `ok: false`, so the only thing that throws here is a genuine
 * transport failure (server down, container still waking). Those are turned
 * into the same `{ ok: false, error }` shape, so a caller has exactly one
 * failure path to render and never an unhandled rejection.
 */

import type {
  HealthResponse,
  ProfilesResponse,
  RunResponse,
  SeasonResponse,
} from "./types";
import type { ModelSettings } from "./settings";

/**
 * Where the API lives.
 *
 * Empty string in development and in the single-origin container, where
 * FastAPI serves `web/dist` itself and a relative `/api/*` path is already
 * correct. Set to the backend's own origin at build time - `.env.production`,
 * read by Vite - for the split deploy, where the static files are served by
 * Hostinger and a static host cannot proxy `/api` anywhere.
 *
 * It is baked into the bundle at build time, not read at runtime, so pointing
 * the frontend at a different backend means a rebuild and a re-upload. That
 * is the honest cost of static hosting; the alternative is a runtime config
 * fetch, which is one more round trip before the page can render anything.
 *
 * Trailing slashes are stripped so `BASE + "/api/health"` can never produce
 * `//api/health`, which some hosts 404 rather than normalise.
 */
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

/** An API path, resolved against whichever origin this build talks to. */
function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok && response.status !== 200) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

function transportError(error: unknown): string {
  const detail = error instanceof Error ? error.message : String(error);
  return `Could not reach the server (${detail}). If this is a free host it may be waking up - give it a moment and retry.`;
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    return await getJSON<HealthResponse>(apiUrl("/api/health"));
  } catch {
    return {
      ok: false,
      has_key: false,
      has_outputs: false,
      profile: "server unreachable",
      max_paste_chars: 120000,
    };
  }
}

export async function fetchProfiles(): Promise<ProfilesResponse> {
  try {
    return await getJSON<ProfilesResponse>(apiUrl("/api/profiles"));
  } catch (error) {
    return {
      ok: false,
      error: transportError(error),
      default: "",
      profiles: [],
    };
  }
}

export async function fetchSeason(): Promise<SeasonResponse> {
  try {
    return await getJSON<SeasonResponse>(apiUrl("/api/season"));
  } catch (error) {
    return {
      ok: false,
      error: transportError(error),
      kind: "transport",
      summary: {},
      promos: [],
    };
  }
}

export async function fetchSample(): Promise<string> {
  try {
    const data = await getJSON<{ ok: boolean; text: string }>(apiUrl("/api/sample"));
    return data.text ?? "";
  } catch {
    return "";
  }
}

/**
 * Run one episode. `settings` carries the chosen profile and any key pasted
 * in the Settings dialog; both go in the POST body, never in the URL - a
 * query string would land in browser history and in any proxy log on the
 * way. Only the keys the chosen profile actually needs are sent, so
 * selecting Gemini never puts an Anthropic key on the wire.
 */
export async function postRun(
  text: string,
  settings: ModelSettings,
  providers: string[],
): Promise<RunResponse> {
  const api_keys: Record<string, string> = {};
  for (const provider of providers) {
    const key = settings.keys[provider];
    if (key) api_keys[provider] = key;
  }
  try {
    return await getJSON<RunResponse>(apiUrl("/api/run"), {
      method: "POST",
      body: JSON.stringify({ text, profile: settings.profile || null, api_keys }),
    });
  } catch (error) {
    return {
      ok: false,
      error: transportError(error),
      kind: "transport",
      promos: [],
      rejected: [],
    };
  }
}
