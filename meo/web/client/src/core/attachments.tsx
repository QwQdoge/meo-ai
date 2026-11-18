import { useEffect } from "react";
import { createPortal } from "react-dom";

// What a paste into the composer becomes. The page decides only what the clipboard holds; the core
// reads the files and keeps the text (see attach_document in the core).

/** A pasted text this long goes in as a Markdown file instead of filling the box. */
export const LONG_PASTE_CHARS = 3000;
export const LONG_PASTE_LINES = 60;

// Structure worth keeping when rich text is pasted: headings, lists, tables, code, quotes, emphasis, links.
const STRUCTURE = /<(h[1-6]|table|ul|ol|pre|blockquote|strong|b|em|a)\b/i;

export type PastePlan =
  | { kind: "files"; files: File[] }
  | { kind: "text-as-file"; markdown: string }
  | { kind: "default" };

// Apps that copy rich text (Notes, Word, a web page) often put a rendered picture of it on the
// clipboard too, named "image.png" or nothing. That picture is not a file the person copied.
const renderedPicture = (f: File) => f.type.startsWith("image/") && (!f.name || /^image\.\w+$/i.test(f.name));

export function planPaste(data: DataTransfer): PastePlan {
  const text = data.getData("text/plain");
  const html = data.getData("text/html");
  const files = Array.from(data.files);
  const hasText = text.trim() !== "";
  // Real files (a screenshot, a file from the file manager) are attached; text beats its own picture.
  if (files.length > 0 && !(hasText && files.every(renderedPicture))) return { kind: "files", files };
  if (!hasText) return { kind: "default" };
  const markdown = html && STRUCTURE.test(html) ? htmlToMarkdown(html) || text : text;
  const long = markdown.length >= LONG_PASTE_CHARS || markdown.split("\n").length >= LONG_PASTE_LINES;
  return long ? { kind: "text-as-file", markdown } : { kind: "default" };
}

const cell = (c: Element) => (c.textContent ?? "").replace(/\s+/g, " ").replace(/\|/g, "\\|").trim();

function table(t: Element): string {
  const rows = Array.from(t.querySelectorAll("tr")).map((tr) => Array.from(tr.children).map(cell));
  if (rows.length === 0) return "";
  const width = Math.max(...rows.map((r) => r.length));
  const line = (r: string[]) => `| ${Array.from({ length: width }, (_, i) => r[i] ?? "").join(" | ")} |`;
  return [line(rows[0]), `| ${Array(width).fill("---").join(" | ")} |`, ...rows.slice(1).map(line)].join("\n");
}

function listItems(list: Element, depth: number): string {
  const ordered = list.tagName.toLowerCase() === "ol";
  let n = 0;
  return Array.from(list.children)
    .filter((c) => c.tagName.toLowerCase() === "li")
    .map((li) => {
      n += 1;
      let text = "";
      const nested: string[] = [];
      for (const child of Array.from(li.childNodes)) {
        const tag = child.nodeType === 1 ? (child as Element).tagName.toLowerCase() : "";
        if (tag === "ul" || tag === "ol") nested.push(listItems(child as Element, depth + 1));
        else text += markdownOf(child, depth + 1);
      }
      const head = `${"  ".repeat(depth)}${ordered ? `${n}.` : "-"} ${text.trim().replace(/\n+/g, " ")}`;
      return nested.length ? `${head}\n${nested.join("\n")}` : head;
    })
    .join("\n");
}

function markdownOf(node: Node, depth: number): string {
  if (node.nodeType === 3) return (node.textContent ?? "").replace(/\s+/g, " ");
  if (node.nodeType !== 1) return "";
  const el = node as Element;
  const tag = el.tagName.toLowerCase();
  const kids = () => Array.from(el.childNodes).map((n) => markdownOf(n, depth)).join("");
  if (/^h[1-6]$/.test(tag)) return `\n\n${"#".repeat(Number(tag[1]))} ${kids().trim()}\n\n`;
  switch (tag) {
    case "script":
    case "style":
    case "head":
      return "";
    case "p":
    case "div":
    case "section":
    case "article":
      return `\n\n${kids().trim()}\n\n`;
    case "br":
      return "\n";
    case "strong":
    case "b":
      return kids().trim() ? `**${kids().trim()}**` : "";
    case "em":
    case "i":
      return kids().trim() ? `*${kids().trim()}*` : "";
    case "code":
      return el.parentElement?.tagName.toLowerCase() === "pre" ? el.textContent ?? "" : `\`${el.textContent ?? ""}\``;
    case "pre": {
      const code = (el.textContent ?? "").replace(/\n$/, "");
      const fence = "`".repeat(Math.max(3, ...(code.match(/`+/g) ?? []).map((r) => r.length + 1)));
      return `\n\n${fence}\n${code}\n${fence}\n\n`;
    }
    case "a": {
      const href = el.getAttribute("href");
      const text = kids().trim();
      return href && text ? `[${text}](${href})` : text;
    }
    case "blockquote":
      return `\n\n${kids().trim().split("\n").map((l) => `> ${l}`).join("\n")}\n\n`;
    case "ul":
    case "ol":
      return `\n\n${listItems(el, depth)}\n\n`;
    case "table":
      return `\n\n${table(el)}\n\n`;
    default:
      return kids();
  }
}

/** Rich text from the clipboard as Markdown: headings, lists, tables, code, quotes, emphasis and links. */
export function htmlToMarkdown(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return markdownOf(doc.body, 0).replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** A picture shown large; a click anywhere or Escape closes it. It sits in the app root so a message's
 *  own layout (content-visibility) cannot clip it. */
export function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="core-lightbox" role="dialog" aria-modal="true" aria-label="Picture" onClick={onClose}>
      <img src={src} alt="" />
      <button className="core-lightbox-close" aria-label="Close" onClick={onClose}>×</button>
    </div>,
    document.querySelector(".core-app") ?? document.body,
  );
}
