/**
 * The model picker, behind the Settings button at the foot of the rail.
 *
 * Two things in one dialog, because they are one decision: which profile the
 * live run uses, and the key that profile needs. Choosing Claude without a
 * place to paste an Anthropic key would be a setting that cannot be acted
 * on, so the key fields follow the selection and only the selected profile's
 * providers get one.
 *
 * The rows come from `GET /api/profiles`, which reads `config/settings.yaml`.
 * Nothing here knows what a Gemini or a Claude is: it renders whatever
 * provider and model strings the YAML holds, and a profile added to the YAML
 * appears in this list with no change to this file.
 *
 * Edits are held in a draft and committed on Save, so backing out of a
 * half-typed key leaves the running configuration alone.
 *
 * Accessibility, since this is the one modal in the app: `role="dialog"` with
 * `aria-modal`, an `aria-labelledby` title, Escape and backdrop to close,
 * focus moved in on open and returned to the Settings button on close, and
 * Tab cycled inside the panel so keyboard focus cannot wander onto the page
 * behind it. The profile list is a real radio group, so arrow keys work.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon";
import { maskKey, type ModelSettings } from "../settings";
import type { ProfileInfo } from "../types";

interface Props {
  profiles: ProfileInfo[];
  /** `default_profile` from the YAML, used when nothing has been chosen. */
  fallback: string;
  settings: ModelSettings;
  onSave: (next: ModelSettings) => void;
  onClose: () => void;
}

const COST_LABEL: Record<ProfileInfo["cost"], string> = {
  free: "Free",
  paid: "Paid",
  local: "Local",
};

/** `candidates` and `rank` are the pipeline's two passes, in plain words. */
const TIER_LABEL: Record<string, string> = {
  candidates: "proposes candidates",
  rank: "scores them",
};

export default function SettingsDialog({
  profiles,
  fallback,
  settings,
  onSave,
  onClose,
}: Props) {
  const [draft, setDraft] = useState<ModelSettings>(() => ({
    profile: settings.profile || fallback,
    keys: { ...settings.keys },
  }));
  /** Providers whose key field is currently being typed into, so a saved key
   *  shows as a mask until someone chooses to replace it. */
  const [editing, setEditing] = useState<Record<string, boolean>>({});

  const panel = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => profiles.find((p) => p.id === draft.profile) ?? profiles[0] ?? null,
    [profiles, draft.profile],
  );

  /* --- focus and keyboard ----------------------------------------------- */

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>(
      "input:not([disabled]), button:not([disabled])",
    );
    first?.focus();
    return () => opener?.focus?.();
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = panel.current?.querySelectorAll<HTMLElement>(
        "input:not([disabled]), button:not([disabled]), [href]",
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  /* --- editing ----------------------------------------------------------- */

  function setKey(provider: string, value: string) {
    setDraft((current) => ({
      ...current,
      keys: { ...current.keys, [provider]: value },
    }));
  }

  function forget(provider: string) {
    setDraft((current) => {
      const keys = { ...current.keys };
      delete keys[provider];
      return { ...current, keys };
    });
    setEditing((current) => ({ ...current, [provider]: true }));
  }

  function save() {
    const keys: Record<string, string> = {};
    for (const [provider, value] of Object.entries(draft.keys)) {
      if (value.trim()) keys[provider] = value.trim();
    }
    onSave({ profile: draft.profile, keys });
  }

  return (
    <div
      className="pf-modal-wrap"
      onKeyDown={onKeyDown}
      // A click that starts and ends on the backdrop closes. Checking the
      // target keeps a drag that ends outside the panel from closing it
      // mid-selection.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="pf-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pf-settings-title"
        ref={panel}
      >
        <header className="pf-modal-head">
          <div>
            <h2 className="pf-modal-title" id="pf-settings-title">
              Model and API key
            </h2>
            <p className="pf-modal-sub">
              Applies to <strong>Run live</strong>. The Season view is
              precomputed and never calls a model.
            </p>
          </div>
          <button
            type="button"
            className="pf-iconbtn"
            onClick={onClose}
            aria-label="Close settings"
          >
            <Icon name="close" />
          </button>
        </header>

        <div className="pf-modal-body">
          {profiles.length === 0 ? (
            <p className="pf-modal-empty">
              The server did not return a model list, so there is nothing to
              choose. The usual cause is a server started before this screen
              existed: restart <code>uvicorn api.main:app</code> and reload.
              Until then a run uses whatever <code>config/settings.yaml</code>{" "}
              has as its default profile.
            </p>
          ) : (
            <fieldset className="pf-fieldset">
              <legend className="pf-legend">Model</legend>
              <ul className="pf-choices">
                {profiles.map((profile) => {
                  const on = profile.id === draft.profile;
                  return (
                    <li key={profile.id}>
                      <label className={`pf-choice${on ? " is-on" : ""}`}>
                        <input
                          type="radio"
                          name="pf-profile"
                          className="pf-choice-radio"
                          value={profile.id}
                          checked={on}
                          onChange={() =>
                            setDraft((current) => ({
                              ...current,
                              profile: profile.id,
                            }))
                          }
                        />
                        <span className="pf-choice-text">
                          <span className="pf-choice-top">
                            <span className="pf-choice-name">{profile.id}</span>
                            <span
                              className="pf-tag"
                              data-cost={profile.cost}
                            >
                              {COST_LABEL[profile.cost]}
                            </span>
                          </span>
                          <span className="pf-choice-models">
                            {profile.tiers.map((tier) => (
                              <span className="pf-choice-tier" key={tier.tier}>
                                <code>{tier.model}</code>{" "}
                                {TIER_LABEL[tier.tier] ?? tier.tier}
                              </span>
                            ))}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          )}

          {selected && selected.keys.length === 0 && (
            <p className="pf-modal-note">
              <Icon name="check" /> This profile needs no API key.
            </p>
          )}

          {selected?.keys.map((need) => {
            const saved = settings.keys[need.provider];
            const typing = editing[need.provider] || !saved;
            return (
              <div className="pf-field pf-field-block" key={need.provider}>
                <label className="pf-label" htmlFor={`pf-key-${need.provider}`}>
                  <Icon name="key" /> {need.provider} API key
                </label>
                {typing ? (
                  <input
                    id={`pf-key-${need.provider}`}
                    className="pf-input"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={draft.keys[need.provider] ?? ""}
                    placeholder={
                      need.on_server
                        ? `optional - ${need.env} is already set on the server`
                        : `paste your ${need.provider} key`
                    }
                    onChange={(event) => setKey(need.provider, event.target.value)}
                  />
                ) : (
                  <div className="pf-keysaved">
                    <code className="pf-keymask">{maskKey(saved)}</code>
                    <button
                      type="button"
                      className="pf-btn pf-btn-quiet"
                      onClick={() => forget(need.provider)}
                    >
                      <Icon name="close" />
                      Forget and replace
                    </button>
                  </div>
                )}
                <p className="pf-help">
                  {need.on_server ? (
                    <>
                      The server already has <code>{need.env}</code>, so this is
                      optional - paste one to use your own quota instead.
                    </>
                  ) : (
                    <>
                      The server has no <code>{need.env}</code>, so a live run
                      on this profile needs a key here.
                    </>
                  )}{" "}
                  It is kept in this browser only and sent with the run request;
                  the server uses it for that one call and never stores it.
                </p>
              </div>
            );
          })}
        </div>

        <footer className="pf-modal-foot">
          <button type="button" className="pf-btn pf-btn-primary" onClick={save}>
            <Icon name="check" />
            Save
          </button>
          <button type="button" className="pf-btn" onClick={onClose}>
            Cancel
          </button>
        </footer>
      </div>
    </div>
  );
}
