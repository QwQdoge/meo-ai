import { useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useCore, type Action, type View } from "./useCore";
import "./core.css";

// Generic renderer for the Meo AI core view (meo/docs/cloud-core-view.md). It
// knows component kinds only, never product features: navigation, pages,
// settings and buttons come from the core, and every interaction sends back the
// action object attached to the element.

type Act = (action: Action | null | undefined) => void;
type Spec = Record<string, any>;

export default function CoreApp() {
  const { view, act, error } = useCore();
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

  const navigation: Spec[] = view.navigation ?? [];
  const page: Spec = view.page;
  return (
    <div className="core-app">
      {navigation.length > 0 && (
        <nav className="core-nav" aria-label="Meo AI">
          {navigation.map((item) => (
            <button
              key={item.id}
              className="core-nav-item"
              aria-current={item.selected ? "page" : undefined}
              onClick={() => act(item.action)}
            >
              <span aria-hidden="true" className="core-nav-dot" />
              {item.label}
            </button>
          ))}
        </nav>
      )}
      {view.dialog && <Dialog dialog={view.dialog} act={act} />}
      <div className="core-main">
        {view.notice && (
          <Banner error={view.notice.kind === "error"} action={strings.dismiss ?? "Dismiss"} onAction={() => act(view.notice.action)}>
            {view.notice.text}
          </Banner>
        )}
        {view.online === false && <Banner>{strings.offline ?? "Offline — showing saved data"}</Banner>}
        <Page page={page} prefs={prefs} strings={strings} act={act} />
      </div>
    </div>
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

function Page({ page, prefs, strings, act }: { page: Spec; prefs: Spec; strings: Spec; act: Act }) {
  switch (page.kind) {
    case "sign_in":
      return <SignIn page={page} act={act} />;
    case "conversation":
      return <Conversation page={page} prefs={prefs} strings={strings} act={act} />;
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
  return (
    <main className="core-page narrow">
      <header className="core-header"><h1>{page.title}</h1></header>
      {(page.sections ?? []).map((section: Spec) => (
        <section key={section.id} className="core-section">
          <h2>{section.label}</h2>
          {(section.items ?? []).map((item: Spec) => <Control key={item.id} item={item} act={act} />)}
        </section>
      ))}
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
      <button aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} onBlur={() => setTimeout(() => setOpen(false), 150)}>⋮</button>
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

function Conversation({ page, prefs, strings, act }: { page: Spec; prefs: Spec; strings: Spec; act: Act }) {
  const [drawer, setDrawer] = useState(false);
  const sidebar: Spec = page.sidebar ?? {};
  const messages: Spec[] = page.messages ?? [];
  const composer: Spec = page.composer ?? {};
  const end = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState("");
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

  return (
    <div className={`core-chat${drawer ? " drawer-open" : ""}`}>
      <aside className="core-sidebar" aria-label={sidebar.title}>
        {(sidebar.actions ?? []).map((a: Spec, i: number) => <Button key={i} spec={a} act={(x) => { setDrawer(false); act(x); }} />)}
        {sidebar.search && <SearchBox search={sidebar.search} act={act} />}
        {(sidebar.tabs ?? []).length > 0 && (
          <div className="core-tabs" role="tablist">
            {sidebar.tabs.map((tab: Spec, i: number) => (
              <button key={i} role="tab" aria-selected={!!tab.selected} onClick={() => act(tab.action)}>{tab.label}</button>
            ))}
          </div>
        )}
        <h2>{sidebar.title}</h2>
        <ul className="core-list">
          {(sidebar.items ?? []).map((item: Spec) => (
            <li key={item.id} className="core-chat-row">
              <button aria-current={item.selected ? "true" : undefined} onClick={() => { setDrawer(false); act(item.action); }}>
                <strong>{item.title}</strong>
                <span>{item.subtitle}</span>
              </button>
              {(item.menu ?? []).length > 0 && <RowMenu menu={item.menu} act={act} label={strings.more ?? "More"} />}
            </li>
          ))}
        </ul>
      </aside>
      <section className="core-thread">
        <header className="core-header">
          <button className="core-menu" aria-label={sidebar.title} onClick={() => setDrawer((open) => !open)}>☰</button>
          <h1>{page.title}</h1>
        </header>
        <div className="core-messages">
          {page.empty && (
            <div className="core-empty">
              <h2>{page.empty.title}</h2>
              <p className="core-muted">{page.empty.text}</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`core-message ${m.role === "user" ? "user" : "assistant"}`}>
              {m.role === "user" ? (
                <div className="core-bubble user">{m.text}</div>
              ) : (
                <div className="core-bubble assistant">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text + (m.streaming ? " ▍" : "")}</ReactMarkdown>
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
        <div className="core-composer">
          {(composer.toolbar ?? []).map((item: Spec) => <Control key={item.id} item={item} act={act} />)}
          <div className="core-input-row">
            <textarea
              rows={1}
              value={input}
              placeholder={composer.placeholder}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing && enterSends !== e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              className="core-button primary"
              aria-label={composer.busy ? (strings.stop ?? "Stop") : (strings.send ?? "Send")}
              onClick={() => (composer.busy ? act(composer.stopAction) : send())}
            >
              {composer.busy ? "■" : "↑"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export type { View };
