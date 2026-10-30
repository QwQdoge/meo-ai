import React, { useEffect, useState, type ReactNode } from "react";
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

export function Blocks({ blocks, components, copy, copied, streaming, act }: { blocks: Spec[]; components?: Record<string, any>; copy: string; copied: string; streaming?: boolean; act?: (action: Spec) => void }): ReactNode {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.type === "callout") return <Callout key={i} block={b} components={components} />;
        if (b.type === "file" && act) return <FileCard key={i} block={b} act={act} />;
        if (b.type === "draft") return <DraftCard key={i} block={b} copy={copy} copied={copied} />;
        const last = streaming && i === blocks.length - 1;
        return <Markdown key={i} text={b.text + (last ? " ▍" : "")} components={components} />;
      })}
    </>
  );
}
