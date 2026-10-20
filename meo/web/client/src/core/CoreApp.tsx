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
      <div className="core-main">
        {view.notice && (
          <Banner error={view.notice.kind === "error"} action="Dismiss" onAction={() => act(view.notice.action)}>
            {view.notice.text}
          </Banner>
        )}
        {view.online === false && <Banner>Offline — showing saved data</Banner>}
        <Page page={page} prefs={prefs} act={act} />
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

function Page({ page, prefs, act }: { page: Spec; prefs: Spec; act: Act }) {
  switch (page.kind) {
    case "sign_in":
      return <SignIn page={page} act={act} />;
    case "conversation":
      return <Conversation page={page} prefs={prefs} act={act} />;
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
    case "button":
      return <Button spec={item} act={act} />;
    default:
      return null;
  }
}

function Conversation({ page, prefs, act }: { page: Spec; prefs: Spec; act: Act }) {
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
        <h2>{sidebar.title}</h2>
        <ul className="core-list">
          {(sidebar.items ?? []).map((item: Spec) => (
            <li key={item.id}>
              <button aria-current={item.selected ? "true" : undefined} onClick={() => { setDrawer(false); act(item.action); }}>
                <strong>{item.title}</strong>
                <span>{item.subtitle}</span>
              </button>
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
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="core-bubble user">{m.text}</div>
            ) : (
              <div key={i} className="core-bubble assistant">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text + (m.streaming ? " ▍" : "")}</ReactMarkdown>
              </div>
            ),
          )}
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
              aria-label={composer.busy ? "Stop" : "Send"}
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
