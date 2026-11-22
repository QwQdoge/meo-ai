import React, { useEffect, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";

// What a paste into the composer becomes. The page decides only what the clipboard holds; the core
// reads the files and keeps the text (see attach_document in the core).

/** How long a Ctrl+V text must be to go in as a file (the core sends its own limits with the composer). */
export type PasteLimits = { chars: number; lines: number };
const DEFAULT_LIMITS: PasteLimits = { chars: 1500, lines: 30 };

// Structure worth keeping when rich text is pasted: headings, lists, tables, code, quotes, emphasis, links.
const STRUCTURE = /<(h[1-6]|table|ul|ol|pre|blockquote|strong|b|em|a)\b/i;

export type PastePlan =
  | { kind: "files"; files: File[] }
  | { kind: "text-as-file"; markdown: string }
  | { kind: "default" };

// Apps that copy rich text (Notes, Word, a web page) often put a rendered picture of it on the
// clipboard too, named "image.png" or nothing. That picture is not a file the person copied.
const renderedPicture = (f: File) => f.type.startsWith("image/") && (!f.name || /^image\.\w+$/i.test(f.name));

// Only what the system's paste delivers decides, never a key of our own: a paste with formatting (a page,
// a document, an editor) that is long becomes a file; plain text only (the system's "paste as plain text",
// whatever shortcut the person uses, or a plain source) goes into the box as the system pasted it.
export function planPaste(data: DataTransfer, limits: PasteLimits = DEFAULT_LIMITS): PastePlan {
  const text = data.getData("text/plain");
  const html = data.getData("text/html");
  const files = Array.from(data.files);
  const hasText = text.trim() !== "";
  // Real files (a screenshot, a file from the file manager) are attached; text beats its own picture.
  if (files.length > 0 && !(hasText && files.every(renderedPicture))) return { kind: "files", files };
  if (!hasText) {
    return files.length > 0 ? { kind: "files", files } : { kind: "default" };
  }
  const markdown = html && html.trim() && STRUCTURE.test(html) ? htmlToMarkdown(html) || text : text;
  const long = markdown.length >= limits.chars || markdown.split("\n").length >= limits.lines;
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

export type LightboxProps = {
  src: string;
  images?: string[];
  initialIndex?: number;
  title?: string;
  onClose: () => void;
};

/** A picture shown large with interactive zoom, pan and multi-image arrow navigation. */
export function Lightbox({ src, images, initialIndex = 0, title, onClose }: LightboxProps) {
  const list = images && images.length > 0 ? images : [src];
  const [currentIndex, setCurrentIndex] = useState(() => {
    if (images && images.length > 0) {
      const found = images.indexOf(src);
      return found >= 0 ? found : Math.min(initialIndex, images.length - 1);
    }
    return 0;
  });

  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const moved = useRef(false);

  const currentSrc = list[currentIndex] || src;

  const goTo = useCallback((idx: number) => {
    const next = (idx + list.length) % list.length;
    setCurrentIndex(next);
    setScale(1);
    setPosition({ x: 0, y: 0 });
  }, [list.length]);

  const prev = useCallback(() => goTo(currentIndex - 1), [goTo, currentIndex]);
  const next = useCallback(() => goTo(currentIndex + 1), [goTo, currentIndex]);

  const zoomIn = useCallback(() => setScale((s) => Math.min(s + 0.35, 5)), []);
  const zoomOut = useCallback(() => setScale((s) => Math.max(s - 0.35, 0.5)), []);
  const resetZoom = useCallback(() => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && list.length > 1) prev();
      else if (e.key === "ArrowRight" && list.length > 1) next();
      else if (e.key === "+" || e.key === "=") zoomIn();
      else if (e.key === "-") zoomOut();
      else if (e.key === "0") resetZoom();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, list.length, prev, next, zoomIn, zoomOut, resetZoom]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY * -0.002;
    setScale((s) => Math.min(Math.max(s + delta, 0.5), 5));
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (scale > 1.2) {
      resetZoom();
    } else {
      setScale(2);
    }
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    dragStart.current = { x: e.clientX - position.x, y: e.clientY - position.y };
    moved.current = false;
    if (scale > 1) {
      isDragging.current = true;
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    }
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging.current) return;
    const dx = Math.abs(e.clientX - (dragStart.current.x + position.x));
    const dy = Math.abs(e.clientY - (dragStart.current.y + position.y));
    if (dx > 3 || dy > 3) {
      moved.current = true;
    }
    setPosition({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
    });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    isDragging.current = false;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
    } catch {}
  };

  return createPortal(
    <div
      className="core-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label="Picture preview"
      onClick={(e) => {
        const isBackdrop = e.target === e.currentTarget || (e.target as HTMLElement).classList.contains("core-lightbox-stage");
        if (isBackdrop && !moved.current) {
          onClose();
        }
        moved.current = false;
      }}
      onWheel={handleWheel}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div className="core-lightbox-header">
        {title && <span className="core-lightbox-title">{title}</span>}
        {list.length > 1 && (
          <span className="core-lightbox-counter">
            {currentIndex + 1} / {list.length}
          </span>
        )}
        <button className="core-lightbox-close" aria-label="Close" onClick={onClose}>×</button>
      </div>

      <div
        className="core-lightbox-stage"
        onPointerDown={handlePointerDown}
        onDoubleClick={handleDoubleClick}
      >
        <img
          src={currentSrc}
          alt=""
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
            cursor: scale > 1 ? (isDragging.current ? "grabbing" : "grab") : "zoom-in",
            transition: isDragging.current ? "none" : "transform 0.15s ease-out",
          }}
          draggable={false}
        />
      </div>

      {list.length > 1 && (
        <>
          <button
            className="core-lightbox-nav prev"
            aria-label="Previous"
            onClick={(e) => { e.stopPropagation(); prev(); }}
          >
            ‹
          </button>
          <button
            className="core-lightbox-nav next"
            aria-label="Next"
            onClick={(e) => { e.stopPropagation(); next(); }}
          >
            ›
          </button>
        </>
      )}

      <div className="core-lightbox-toolbar" onClick={(e) => e.stopPropagation()}>
        <button onClick={zoomOut} title="Zoom out (-)" aria-label="Zoom out">−</button>
        <button onClick={resetZoom} title="Reset zoom (0)">{Math.round(scale * 100)}%</button>
        <button onClick={zoomIn} title="Zoom in (+)" aria-label="Zoom in">+</button>
        <a
          href={currentSrc}
          download={`image-${currentIndex + 1}.png`}
          className="core-lightbox-download"
          title="Download picture"
        >
          ↓
        </a>
      </div>
    </div>,
    document.querySelector(".core-app") ?? document.body,
  );
}
