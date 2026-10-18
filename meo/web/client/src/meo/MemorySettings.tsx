import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { settingsRequest } from "./settingsClient";
type Item = { id: string; text: string; pinned: boolean; archived: boolean };
type Memory = { schema_version: number; revision: number; items: Item[] };
async function call(path: string, init?: RequestInit): Promise<Memory> {
  const result = await settingsRequest<{ scope: string; memory: Memory }>(
    `/ai/memory${path}`,
    init,
  );
  if (result.scope !== "account") throw new Error("unavailable");
  return result.memory;
}
export default function MemorySettings() {
  const { t } = useTranslation();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [archived, setArchived] = useState(false);
  const load = () => {
    setError("");
    void call("")
      .then(setMemory)
      .catch((reason) => setError(reason.message));
  };
  useEffect(load, []);
  async function write(item?: Item, archive?: boolean) {
    if (!memory) return;
    setBusy(true);
    setError("");
    try {
      const result = await call(item ? `/${encodeURIComponent(item.id)}` : "", {
        method: item ? "PUT" : "POST",
        body: JSON.stringify({
          expected_revision: memory.revision,
          text: archive !== undefined && item ? item.text : text,
          pinned: item?.pinned || false,
          archived: archive ?? item?.archived ?? false,
        }),
      });
      setMemory(result);
      setText("");
      setEditing(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="memory-manager"
      aria-label={t("meo.settings.memoryCopy1")}
    >
      <div className="memory-heading">
        <div>
          <h3>{t("meo.settings.memoryCopy2")}</h3>
          <p>{t("meo.settings.memoryCopy3")}</p>
        </div>
        <label className="archive-filter">
          <input
            type="checkbox"
            checked={archived}
            onChange={(event) => setArchived(event.target.checked)}
          />
          {t("meo.settings.memoryCopy4")}
        </label>
      </div>
      {!memory && !error && (
        <p role="status" className="memory-empty">
          {t("meo.settings.memoryCopy5")}
        </p>
      )}
      {error && (
        <div className="notice error" role="alert">
          {t(`meo.settings.error.${error}`, {
            defaultValue: t("meo.settings.error.failed"),
          })}
          <button onClick={load}>{t("meo.settings.memoryCopy6")}</button>
        </div>
      )}
      {memory?.items
        .filter((item) => item.archived === archived)
        .map((item) => (
          <div className="memory-row" key={item.id}>
            <p>{item.text}</p>
            <div className="memory-actions">
              {!item.archived && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => {
                    setEditing(item.id);
                    setText(item.text);
                  }}
                >
                  {t("meo.settings.memoryCopy7")}
                </button>
              )}
              <button
                className="text-button"
                disabled={busy}
                onClick={() => void write(item, !item.archived)}
              >
                {item.archived
                  ? t("meo.settings.memoryCopy8")
                  : t("meo.settings.memoryCopy9")}
              </button>
            </div>
          </div>
        ))}
      {memory &&
        memory.items.filter((item) => item.archived === archived).length ===
          0 && (
          <p className="memory-empty">
            {archived
              ? t("meo.settings.memoryCopy10")
              : t("meo.settings.memoryCopy11")}
          </p>
        )}
      {!archived && (
        <form
          className="memory-form"
          onSubmit={(event) => {
            event.preventDefault();
            void write(
              editing
                ? memory?.items.find((item) => item.id === editing)
                : undefined,
            );
          }}
        >
          <label htmlFor="new-memory">
            {editing
              ? t("meo.settings.memoryCopy12")
              : t("meo.settings.memoryCopy13")}
          </label>
          <textarea
            id="new-memory"
            value={text}
            maxLength={4000}
            rows={2}
            onChange={(event) => setText(event.target.value)}
            placeholder={t("meo.settings.memoryCopy14")}
            disabled={busy}
          />
          <div>
            <button
              className="button secondary"
              type="submit"
              disabled={busy || !text.trim() || !memory}
            >
              {editing
                ? t("meo.settings.memoryCopy15")
                : t("meo.settings.memoryCopy16")}
            </button>
            {editing && (
              <button
                className="text-button"
                type="button"
                onClick={() => {
                  setEditing(null);
                  setText("");
                }}
              >
                {t("meo.settings.memoryCopy17")}
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
