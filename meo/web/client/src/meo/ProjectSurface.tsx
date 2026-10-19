import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import "./ProjectSurface.css";

type Project = {
  id: string;
  name: string;
  description?: string | null;
  updated_at?: string;
};
type ProjectList = { projects: Project[] };
type ProjectResult = { project: Project };

const safeId = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

async function projectRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/meo/projects${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const code = data?.error?.message || data?.error?.code || `HTTP ${response.status}`;
    throw new Error(String(code));
  }
  return data as T;
}

export default function ProjectSurface() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [editName, setEditName] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await projectRequest<ProjectList>("");
      if (!Array.isArray(result.projects)) throw new Error("invalid_project_response");
      setProjects(result.projects.filter((row) => row && safeId.test(row.id)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const selected = projects.find((item) => item.id === selectedId) || null;

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newName.trim();
    if (!name || name.length > 160 || busy) return;
    setBusy(true);
    setError("");
    try {
      const { project } = await projectRequest<ProjectResult>("", {
        method: "POST", body: JSON.stringify({ name }),
      });
      if (!safeId.test(project.id)) throw new Error("invalid_project_response");
      setProjects((previous) => [project, ...previous.filter((row) => row.id !== project.id)]);
      setSelectedId(project.id);
      setNewName("");
      setCreating(false);
      setEditing(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "unavailable"); }
    finally { setBusy(false); }
  }

  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = editName.trim();
    if (!selected || !name || name.length > 160 || busy) return;
    setBusy(true);
    setError("");
    try {
      const { project } = await projectRequest<ProjectResult>(`/${selected.id}`, {
        method: "PATCH", body: JSON.stringify({ name }),
      });
      if (project.id !== selected.id) throw new Error("invalid_project_response");
      setProjects((previous) => previous.map((row) => row.id === project.id ? project : row));
      setEditing(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "unavailable"); }
    finally { setBusy(false); }
  }

  return (
    <section className="meo-projects" aria-label={t("meo.projects.title")}>
      <header className="meo-projects-header">
        <div>
          <h1>{t("meo.projects.title")}</h1>
          <p>{t("meo.projects.cloudScope")}</p>
        </div>
        <button type="button" className="meo-projects-action" disabled={busy}
          onClick={() => setCreating((value) => !value)}>
          {creating ? t("meo.projects.cancel") : t("meo.projects.new")}
        </button>
      </header>
      {creating && (
        <form className="meo-projects-form" onSubmit={(event) => void create(event)}>
          <label htmlFor="meo-new-project">{t("meo.projects.name")}</label>
          <div className="meo-projects-form-row">
            <input id="meo-new-project" value={newName} maxLength={160} disabled={busy}
              onChange={(event) => setNewName(event.target.value)} autoFocus />
            <button type="submit" disabled={busy || !newName.trim()}>{t("meo.projects.create")}</button>
          </div>
        </form>
      )}
      {error && <div role="alert" className="meo-projects-error">
        {t("meo.projects.requestFailed")}: {error}
        <button type="button" disabled={busy || loading} onClick={() => void load()}>
          {t("meo.projects.retry")}
        </button>
      </div>}
      {loading ? <p role="status">{t("meo.projects.loading")}</p>
      : !error && projects.length === 0
        ? <p className="meo-projects-empty">{t("meo.projects.empty")}</p>
        : (
          <div className="meo-projects-layout">
            <nav className="meo-projects-list" aria-label={t("meo.projects.title")}>
              {projects.map((project) => (
                <button key={project.id} type="button" className={selectedId === project.id ? "active" : ""}
                  aria-current={selectedId === project.id ? "true" : undefined}
                  onClick={() => { setSelectedId(project.id); setEditing(false); }}>
                  <strong>{project.name}</strong>
                  <span>{project.description || t("meo.projects.noDescription")}</span>
                </button>
              ))}
            </nav>
            {selected && <article className="meo-projects-details">
              <h2>{selected.name}</h2>
              <p>{t("meo.projects.contextNote")}</p>
              {editing ? <form className="meo-projects-form" onSubmit={(event) => void rename(event)}>
                <label htmlFor="meo-rename-project">{t("meo.projects.name")}</label>
                <div className="meo-projects-form-row">
                  <input id="meo-rename-project" value={editName} maxLength={160} disabled={busy}
                    onChange={(event) => setEditName(event.target.value)} autoFocus />
                  <button type="submit" disabled={busy || !editName.trim()}>{t("meo.projects.save")}</button>
                  <button type="button" disabled={busy} onClick={() => setEditing(false)}>
                    {t("meo.projects.cancel")}
                  </button>
                </div>
              </form> : <button type="button" className="meo-projects-action" disabled={busy}
                onClick={() => { setEditName(selected.name); setEditing(true); }}>
                {t("meo.projects.rename")}
              </button>}
            </article>}
          </div>
        )}
    </section>
  );
}
