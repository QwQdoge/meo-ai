import React, { useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { prepareMath } from "./mathText.mjs";
import { Icon, hasIcon } from "./icons";

type Spec = Record<string, any>;

/** `:icon[name]:` inside Markdown becomes an inline icon (unknown names stay as written). */
function remarkIcons() {
  const pattern = /:icon\[([a-z0-9_]+)\]:/g;
  const walk = (node: any) => {
    if (!Array.isArray(node.children)) return;
    const next: any[] = [];
    for (const child of node.children) {
      if (child.type === "text" && pattern.test(child.value)) {
        pattern.lastIndex = 0;
        let last = 0;
        for (const m of child.value.matchAll(pattern)) {
          if (!hasIcon(m[1])) continue;
          if (m.index! > last) next.push({ type: "text", value: child.value.slice(last, m.index) });
          next.push({ type: "emphasis", children: [], data: { hName: "span", hProperties: { "data-icon": m[1] } } });
          last = m.index! + m[0].length;
        }
        if (last < child.value.length) next.push({ type: "text", value: child.value.slice(last) });
      } else {
        walk(child);
        next.push(child);
      }
    }
    node.children = next;
  };
  return (tree: any) => walk(tree);
}

type MathPlugins = { mathRemark: any[]; mathRehype: any[] };
let mathPlugins: MathPlugins | null = null;
let mathLoading: Promise<void> | null = null;

/** The math plugins, fetched the first time an answer contains something that looks like a formula. */
function useMathPlugins(text: string): MathPlugins | null {
  const needed = /\$|\\\(|\\\[/.test(text);
  const [, refresh] = useState(0);
  useEffect(() => {
    if (!needed || mathPlugins) return;
    mathLoading ??= import("./mathPlugins").then((m) => { mathPlugins = m; });
    let alive = true;
    void mathLoading.then(() => { if (alive) refresh((n) => n + 1); });
    return () => { alive = false; };
  }, [needed]);
  return needed ? mathPlugins : null;
}

export function Markdown({ text, components }: { text: string; components?: Record<string, any> }) {
  const math = useMathPlugins(text);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, ...(math ? math.mathRemark : []), remarkIcons]}
      rehypePlugins={math ? math.mathRehype : []}
      components={{
        ...components,
        span: ({ node: _node, ...props }: any) =>
          props["data-icon"] ? <Icon name={props["data-icon"]} className="inline" /> : <span {...props} />,
      }}
    >
      {math ? prepareMath(text) : text}
    </ReactMarkdown>
  );
}

/** A file the assistant wrote: the core owns its content and builds the bytes; the page only asks to save. */
export function FileCard({ block, act }: { block: Spec; act: (action: Spec) => void }) {
  return (
    <div className="core-filecard">
      <Icon name="description" size={22} />
      <div className="core-filecard-text">
        <strong>{block.name}</strong>
        <span className="core-muted">{block.kind}</span>
      </div>
      <button className="core-filecard-save" disabled={!block.action?.message} onClick={() => act(block.action)}>Download</button>
    </div>
  );
}

export function Callout({ block, components }: { block: Spec; components?: Record<string, any> }) {
  return (
    <aside className={`core-callout ${block.kind}`}>
      <header><Icon name={block.icon} size={16} /> <strong>{block.title}</strong></header>
      {block.text && <Markdown text={block.text} components={components} />}
    </aside>
  );
}

/** The run's goal and task list, updated in place while it works (`live`), kept with the answer after. */
export function PlanCard({ block, act }: { block: Spec; act?: (action: Spec) => void }) {
  const goal: Spec | null = block.goal ?? null;
  const items: Spec[] = block.items ?? [];
  const done = items.filter((t) => t.state === "done").length;
  const status: string = goal?.status ?? (items.length && done === items.length ? "done" : "active");
  const pct = items.length ? Math.round((done / items.length) * 100) : status === "done" ? 100 : 0;
  return (
    <section className={`core-plan ${status}${block.live ? " live" : ""}`} aria-live="polite">
      <header>
        <span className="core-plan-mark" key={status}>
          <Icon name={status === "done" ? "check_circle" : status === "blocked" ? "block" : status === "paused" ? "pause" : "flag"} size={16} />
        </span>
        <span className="core-plan-goal">{goal?.objective ?? "Tasks"}</span>
        {items.length > 0 && <span className="core-plan-count">{done}/{items.length}</span>}
      </header>
      {goal?.doneWhen && <p className="core-plan-when">{goal.doneWhen}</p>}
      {items.length > 0 && (
        <div className="core-plan-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <i style={{ width: `${pct}%` }} />
        </div>
      )}
      {items.length > 0 && (
        <ol>
          {items.map((t, i) => (
            <li key={i} className={`task-${t.state}`}>
              <span className="core-task-mark" key={t.state}>
                <Icon
                  name={t.state === "done" ? "check_circle" : t.state === "doing" ? "progress_activity" : "radio_button_unchecked"}
                  size={15}
                  className={t.state === "doing" && block.live ? "core-spin" : undefined}
                />
              </span>
              <span className="core-task-title">{t.title}</span>
            </li>
          ))}
        </ol>
      )}
      {goal?.note && <p className="core-plan-note">{goal.note}</p>}
      {act && goal?.maxRounds != null && <p className="core-plan-note">Rounds {goal.roundsUsed ?? 0}/{goal.maxRounds}</p>}
      {act && (block.actions ?? []).length > 0 && (
        <div className="core-plan-actions">
          {(block.actions as Spec[]).map((a, i) => (
            <button key={i} className="core-plan-btn" disabled={!!a.disabled} onClick={() => act(a.action)}>
              {a.icon && <Icon name={a.icon} size={14} />} {a.label}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

/** The model's question or the plan review, inside the chat: options as buttons, a field for a free
 *  answer, Answer/Skip (or Approve/Keep planning). It stays open until answered; the composer stays free. */
export function QuestionCard({ block, act }: { block: Spec; act: (action: Spec) => void }) {
  const [value, setValue] = useState("");
  const run = (a: Spec) => act(a.withInput ? { ...a.action, text: value } : a.action);
  const [primary, secondary] = (block.actions ?? []) as Spec[];
  return (
    <section className="core-question" aria-live="polite">
      <header>
        <Icon name={block.kind === "plan" ? "flag" : "psychology"} size={16} />
        <span>{block.title}</span>
        {block.step && String(block.step).split("/")[1] !== "1" && <span className="core-question-step">{block.step}</span>}
      </header>
      {block.text && <p className="core-question-text">{block.text}</p>}
      {(block.choices ?? []).length > 0 && (
        <div className="core-question-choices" role="group">
          {(block.choices as Spec[]).map((c, i) => (
            <button key={i} className={`core-choice${c.selected ? " selected" : ""}`} aria-pressed={!!c.selected} onClick={() => act(c.action)}>
              <strong>{c.selected ? "✓ " : ""}{c.label}</strong>
              {c.description && <span className="core-muted">{c.description}</span>}
            </button>
          ))}
        </div>
      )}
      {block.input && (block.input.multiline ? (
        <textarea rows={3} value={value} placeholder={block.input.placeholder} onChange={(e) => setValue(e.target.value)} />
      ) : (
        <input
          type="text" autoComplete="off" value={value} placeholder={block.input.placeholder}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && primary && run(primary)}
        />
      ))}
      <div className="core-question-actions">
        {secondary && <button className="core-button secondary" onClick={() => run(secondary)}>{secondary.label}</button>}
        {primary && <button className={`core-button ${primary.style ?? "primary"}`} onClick={() => run(primary)}>{primary.label}</button>}
      </div>
    </section>
  );
}

/** A ready-to-use draft (email, message): variants as tabs, subject, body, copy. */
export function DraftCard({ block, copy, copied }: { block: Spec; copy: string; copied: string }) {
  const variants: Spec[] = block.variants ?? [];
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(false);
  const v = variants[Math.min(index, variants.length - 1)] ?? {};
  const text = (v.subject ? `${v.subject}\n\n` : "") + (v.body ?? "");
  return (
    <section className="core-draft">
      {block.title && <header className="core-draft-title">{block.title}</header>}
      {variants.length > 1 && (
        <div className="core-draft-tabs" role="tablist">
          {variants.map((x, i) => (
            <button key={i} role="tab" aria-selected={i === index} onClick={() => setIndex(i)}>
              <span className="core-draft-letter">{String.fromCharCode(65 + i)}</span> {x.label}
            </button>
          ))}
        </div>
      )}
      {v.subject && <div className="core-draft-subject"><span className="core-muted">Subject:</span> {v.subject}</div>}
      <div className="core-draft-body">{v.body}</div>
      <footer>
        <button
          onClick={() => {
            void navigator.clipboard?.writeText(text).then(() => {
              setDone(true);
              setTimeout(() => setDone(false), 1200);
            });
          }}
        >
          <Icon name={done ? "check" : "content_copy"} /> {done ? copied : copy}
        </button>
      </footer>
    </section>
  );
}

/** Text that arrives in bursts is shown flowing: each frame reveals part of what has not been shown yet (more when
 *  far behind, a character at a time when close), so streamed answers read smoothly instead of jumping by chunk. */
function SmoothMarkdown({ text, components }: { text: string; components?: Record<string, any> }) {
  const [shown, setShown] = useState(0);
  const target = useRef(text);
  target.current = text;
  useEffect(() => {
    if (document.documentElement.dataset.reduceMotion === "true") return;
    let frame = 0;
    const tick = () => {
      setShown((n) => {
        const goal = target.current.length;
        if (n >= goal) return goal;
        const step = Math.max(1, Math.ceil((goal - n) * 0.12));
        return Math.min(goal, n + step);
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  const reduce = typeof document !== "undefined" && document.documentElement.dataset.reduceMotion === "true";
  const n = reduce ? text.length : Math.min(shown, text.length);
  // Never cut inside a surrogate pair.
  const cut = n > 0 && n < text.length && /[\uD800-\uDBFF]/.test(text[n - 1]) ? n + 1 : n;
  return <Markdown text={text.slice(0, cut)} components={components} />;
}

export function Blocks({ blocks, components, copy, copied, streaming, act }: { blocks: Spec[]; components?: Record<string, any>; copy: string; copied: string; streaming?: boolean; act?: (action: Spec) => void }): ReactNode {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.type === "callout") return <Callout key={i} block={b} components={components} />;
        if (b.type === "file" && act) return <FileCard key={i} block={b} act={act} />;
        if (b.type === "plan") return <PlanCard key="plan" block={b} act={act} />;
        if (b.type === "question" && act) return <QuestionCard key={`${b.title}|${b.text}`} block={b} act={act} />;
        if (b.type === "draft") return <DraftCard key={i} block={b} copy={copy} copied={copied} />;
        const last = streaming && i === blocks.length - 1;
        // The caret is drawn by CSS after the last character, so it never changes how the text parses.
        return last ? <div key={i} className="core-tail"><SmoothMarkdown text={b.text} components={components} /></div> : <Markdown key={i} text={b.text} components={components} />;
      })}
    </>
  );
}
