import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import catalogue from "../../../../ui-schema/settings.json";
import { matchSettingsSections } from "./settingsSearch.mjs";
import {
  applyAppearance,
  readBrowserPreferences,
  saveBrowserPreferences,
  useBrowserPreferences,
} from "./browserPreferences";
import type { BrowserPreferences } from "./browserPreferences";
import MemorySettings from "./MemorySettings";
import PluginLibrary from "./PluginLibrary";
import { settingsRequest } from "./settingsClient";
import "./SettingsCenter.css";

type Personalization = {
  personalization: { custom_instructions: string; response_language: string };
  memory: { enabled: boolean };
};
type CoreDocument = {
  schema_version: number;
  revision: number;
  preferences: Personalization & BrowserPreferences;
};
type SettingsResponse = { scope: "account" | "device"; settings: CoreDocument };
type Connection = {
  id: string;
  displayName?: string;
  provider?: string;
  defaultModel?: string;
};

export default function SettingsCenter({
  onDirty,
}: {
  onDirty: (dirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const savedBrowser = useBrowserPreferences();
  const [browserDraft, setBrowserDraft] = useState(savedBrowser);
  const [section, setSection] = useState("general");
  const [searchQuery, setSearchQuery] = useState("");
  const [saved, setSaved] = useState<CoreDocument | null>(null);
  const [personalDraft, setPersonalDraft] = useState<Personalization | null>(
    null,
  );
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const current = catalogue.sections.find((item) => item.id === section)!;
  const matchingSections = useMemo(() => matchSettingsSections(
    catalogue.sections, searchQuery, (key: string, fallback: string) =>
      t(key, { defaultValue: fallback }),
  ), [searchQuery, t]);
  const dirty =
    section === "general"
      ? JSON.stringify(savedBrowser) !== JSON.stringify(browserDraft)
      : section === "personalization" &&
        !!saved &&
        JSON.stringify({
          personalization: saved.preferences.personalization,
          memory: saved.preferences.memory,
        }) !== JSON.stringify(personalDraft);

  useEffect(() => {
    onDirty(Boolean(dirty));
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    setBrowserDraft(savedBrowser);
  }, [savedBrowser]);
  useEffect(() => {
    applyAppearance(browserDraft);
    return () => applyAppearance(readBrowserPreferences());
  }, [browserDraft]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  async function load() {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      if (section === "personalization") {
        const result = await settingsRequest<SettingsResponse>("/ai/settings");
        // Public Web only accepts account-owned preferences; loopback/device stores
        // are never a silent fallback for a signed-in cloud account.
        if (result.scope !== "account" || result.settings.schema_version !== 1)
          throw new Error("unavailable");
        setSaved(result.settings);
        setPersonalDraft({
          personalization: result.settings.preferences.personalization,
          memory: result.settings.preferences.memory,
        });
      } else if (section === "models") {
        const result = await settingsRequest<{ credentials: Connection[] }>(
          "/connections",
        );
        setConnections(result.credentials || []);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, [section]);
  const discard = () => {
    setBrowserDraft(savedBrowser);
    if (saved)
      setPersonalDraft({
        personalization: saved.preferences.personalization,
        memory: saved.preferences.memory,
      });
    setStatus("");
  };
  async function save() {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      if (section === "general") {
        saveBrowserPreferences(browserDraft);
        setStatus("savedBrowser");
      } else if (section === "personalization" && saved && personalDraft) {
        const result = await settingsRequest<SettingsResponse>("/ai/settings", {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: saved.revision,
            patch: personalDraft,
          }),
        });
        if (result.scope !== "account") throw new Error("unavailable");
        setSaved(result.settings);
        setPersonalDraft({
          personalization: result.settings.preferences.personalization,
          memory: result.settings.preferences.memory,
        });
        setStatus("savedAccount");
      }
    } catch (reason) {
      setError(
        section === "general" ? "storageFailed" : (reason as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }
  function setField(binding: string, value: string | boolean) {
    const [group, key] = binding.split(".");
    if (section === "general")
      setBrowserDraft((previous) => ({
        ...previous,
        [group]: {
          ...previous[group as keyof BrowserPreferences],
          [key]: value,
        },
      }));
    else if (personalDraft)
      setPersonalDraft({
        ...personalDraft,
        [group]: {
          ...personalDraft[group as keyof Personalization],
          [key]: value,
        },
      });
    setStatus("");
  }
  const accountLink = (
    <a
      className="button secondary"
      href="https://account.meoarch.org"
      target="_blank"
      rel="noreferrer"
    >
      {t("meo.settings.openAccount")} ↗
    </a>
  );
  return (
    <div className="meo-settings">
      <div className="settings-layout">
        <nav className="settings-nav" aria-label={t("meo.settings.categories")}>
          <h1>{t("meo.settings.title")}</h1>
          <label className="settings-search-label" htmlFor="meo-settings-search">{t("meo.settings.searchLabel")}</label>
          <input
            id="meo-settings-search"
            className="settings-search-input"
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder={t("meo.settings.searchPlaceholder")}
            autoComplete="off"
          />
          {matchingSections.length === 0 && (
            <p className="settings-no-results" role="status">{t("meo.settings.noResults")}</p>
          )}
          {matchingSections.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={busy}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => {
                if (dirty && !window.confirm(t("meo.settings.discardConfirm")))
                  return;
                discard();
                setSection(item.id);
                setSearchQuery("");
              }}
            >
              {t(item.labelKey, { defaultValue: item.label })}
            </button>
          ))}
        </nav>
        <section
          className="settings-content"
          aria-label={t(current.labelKey, { defaultValue: current.label })}
        >
          <div className="section-heading">
            <span className="eyebrow">
              {t(current.labelKey, { defaultValue: current.label })}
            </span>
            <h2>{t(`meo.settings.${section}.heading`)}</h2>
            <p>{t(`meo.settings.${section}.description`)}</p>
          </div>
          {busy && <p role="status">{t("meo.settings.loading")}</p>}
          {error && (
            <div className="notice error" role="alert">
              {t(`meo.settings.error.${error}`, {
                defaultValue: t("meo.settings.error.failed"),
              })}
              <button type="button" disabled={busy} onClick={() => void load()}>
                {t("meo.settings.reload")}
              </button>
            </div>
          )}
          {current.items.map((item) => {
            const source = section === "general" ? browserDraft : personalDraft;
            if (!source) return null;
            const [group, key] = item.binding.split(".");
            const value = (
              source as unknown as Record<
                string,
                Record<string, string | boolean>
              >
            )[group]?.[key];
            const hint = `${item.id}-hint`;
            return (
              <div
                className={`setting-row ${item.kind === "text" ? "vertical" : ""}`}
                key={item.id}
              >
                <div className="row-copy">
                  <label htmlFor={item.id}>
                    {t(item.labelKey, { defaultValue: item.label })}
                  </label>
                  <p id={hint}>{t(`meo.settings.hint.${item.id}`)}</p>
                </div>
                {item.kind === "toggle" ? (
                  <input
                    className="switch"
                    id={item.id}
                    aria-describedby={hint}
                    type="checkbox"
                    checked={Boolean(value)}
                    disabled={busy}
                    onChange={(event) =>
                      setField(item.binding, event.target.checked)
                    }
                  />
                ) : item.kind === "select" ? (
                  <select
                    id={item.id}
                    aria-describedby={hint}
                    value={String(value)}
                    disabled={busy}
                    onChange={(event) =>
                      setField(item.binding, event.target.value)
                    }
                  >
                    {("options" in item ? item.options : [])?.map((option) => (
                      <option key={option} value={option}>
                        {t(`meo.settings.option.${option}`, {
                          defaultValue: option,
                        })}
                      </option>
                    ))}
                  </select>
                ) : (
                  <>
                    <textarea
                      id={item.id}
                      aria-describedby={hint}
                      rows={7}
                      maxLength={
                        "maxLength" in item ? item.maxLength : undefined
                      }
                      disabled={busy}
                      value={String(value)}
                      onChange={(event) =>
                        setField(item.binding, event.target.value)
                      }
                    />
                    <span className="field-count">
                      {Array.from(String(value)).length} /{" "}
                      {"maxLength" in item ? item.maxLength : ""}
                    </span>
                  </>
                )}
              </div>
            );
          })}
          {section === "personalization" && saved && <MemorySettings />}
          {section === "models" && (
            <>
              <div className="setting-row">
                <div className="row-copy">
                  <h3>{t("meo.settings.connections")}</h3>
                  <p>{t("meo.settings.connectionsHint")}</p>
                </div>
                <a
                  className="button secondary"
                  href="https://account.meoarch.org/settings/services"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("meo.settings.openAccount")} ↗
                </a>
              </div>
              {connections?.map((item) => (
                <div className="setting-row" key={item.id}>
                  <div className="row-copy">
                    <h3>{item.displayName || item.provider}</h3>
                    <p>{item.defaultModel || t("meo.settings.noDefault")}</p>
                  </div>
                </div>
              ))}
              {connections?.length === 0 && (
                <p>{t("meo.settings.noConnections")}</p>
              )}
            </>
          )}
          {["privacy", "account"].includes(section) && (
            <div className="setting-row">
              <div className="row-copy">
                <h3>{t(`meo.settings.${section}.heading`)}</h3>
                <p>{t(`meo.settings.${section}.actionHint`)}</p>
              </div>
              {accountLink}
            </div>
          )}
          {section === "connectors" && <PluginLibrary />}
          {["devices", "usage"].includes(section) && (
            <div className="empty-state">
              <h3>{t("meo.settings.serviceUnavailable")}</h3>
              <p>{t(`meo.settings.${section}.unavailable`)}</p>
            </div>
          )}
          {section === "general" && (
            <div className="version-note">Meo AI · Development preview</div>
          )}
          {current.items.length > 0 && (section === "general" || saved) && (
            <footer className="settings-footer">
              <div role="status">
                {t(
                  `meo.settings.${status || (dirty ? "unsaved" : section === "general" ? "browserScope" : "accountScope")}`,
                )}
              </div>
              <div className="footer-actions">
                <button
                  type="button"
                  className="button secondary"
                  disabled={!dirty || busy}
                  onClick={discard}
                >
                  {t("meo.settings.discard")}
                </button>
                <button
                  type="button"
                  className="button primary"
                  disabled={!dirty || busy}
                  onClick={() => void save()}
                >
                  {t("meo.settings.save")}
                </button>
              </div>
            </footer>
          )}
        </section>
      </div>
    </div>
  );
}
