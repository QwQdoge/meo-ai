import { useEffect, useState } from "react";
import { Icon } from "./icons";
import type { Action } from "./useCore";

type Act = (action: Action | null | undefined) => void;
type Spec = Record<string, any>;

const TILES = ["#1a73e8", "#0f766e", "#c2410c", "#7c3aed", "#db2777", "#ca8a04", "#0369a1", "#15803d"];

function tint(name: string): string {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TILES[h % TILES.length];
}

/** The app mark: a brand glyph (`svg` path), a named glyph, or a letter tile when the core has none. */
export function AppIcon({ icon, name, size = 48 }: { icon?: Spec | null; name: string; size?: number }) {
  const color: string | undefined = icon?.color || undefined;
  let inner: React.ReactNode;
  let bg: string | undefined;
  if (icon?.svg) {
    inner = <svg viewBox="0 0 24 24" width={size * 0.56} height={size * 0.56} aria-hidden><path d={icon.svg} fill={color ?? "currentColor"} /></svg>;
  } else if (icon?.glyph) {
    inner = <span style={{ color: color ?? "currentColor", display: "grid" }}><Icon name={icon.glyph} size={size * 0.5} /></span>;
  } else {
    bg = tint(name);
    inner = <b style={{ color: "#fff", fontSize: size * 0.42 }}>{(name.match(/[\p{L}\p{N}]/u)?.[0] ?? "?").toUpperCase()}</b>;
  }
  return <span className="store-icon" style={{ width: size, height: size, background: bg }} aria-hidden>{inner}</span>;
}

function openLink(url: string) {
  if (/^https:\/\//.test(url)) window.open(url, "_blank", "noopener,noreferrer");
}

export default function StorePage({ page, act }: { page: Spec; act: Act }) {
  const [query, setQuery] = useState<string>(page.search?.value ?? "");
  useEffect(() => setQuery(page.search?.value ?? ""), [page.search?.value]);
  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    act({ ...page.search.action, [page.search.field]: query });
  };
  const run = (action: Spec) => (action.type === "open_link" ? openLink(String(action.url)) : act(action as Action));
  return (
    <main className="core-page store">
      <header className="store-head">
        <h1>{page.title}</h1>
        {page.loading && <div className="core-spinner" role="progressbar" />}
      </header>
      <form className="store-search" role="search" onSubmit={submit}>
        <Icon name="search" size={20} />
        <input value={query} placeholder={page.search?.placeholder} aria-label={page.search?.placeholder} onChange={(e) => setQuery(e.target.value)} />
        {query && <button type="button" className="core-icon-btn" aria-label="Clear" onClick={() => { setQuery(""); act({ ...page.search.action, [page.search.field]: "" }); }}><Icon name="close" size={18} /></button>}
      </form>
      <div className="store-tabs" role="tablist">
        {(page.tabs ?? []).map((t: Spec) => (
          <button key={t.id} role="tab" aria-selected={t.selected} onClick={() => act(t.action)}>{t.label}</button>
        ))}
      </div>
      {(page.filters ?? []).length > 0 && (
        <div className="store-chips">
          {page.filters.map((f: Spec) => <button key={f.id} aria-pressed={f.selected} onClick={() => act(f.action)}>{f.label}</button>)}
        </div>
      )}
      {(page.sections ?? []).map((sec: Spec) => (
        <section key={sec.id} className="store-section">
          <h2>{sec.title}</h2>
          {sec.cards && (sec.cards.length === 0
            ? sec.empty && <p className="core-muted">{sec.empty}</p>
            : <div className="store-grid">{sec.cards.map((c: Spec) => <Card key={c.id} card={c} run={run} />)}</div>)}
          {sec.forms && <div className="store-forms">{sec.forms.map((f: Spec) => <ImportForm key={f.id} form={f} act={act} />)}</div>}
          {sec.links && (
            <ul className="store-links">
              {sec.links.map((l: Spec) => (
                <li key={l.url}><button onClick={() => openLink(l.url)}><strong>{l.title}</strong><span>{l.subtitle}</span></button></li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </main>
  );
}

function Card({ card, run }: { card: Spec; run: (a: Spec) => void }) {
  return (
    <article className="store-card" data-state={card.state}>
      <AppIcon icon={card.icon} name={card.title} size={36} />
      <div className="store-card-body">
        <h3>{card.title}</h3>
        <p className="store-pub">{card.publisher}</p>
        <p className="store-desc">{card.subtitle}</p>
        <div className="store-badges">
          {(card.badges ?? []).map((b: string) => <span key={b}>{b}</span>)}
          {card.state === "installed" && <span className="ok"><Icon name="check" size={12} /> Installed</span>}
        </div>
      </div>
      <div className="store-card-actions">
        {(card.actions ?? []).map((a: Spec, i: number) => (
          <button key={i} className={`core-button ${a.style ?? "secondary"}`} onClick={() => run(a.action)}>{a.label}</button>
        ))}
      </div>
    </article>
  );
}

function ImportForm({ form, act }: { form: Spec; act: Act }) {
  const [value, setValue] = useState("");
  const go = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    act({ ...form.action, [form.field]: value.trim() });
    setValue("");
  };
  return (
    <form className="store-form" onSubmit={go}>
      <div className="store-form-head"><AppIcon icon={form.icon} name={form.title} size={40} /><h3>{form.title}</h3></div>
      <p className="core-muted">{form.text}</p>
      <input value={value} placeholder={form.placeholder} aria-label={form.title} onChange={(e) => setValue(e.target.value)} />
      <button type="submit" className="core-button primary" disabled={!value.trim()}>{form.button}</button>
    </form>
  );
}
