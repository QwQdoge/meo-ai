import React, { useEffect, useRef, useState, type ReactNode } from "react";
import { Blocks } from "./rich";
import { Icon, hasIcon } from "./icons";
import browserHost from "./browserHost";

// Formats the core reads itself (PDF, Word, Excel, PowerPoint, RTF): the page only hands over the bytes.
const documentExtensions = ["pdf", "docx", "xlsx", "pptx", "rtf"];

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
import { useCore, type Action, type View } from "./useCore";
import "./core.css";
import "./shell.css";

// Generic renderer for the Meo AI core view (meo/docs/cloud-core-view.md). It
// knows component kinds only, never product features: navigation, pages,
// settings and buttons come from the core, and every interaction sends back the
// action object attached to the element.

type Act = (action: Action | null | undefined) => void;
type Spec = Record<string, any>;

export default function CoreApp() {
  const { view, act, error } = useCore();
  const [drawer, setDrawer] = useState(false);
  const prefs: Spec = view.prefs ?? {};
  const strings: Spec = view.strings ?? {};

  useEffect(() => {
    const theme = ["light", "dark"].includes(prefs["appearance.theme"]) ? prefs["appearance.theme"] : "system";
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.reduceMotion = String(prefs["appearance.reduce_motion"] === true);
  }, [prefs]);

  if (error) {
    return (
      <main className="core-center" role="alert">
        <h1>Meo AI</h1>
        <p>Could not start the Meo AI core: {error}</p>
      </main>
    );
  }
  if (!view.page) return <main className="core-center" aria-busy="true" />;

  const page: Spec = view.page;
  return (
    <div className={`core-app${drawer ? " drawer-open" : ""}`} data-mode={view.route === "work" ? "work" : "chat"}>
      {view.sidebar && <Sidebar sidebar={view.sidebar} strings={strings} act={act} open={drawer} setOpen={setDrawer} />}
      {view.sidebar && drawer && <div className="core-drawer-scrim" onClick={() => setDrawer(false)} />}
      {view.dialog && <Dialog dialog={view.dialog} act={act} />}
      <div className="core-main">
        {view.sidebar && (
          <div className="core-appbar">
            <button className="core-icon-btn" aria-label="Menu" onClick={() => setDrawer((v) => !v)}><Icon name="menu" size={22} /></button>
            <img src="/meo-ai.svg" alt="" width={24} height={24} />
            <strong>Meo AI</strong>
          </div>
        )}
        {view.notice && (
          <Banner error={view.notice.kind === "error"} action={view.notice.actionLabel ?? strings.dismiss ?? "Dismiss"} onAction={() => act(view.notice.action)}>
            {view.notice.text}
          </Banner>
        )}
        {view.online === false && <Banner>{strings.offline ?? "Offline — showing saved data"}</Banner>}
        <Page page={page} prefs={prefs} strings={strings} act={act} work={view.route === "work"} />
      </div>
    </div>
  );
}

const glyph = (name: string, size = 18): ReactNode => (hasIcon(name) ? <Icon name={name} size={size} /> : <span>•</span>);

/** Claude-style left column: Chat | Work switch, search, new chat, plugins, projects tree, chats. */
function Sidebar({ sidebar, strings, act, open, setOpen }: { sidebar: Spec; strings: Spec; act: Act; open: boolean; setOpen: (v: boolean) => void }) {
  const go = (a: Action | undefined) => { setOpen(false); act(a); };
  const collapsed = !!sidebar.collapsed;
  const row = (item: Spec, depth = 0): ReactNode => (
    <li key={item.id} className="core-chat-row" style={{ paddingInlineStart: depth * 14 }}>
      <button aria-current={item.selected ? "true" : undefined} onClick={() => go(item.action)}>
        <strong>{item.title}</strong>
        {item.subtitle && <span>{item.subtitle}</span>}
      </button>
      {(item.menu ?? []).length > 0 && <RowMenu menu={item.menu} act={act} label={strings.more ?? "More"} />}
    </li>
  );
  return (
    <aside className={`core-sidebar${collapsed ? " collapsed" : ""}${open ? " open" : ""}`} aria-label="Meo AI">
      <div className="core-side-top">
        <div className="core-modes" role="tablist">
          {(sidebar.modes ?? []).map((m: Spec) => (
            <button key={m.id} role="tab" aria-selected={!!m.selected} title={m.label} onClick={() => go(m.action)}>
              {glyph(m.icon)}{!collapsed && <span>{m.label}</span>}
            </button>
          ))}
        </div>
        <button className="core-icon-btn core-collapse" aria-label="Collapse sidebar" onClick={() => act(sidebar.toggle)}>{glyph(collapsed ? "expand" : "collapse", 20)}</button>
      </div>
      {!collapsed && sidebar.search && <SearchBox search={sidebar.search} act={act} />}
      {sidebar.newChat && (
        <button className="core-newchat" title={sidebar.newChat.label} onClick={() => go(sidebar.newChat.action)}>
          {glyph("add", 20)}{!collapsed && <span>{sidebar.newChat.label}</span>}
        </button>
      )}
      <div className="core-side-scroll">
        {(sidebar.sections ?? []).map((sec: Spec) => (
          <section key={sec.id} className="core-side-section">
            {sec.kind === "list" ? (
              !collapsed && (
                <>
                  <h2>{sec.label}</h2>
                  {(sec.tabs ?? []).length > 0 && (
                    <div className="core-tabs" role="tablist">
                      {sec.tabs.map((tab: Spec, i: number) => (
                        <button key={i} role="tab" aria-selected={!!tab.selected} onClick={() => act(tab.action)}>{tab.label}</button>
                      ))}
                    </div>
                  )}
                  <ul className="core-list">{(sec.items ?? []).map((i: Spec) => row(i))}</ul>
                </>
              )
            ) : (
              <>
                <button className="core-side-link" aria-current={sec.selected ? "page" : undefined} title={sec.label} onClick={() => go(sec.action)}>
                  {glyph(sec.icon)}{!collapsed && <span>{sec.label}</span>}
                </button>
                {!collapsed && sec.kind === "tree" && (
                  <ul className="core-list">
                    {(sec.items ?? []).map((p: Spec) => (
                      <React.Fragment key={p.id}>
                        {row(p, 1)}
                        {(p.children ?? []).map((c: Spec) => row(c, 2))}
                      </React.Fragment>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>
        ))}
      </div>
      <div className="core-side-foot">
        {(sidebar.footer ?? []).map((f: Spec) => (
          <button key={f.id} className="core-side-link" aria-current={f.selected ? "page" : undefined} title={f.label} onClick={() => go(f.action)}>
            {glyph(f.icon)}{!collapsed && <span>{f.label}</span>}
          </button>
        ))}
      </div>
    </aside>
  );
}

function Banner(props: { children: ReactNode; error?: boolean; action?: string; onAction?: () => void }) {
  return (
    <div className={`core-banner${props.error ? " error" : ""}`} role={props.error ? "alert" : "status"}>
      <span>{props.children}</span>
      {props.action && <button onClick={props.onAction}>{props.action}</button>}
    </div>
  );
}

/** Generic modal question from the core: `prompt` has a text field, `confirm` does not. */
function Dialog({ dialog, act }: { dialog: Spec; act: Act }) {
  const [value, setValue] = useState<string>(dialog.input?.value ?? "");
  const run = (a: Spec) => act(a.withInput ? { ...a.action, text: value } : a.action);
  const [confirm, cancel] = dialog.actions ?? [];
  return (
    <div className="core-scrim" onKeyDown={(e) => e.key === "Escape" && act({ type: "close_dialog" })}>
      <div className="core-dialog" role="dialog" aria-modal="true" aria-label={dialog.title}>
        <h2>{dialog.title}</h2>
        {dialog.text && <p className="core-muted">{dialog.text}</p>}
        {dialog.input && dialog.input.multiline ? (
          <textarea autoFocus rows={5} value={value} placeholder={dialog.input.placeholder} onChange={(e) => setValue(e.target.value)} />
        ) : (
          dialog.input && (
            <input
              autoFocus
              type={dialog.input.secret ? "password" : "text"}
              autoComplete="off"
              value={value}
              placeholder={dialog.input.placeholder}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && confirm && run(confirm)}
            />
          )
        )}
        <div className="core-dialog-actions">
          {cancel && <button className="core-button secondary" onClick={() => run(cancel)}>{cancel.label}</button>}
          {confirm && <button className={`core-button ${confirm.style ?? "primary"}`} onClick={() => run(confirm)}>{confirm.label}</button>}
        </div>
      </div>
    </div>
  );
}

function Page({ page, prefs, strings, act, work }: { page: Spec; prefs: Spec; strings: Spec; act: Act; work?: boolean }) {
  switch (page.kind) {
    case "sign_in":
      return <SignIn page={page} act={act} />;
    case "conversation":
      return <Conversation page={page} prefs={prefs} strings={strings} act={act} work={work} />;
    case "list":
      return <ListPage page={page} act={act} />;
    case "settings":
      return <SettingsPage page={page} act={act} />;
    default:
      return <Unavailable page={page} act={act} />;
  }
}

function Button({ spec, act }: { spec: Spec; act: Act }) {
  return (
    <button className={`core-button ${spec.style ?? "secondary"}`} onClick={() => act(spec.action)}>
      {spec.label}
    </button>
  );
}

function SignIn({ page, act }: { page: Spec; act: Act }) {
  return (
    <main className="core-center">
      <img src="/meo-ai.svg" alt="" width={72} height={72} />
      <h1>{page.title}</h1>
      <p>{page.text}</p>
      {page.busy && <div className="core-spinner" role="progressbar" aria-label="Signing in" />}
      {(page.actions ?? []).map((a: Spec, i: number) => <Button key={i} spec={a} act={act} />)}
    </main>
  );
}

function Unavailable({ page, act }: { page: Spec; act: Act }) {
  return (
    <main className="core-center">
      <h1>{page.title}</h1>
      <p>{page.text}</p>
      {(page.actions ?? []).map((a: Spec, i: number) => <Button key={i} spec={a} act={act} />)}
    </main>
  );
}

function ListPage({ page, act }: { page: Spec; act: Act }) {
  return (
    <main className="core-page">
      <header className="core-header">
        <h1>{page.title}</h1>
        {(page.actions ?? []).map((a: Spec, i: number) => <Button key={i} spec={a} act={act} />)}
      </header>
      {page.loading && <div className="core-spinner" role="progressbar" />}
      {page.empty && <p className="core-muted">{page.empty.title}</p>}
      <ul className="core-list">
        {(page.items ?? []).map((item: Spec) => (
          <li key={item.id}>
            <button disabled={!item.action} onClick={() => act(item.action)}>
              <strong>{item.title}</strong>
              {item.subtitle && <span>{item.subtitle}</span>}
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}

function SettingsPage({ page, act }: { page: Spec; act: Act }) {
  const sections: Spec[] = page.sections ?? [];
  const current = sections.find((x) => x.id === page.selected) ?? sections[0];
  return (
    <main className="core-settings">
      <div className="core-settings-card">
        <nav className="core-settings-nav" aria-label={page.title}>
          {(page.nav ?? []).map((group: Spec) => (
            <div key={group.label}>
              <h3>{group.label}</h3>
              {(group.items ?? []).map((entry: Spec) => (
                <button key={entry.id} aria-current={entry.selected ? "page" : undefined} onClick={() => act(entry.action)}>{entry.label}</button>
              ))}
            </div>
          ))}
        </nav>
        <div className="core-settings-body">
          <header className="core-header">
            <h1>{current?.label ?? page.title}</h1>
            {page.close && <button className="core-close" aria-label="Close" onClick={() => act(page.close)}>✕</button>}
          </header>
          <div className="core-section">
            {(current?.items ?? []).map((item: Spec) => <Control key={item.id} item={item} act={act} />)}
          </div>
        </div>
      </div>
    </main>
  );
}

const setting = (item: Spec, value: unknown): Action => ({ type: "set_setting", binding: item.binding, value });

function Control({ item, act }: { item: Spec; act: Act }) {
  const [text, setText] = useState<string>(String(item.value ?? ""));
  useEffect(() => {
    setText(String(item.value ?? ""));
  }, [item.value]);
  const commit = () => text !== String(item.value ?? "") && act(setting(item, text));
  switch (item.kind) {
    case "toggle":
      return (
        <label className="core-row">
          <span>{item.label}</span>
          <input type="checkbox" role="switch" checked={item.value === true} onChange={(e) => act(setting(item, e.target.checked))} />
        </label>
      );
    case "slider": {
      const options: Spec[] = item.options ?? [];
      const index = Math.max(0, options.findIndex((o) => o.value === item.value));
      return (
        <label className="core-slider" title={options[index]?.label}>
          <span>{item.label}</span>
          <input type="range" min={0} max={options.length - 1} step={1} value={index} aria-valuetext={options[index]?.label}
            onChange={(e) => act(setting(item, options[Number(e.target.value)].value))} />
          <small className="core-muted">{options[index]?.label}</small>
        </label>
      );
    }
    case "select":
      return (
        <label className="core-field">
          <span>{item.label}</span>
          <select value={item.value ?? ""} onChange={(e) => act(setting(item, e.target.value))}>
            {!(item.options ?? []).some((o: Spec) => o.value === item.value) && <option value="">—</option>}
            {(item.options ?? []).map((o: Spec) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
      );
    case "text":
      return (
        <label className="core-field">
          <span>{item.label}</span>
          {item.single_line ? (
            <input value={text} placeholder={item.placeholder} onChange={(e) => setText(e.target.value)} onBlur={commit}
              onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && commit()} />
          ) : (
            <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} />
          )}
        </label>
      );
    case "hint":
      return <p className="core-hint core-muted">{item.text}</p>;
    case "stats":
      return (
        <div className="core-stats">
          {(item.items ?? []).map((t: Spec) => (
            <div key={t.label}><strong>{t.value}</strong><span className="core-muted">{t.label}</span></div>
          ))}
        </div>
      );
    case "bars": {
      const peak = Math.max(1, ...(item.items ?? []).map((b: Spec) => b.value));
      return (
        <div className="core-bars-wrap">
          <span className="core-muted">{item.label}</span>
          <div className="core-bars" role="img" aria-label={item.label}>
            {(item.items ?? []).map((b: Spec) => (
              <i key={b.label} title={`${b.label}: ${Math.round(b.value).toLocaleString()}`} style={{ height: `${Math.max(3, (b.value / peak) * 100)}%` }} />
            ))}
          </div>
        </div>
      );
    }
    case "info":
      return (
        <div className="core-row"><span>{item.label}</span><span className="core-muted">{String(item.value ?? "")}</span></div>
      );
    case "item":
      return (
        <div className="core-item">
          <div className="core-item-text">
            <span>{item.label}</span>
            {item.value && <small className="core-muted">{item.value}</small>}
          </div>
          {(item.buttons ?? []).map((b: Spec, i: number) => <Button key={i} spec={b} act={act} />)}
        </div>
      );
    case "button":
      return <Button spec={item} act={act} />;
    default:
      return null;
  }
}

/** Fenced code from a model answer, with a language label and a copy button. */
function CodeBlock({ node, children, label, done }: { node?: any; children?: React.ReactNode; label: string; done: string }) {
  const code = node?.children?.[0];
  const language = String(code?.properties?.className?.[0] ?? "").replace("language-", "") || "code";
  const text = (code?.children ?? []).map((c: any) => c.value ?? "").join("");
  return (
    <div className="core-code">
      <div className="core-code-head">
        <span>{language}</span>
        <span className="core-code-actions">
          <CopyButton text={text} label={label} done={done} />
        </span>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function CopyButton({ text, label, done: doneLabel }: { text: string; label: string; done: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        });
      }}
    >
      {done ? doneLabel : label}
    </button>
  );
}

/** Debounced search field; the text is sent as `text` on the search action. */
function SearchBox({ search, act }: { search: Spec; act: Act }) {
  const [text, setText] = useState<string>(search.value ?? "");
  useEffect(() => {
    if (text === (search.value ?? "")) return;
    const timer = setTimeout(() => act({ ...search.action, text }), 300);
    return () => clearTimeout(timer);
  }, [text]);
  return (
    <input
      type="search"
      className="core-search"
      value={text}
      placeholder={search.placeholder}
      onChange={(e) => setText(e.target.value)}
    />
  );
}

function RowMenu({ menu, act, label }: { menu: Spec[]; act: Act; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="core-row-menu">
      <button aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} onBlur={() => setTimeout(() => setOpen(false), 150)}><Icon name="more" size={18} /></button>
      {open && (
        <ul role="menu">
          {menu.map((m, i) => (
            <li key={i} role="menuitem">
              <button className={m.style === "danger" ? "danger" : undefined} onMouseDown={(e) => e.preventDefault()} onClick={() => { setOpen(false); act(m.action); }}>{m.label}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One collapsible part of the details card: icon rows, a usage bar, step rows, links. */
function InspectorSection({ sec }: { sec: Spec }) {
  const [open, setOpen] = useState(sec.open !== false);
  const total = Math.max(1, ...[(sec.bar?.segments ?? []).reduce((n: number, x: Spec) => n + x.value, 0)]);
  return (
    <section className="core-isec">
      <button className="core-isec-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{sec.title}</span><Icon name={open ? "expand_more" : "chevron_right"} size={14} />
      </button>
      {open && (
        <div className="core-isec-body">
          {sec.bar && (
            <>
              <div className="core-bar" role="img" aria-label={sec.bar.label}>
                {sec.bar.segments.map((x: Spec, i: number) => <i key={i} className={`seg${i}`} style={{ flexGrow: x.value / total }} title={`${x.label}: ${x.value}`} />)}
              </div>
              <div className="core-muted core-bar-label">{sec.bar.label}</div>
            </>
          )}
          {(sec.rows ?? []).filter((r: Spec) => r.label).map((r: Spec, i: number) => (
            <div key={i} className="core-irow">
              {r.icon && <Icon name={r.icon} />}
              {r.status && <span className={`dot ${r.status}`} aria-hidden />}
              <span className="label">{r.label}</span>
              {r.value != null && <span className="core-muted">{r.value}</span>}
            </div>
          ))}
          {(sec.files ?? []).map((f: Spec) => (
            <details key={f.path} className="core-change">
              <summary>
                <Icon name="description" size={14} />
                <span className="label">{f.path}</span>
                <span className="core-change-stat"><b className="add">+{f.added}</b> <b className="del">−{f.removed}</b></span>
                <em className={`core-change-state ${f.state}`}>{f.state}</em>
              </summary>
              <pre className="core-diff">
                {String(f.diff).split("\n").map((line, i) => (
                  <span key={i} className={line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : line.startsWith("@@") ? "hunk" : ""}>{line + "\n"}</span>
                ))}
              </pre>
            </details>
          ))}
          {(sec.links ?? []).map((r: Spec, i: number) => (
            <div key={i} className="core-irow">
              {/^https?:\/\//.test(r.url ?? "") ? <a href={r.url} target="_blank" rel="noreferrer noopener">{r.title || r.url}</a> : <span className="label">{r.title}</span>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** Slider in a popover. It closes on an outside press or Escape, never on blur: blur/preventDefault
 * on the popover made the range thumb undraggable. */
function SliderChip({ item, act }: { item: Spec; act: Act }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const options: Spec[] = item.options ?? [];
  const index = Math.max(0, options.findIndex((o) => o.value === item.value));
  const current = options[index];
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="core-pop" ref={root}>
      <button className="core-chipbtn" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {current?.label ?? item.label} ▾
      </button>
      {open && (
        <div className="core-popover" role="dialog" aria-label={item.label}>
          <span className="core-muted">{item.label}</span>
          <input type="range" min={0} max={options.length - 1} step={1} value={index} aria-valuetext={current?.label}
            onChange={(e) => act(setting(item, options[Number(e.target.value)].value))} />
          <span>{current?.label}</span>
        </div>
      )}
    </span>
  );
}

/** Quiet one-line control under the composer (Claude style): text button, slider in a popover. */
function ControlChip({ item, act }: { item: Spec; act: Act }) {
  const [open, setOpen] = useState(false);
  const options: Spec[] = item.options ?? [];
  const current = options.find((o) => o.value === item.value);
  if (item.kind === "toggle" && item.icon) {
    return (
      <button className="core-chipbtn icon" aria-pressed={item.value === true} aria-label={item.label} title={item.label} onClick={() => act(setting(item, item.value !== true))}>
        <Icon name={item.icon} size={16} />
      </button>
    );
  }
  if (item.kind === "toggle") {
    return (
      <button className="core-chipbtn" aria-pressed={item.value === true} onClick={() => act(setting(item, item.value !== true))}>
        {item.value === true ? "● " : "○ "}{item.label}
      </button>
    );
  }
  if (item.kind === "select") {
    return (
      <select className="core-chipselect" aria-label={item.label} value={item.value ?? ""} onChange={(e) => act(setting(item, e.target.value))}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  }
  if (item.kind === "slider") {
    return <SliderChip item={item} act={act} />;
  }
  return <Control item={item} act={act} />;
}

/** Quick toggles (search, sub-agents) and the Work device, shown as chips next to the attach button. */
function FolderChip({ sendAction, act }: { sendAction?: Spec; act: Act }) {
  const [name, setName] = useState(browserHost.name);
  if (!browserHost.supported || !sendAction) return null;
  const choose = async () => {
    try {
      const picked = await browserHost.pick();
      setName(picked);
      act({ type: "send", ...sendAction, text: "/workspace " + picked });
    } catch {
      // The picker was closed without a choice.
    }
  };
  return (
    <button className="core-chip-toggle" aria-pressed={!!name} title="Open a folder Meo may read and edit (stays in this browser)" onClick={choose}>
      <Icon name="projects" size={16} /><span>{name || "Open folder"}</span>
    </button>
  );
}

function ComposerControls({ toolbar, act, work, sendAction }: { toolbar: Spec[]; act: Act; work?: boolean; sendAction?: Spec }) {
  // Work runs on a chosen online device. The core only offers the choice once a device is enrolled and
  // online; until then say so instead of hiding it, so the missing piece is visible.
  const hasDevice = toolbar.some((c) => c.id === "run_on");
  return (
    <>
      {work && <FolderChip sendAction={sendAction} act={act} />}
      {work && !hasDevice && (
        <span className="core-device reserved" title="No computer is online. Run meo-runner on a computer you own (see meo/docs/runner.md) and it appears here.">
          <Icon name="device" size={16} /><span>Cloud · no device</span>
        </span>
      )}
      {toolbar.filter((c) => c.id === "run_on").map((c) => <DeviceChip key={c.id} item={c} act={act} />)}
      {toolbar.filter((c) => c.kind === "toggle" && c.icon).map((c) => (
        <button key={c.id} className="core-chip-toggle" aria-pressed={c.value === true} title={c.label} onClick={() => act(setting(c, c.value !== true))}>
          <Icon name={c.icon} size={16} /><span>{c.label}</span>
        </button>
      ))}
    </>
  );
}

function DeviceChip({ item, act }: { item: Spec; act: Act }) {
  const options: Spec[] = item.options ?? [];
  return (
    <label className="core-device" title={item.label}>
      <Icon name="device" size={16} />
      <select aria-label={item.label} value={item.value ?? ""} onChange={(e) => act(setting(item, e.target.value))}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

/** One "Tune" sheet instead of a row of loose controls: ordered choices are sliders, the rest are selects. */
function TuneButton({ toolbar, act }: { toolbar: Spec[]; act: Act }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const items = toolbar.filter((c) => c.id !== "run_on" && !(c.kind === "toggle" && c.icon));
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (items.length === 0) return null;
  const summary = items
    .filter((c) => c.kind === "slider" || c.id === "mode")
    .map((c) => (c.options ?? []).find((o: Spec) => o.value === c.value)?.label)
    .filter(Boolean)
    .slice(0, 2)
    .join(" · ");
  return (
    <span className="core-pop" ref={root}>
      <button className="core-tune" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Icon name="tune" size={16} /><span>{summary || items[0].label}</span>
      </button>
      {open && (
        <div className="core-sheet" role="dialog">
          {items.map((item) => {
            const options: Spec[] = item.options ?? [];
            const index = Math.max(0, options.findIndex((o) => o.value === item.value));
            return (
              <div key={item.id} className="core-sheet-row">
                <div className="core-sheet-label">{item.icon && <Icon name={item.icon} size={16} />}<span>{item.label}</span>
                  {item.kind === "slider" && <b>{options[index]?.label}</b>}</div>
                {item.kind === "slider" ? (
                  <input type="range" min={0} max={options.length - 1} step={1} value={index} aria-label={item.label} aria-valuetext={options[index]?.label}
                    onChange={(e) => act(setting(item, options[Number(e.target.value)].value))} />
                ) : item.kind === "select" ? (
                  <select aria-label={item.label} value={item.value ?? ""} onChange={(e) => act(setting(item, e.target.value))}>
                    {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <ControlChip item={item} act={act} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </span>
  );
}

function Conversation({ page, prefs, strings, act, work }: { page: Spec; prefs: Spec; strings: Spec; act: Act; work?: boolean }) {
  const inspector: Spec = page.inspector ?? {};
  const area = useRef<HTMLTextAreaElement>(null);
  const messages: Spec[] = page.messages ?? [];
  const composer: Spec = page.composer ?? {};
  const end = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [dragging, setDragging] = useState(false);
  const [attachNote, setAttachNote] = useState("");
  const note = (text: string) => { setAttachNote(text); window.setTimeout(() => setAttachNote(""), 4000); };
  // One path for the picker, paste and drag-and-drop: pictures are shrunk, text files go in as text.
  const attachFiles = async (files: File[]) => {
    if (!composer.attach) return;
    const textTypes: string[] = composer.attach.extensions ?? [];
    for (const file of files) {
      const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
      if (file.type.startsWith("image/")) {
        const data = await shrinkImage(file);
        if (data) act({ type: "attach_image", name: file.name || "image.jpg", mime: "image/jpeg", data });
        else note(`Could not read ${file.name || "the picture"}`);
      } else if (documentExtensions.includes(ext) || file.type === "application/pdf") {
        if (file.size > 25 * 1024 * 1024) { note(`${file.name} is larger than 25 MB`); continue; }
        act({ type: "attach_document", name: file.name, data: toBase64(new Uint8Array(await file.arrayBuffer())) });
      } else if (file.size > 2 * 1024 * 1024) {
        note(`${file.name} is larger than 2 MB`);
      } else if (textTypes.includes(ext) || file.type.startsWith("text/") || (!ext && file.type === "")) {
        act({ type: composer.attach.action, name: file.name || "pasted.txt", text: await file.text() });
      } else {
        note(`${file.name}: this file type is not supported yet (PDF, Word, Excel, PowerPoint, text, code and pictures work)`);
      }
    }
  };
  const last = messages[messages.length - 1]?.text?.length ?? 0;

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, last]);

  const send = () => {
    const text = input.trim();
    if (!text || composer.busy || !composer.sendAction) return;
    act({ ...composer.sendAction, text });
    setInput("");
  };
  const enterSends = prefs["general.enter_to_send"] !== false;
  // Grow with the text up to half the window (the stylesheet also lets the user drag it taller).
  const fit = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, window.innerHeight / 2) + "px";
  };
  useEffect(() => { if (area.current) fit(area.current); }, [input]);
  const matches: Spec[] = /^\/\S*$/.test(input)
    ? (composer.commands ?? []).filter((c: Spec) => c.name.startsWith(input.toLowerCase()))
    : [];
  const pick = (c: Spec) => {
    if (c.hint) setInput(c.name + " ");
    else if (!composer.busy) {
      act({ ...composer.sendAction, text: c.name });
      setInput("");
    }
  };

  return (
    <div className="core-chat">
      <section className="core-thread">
        <header className="core-header">
          <h1>{page.title}</h1>
          {(page.menu ?? []).length > 0 && <RowMenu menu={page.menu} act={act} label={strings.more ?? "More"} />}
          {inspector.title && !inspector.visible && (
            <button className="core-chip" onClick={() => act(inspector.show)}>{inspector.title}</button>
          )}
        </header>
        <div className="core-messages">
          {inspector.visible && (
            <aside className="core-inspector" aria-label={inspector.title}>
              <header><strong>{inspector.title}</strong><button aria-label="Hide" onClick={() => act(inspector.hide)}>✕</button></header>
              {(inspector.sections ?? []).map((sec: Spec) => <InspectorSection key={sec.id} sec={sec} />)}
            </aside>
          )}
          {page.empty && (
            <div className="core-empty">
              <h2>{page.empty.title}</h2>
              <p className="core-muted">{page.empty.text}</p>
              <div className="core-chips">
                {(page.empty.suggestions ?? []).map((c: Spec, i: number) => (
                  <button key={i} className="core-suggest" onClick={() => act(c.action)}><Icon name="auto_awesome" size={18} /><span>{c.label}</span></button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`core-message ${m.role === "user" ? "user" : "assistant"}`}>
              {m.role === "user" ? (
                <div className="core-bubble user">{m.text}</div>
              ) : (
                <div className="core-bubble assistant">
                  {m.steps && (
                    <details className="core-steps" open={!!m.stepsOpen}>
                      <summary>{m.stepsLabel}</summary>
                      <ol>
                        {m.steps.map((st: Spec) => (
                          <li key={st.id} className={`step-${st.status}`}>
                            <details>
                              <summary>
                                <span className="core-step-mark" aria-hidden>
                                  {st.status === "done" ? <Icon name="check_circle" size={14} /> : st.status === "error" ? <Icon name="error" size={14} /> : <Icon name="progress_activity" size={14} className="spin" />}
                                </span>
                                <b>{st.title}</b>
                              </summary>
                              {st.detail ? <p className="core-muted">{st.detail}</p> : null}
                              {(st.items ?? []).length > 0 && (
                                <ul>
                                  {st.items.map((it: Spec, k: number) => (
                                    <li key={k}>{/^https?:\/\//.test(it.url) ? <a href={it.url} target="_blank" rel="noreferrer noopener">{it.title || it.url}</a> : it.title}</li>
                                  ))}
                                </ul>
                              )}
                            </details>
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                  <Blocks
                    blocks={m.blocks?.length ? m.blocks : [{ type: "markdown", text: m.text }]}
                    streaming={!!m.streaming}
                    act={act as (action: Spec) => void}
                    copy={strings.copy ?? "Copy"}
                    copied={strings.copied ?? "Copied"}
                    components={{ pre: (props: any) => <CodeBlock {...props} label={strings.copy ?? "Copy"} done={strings.copied ?? "Copied"} /> }}
                  />
                  {(m.images ?? []).map((img: Spec, k: number) => (
                    <span key={k} className="core-image-wrap">
                      <img className="core-image" src={img.url} alt="" loading="lazy" />
                      <a className="core-image-save" href={img.url} download={`meo-image-${k + 1}.png`} aria-label="Download">Download</a>
                    </span>
                  ))}
                </div>
              )}
              {!m.streaming && m.text && (
                <div className="core-message-actions">
                  <CopyButton text={m.text} label={strings.copy ?? "Copy"} done={strings.copied ?? "Copied"} />
                  {(m.actions ?? []).map((a: Spec, j: number) => (
                    <button key={j} onClick={() => act(a.action)}>{a.label}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={end} />
        </div>
        {page.consent && (
          <div className="core-banner" role="alertdialog" aria-label={page.consent.title}>
            <span><strong>{page.consent.title}</strong> {page.consent.text}</span>
            {(page.consent.actions ?? []).map((a: Spec, i: number) => <Button key={i} spec={a} act={act} />)}
          </div>
        )}
        <div
          className={`core-composer${dragging ? " dragging" : ""}`}
          onDragOver={(e) => { if (composer.attach && e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }}
          onDrop={(e) => {
            if (!composer.attach) return;
            e.preventDefault();
            setDragging(false);
            void attachFiles(Array.from(e.dataTransfer.files));
          }}
        >
          {attachNote && <p className="core-attach-note" role="status">{attachNote}</p>}
          {matches.length > 0 && (
            <ul className="core-commands" role="listbox">
              {matches.map((c: Spec) => (
                <li key={c.name}>
                  <button role="option" onClick={() => pick(c)}>
                    <b>{c.name}</b>{c.hint ? <i> {c.hint}</i> : null}<span className="core-muted"> {c.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {(page.files ?? []).length > 0 && (
            <div className="core-files">
              {page.files.map((f: Spec) => (
                <span key={f.id} className="core-chip">
                  {f.name} <small>{f.subtitle}</small>
                  <button aria-label={f.remove?.label} onClick={() => act(f.remove?.action)}>×</button>
                </span>
              ))}
            </div>
          )}
          <div className="core-input-box">
            <textarea
              ref={area}
              rows={1}
              value={input}
              placeholder={composer.placeholder}
              onChange={(e) => { setInput(e.target.value); fit(e.target); }}
              onPaste={(e) => {
                const files = Array.from(e.clipboardData.files);
                if (files.length === 0) return;
                e.preventDefault();
                void attachFiles(files);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape" && composer.busy) act(composer.stopAction);
                if (e.key === "Tab" && matches.length > 0) {
                  e.preventDefault();
                  setInput(matches[0].name + " ");
                }
                if (e.key === "Enter" && !e.nativeEvent.isComposing && enterSends !== e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div className="core-input-bar">
            {composer.attach && (
              <>
                <button className="core-icon-btn core-attach" aria-label={composer.attach.label} title={composer.attach.label} onClick={() => fileInput.current?.click()}><Icon name="attach" size={20} /></button>
                <input
                  ref={fileInput}
                  type="file"
                  hidden
                  multiple
                  accept={[...(composer.attach.extensions ?? []), ...documentExtensions].map((e: string) => "." + e).join(",")}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    e.target.value = "";
                    void attachFiles(files);
                  }}
                />
              </>
            )}
              <ComposerControls toolbar={composer.toolbar ?? []} act={act} work={work} sendAction={composer.sendAction} />
              <span className="core-spacer" />
              <TuneButton toolbar={composer.toolbar ?? []} act={act} />
            <button
                className="core-send"
                aria-label={composer.busy ? (strings.stop ?? "Stop") : (strings.send ?? "Send")}
                onClick={() => (composer.busy ? act(composer.stopAction) : send())}
              >
                {composer.busy ? <Icon name="stop" size={16} /> : <Icon name="arrow_up" size={20} />}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export type { View };

/** Downscale a picture to at most 1568 px and return it as base64 JPEG (no prefix), or null. */
async function shrinkImage(file: File): Promise<string | null> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1568 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.85, 0.7, 0.55, 0.4]) {
      const url = canvas.toDataURL("image/jpeg", quality);
      const data = url.slice(url.indexOf(",") + 1);
      if (data.length <= 1_800_000) return data;
    }
  } catch {
    // fall through
  }
  return null;
}
