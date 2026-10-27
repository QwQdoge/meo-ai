// Reading and writing documents in the browser. Nothing is uploaded: PDFs, Word, Excel and
// PowerPoint files are turned into plain text here and attached like any text file; files the model
// writes are built here and saved with the browser's own download.

import { unzipSync, zipSync, strFromU8, strToU8 } from "fflate";

const MAX_TEXT = 400_000;

const clip = (text: string) => (text.length > MAX_TEXT ? text.slice(0, MAX_TEXT) + "\n(text cut)" : text);
const decodeXml = (s: string) =>
  s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");
const encodeXml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** File extensions this module can read, besides plain text and pictures. */
export const documentExtensions = ["pdf", "docx", "xlsx", "pptx", "odt", "rtf"];

async function pdfText(bytes: Uint8Array): Promise<string> {
  const { extractText, getDocumentProxy } = await import("unpdf");
  const pdf = await getDocumentProxy(bytes);
  const { text } = await extractText(pdf, { mergePages: false });
  return (text as string[]).map((page, i) => `--- page ${i + 1} ---\n${page}`).join("\n\n");
}

function docxText(files: Record<string, Uint8Array>): string {
  const xml = strFromU8(files["word/document.xml"] ?? new Uint8Array());
  return decodeXml(
    xml
      .replace(/<w:tab\/>/g, "\t")
      .replace(/<w:br[^>]*\/>/g, "\n")
      .replace(/<\/w:p>/g, "\n")
      .replace(/<[^>]+>/g, ""),
  ).replace(/\n{3,}/g, "\n\n");
}

function pptxText(files: Record<string, Uint8Array>): string {
  const slides = Object.keys(files)
    .filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name))
    .sort((a, b) => Number(a.match(/\d+/)![0]) - Number(b.match(/\d+/)![0]));
  return slides
    .map((name, i) => {
      const xml = strFromU8(files[name]);
      const text = decodeXml(xml.replace(/<\/a:p>/g, "\n").replace(/<[^>]+>/g, ""));
      return `--- slide ${i + 1} ---\n${text.trim()}`;
    })
    .join("\n\n");
}

function xlsxText(files: Record<string, Uint8Array>): string {
  const shared: string[] = [];
  const sst = files["xl/sharedStrings.xml"];
  if (sst) {
    for (const m of strFromU8(sst).matchAll(/<si>([\s\S]*?)<\/si>/g)) {
      shared.push(decodeXml([...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((t) => t[1]).join("")));
    }
  }
  const names: string[] = [];
  const workbook = files["xl/workbook.xml"];
  if (workbook) for (const m of strFromU8(workbook).matchAll(/<sheet [^>]*name="([^"]*)"/g)) names.push(decodeXml(m[1]));
  const sheets = Object.keys(files)
    .filter((n) => /^xl\/worksheets\/sheet\d+\.xml$/.test(n))
    .sort((a, b) => Number(a.match(/\d+/)![0]) - Number(b.match(/\d+/)![0]));
  return sheets
    .map((name, i) => {
      const xml = strFromU8(files[name]);
      const rows: string[] = [];
      for (const row of xml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)) {
        const cells: string[] = [];
        for (const c of row[1].matchAll(/<c ([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
          const attrs = c[1];
          const body = c[2] ?? "";
          const type = attrs.match(/t="([^"]*)"/)?.[1];
          const value = body.match(/<v>([\s\S]*?)<\/v>/)?.[1] ?? body.match(/<t[^>]*>([\s\S]*?)<\/t>/)?.[1] ?? "";
          cells.push(type === "s" ? shared[Number(value)] ?? "" : decodeXml(value));
        }
        rows.push(cells.map((v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)).join(","));
      }
      return `--- sheet ${names[i] ?? i + 1} (CSV) ---\n${rows.join("\n")}`;
    })
    .join("\n\n");
}

/** Plain text of a document, or null when the type is not one this module reads. */
export async function readDocument(file: File): Promise<string | null> {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (ext === "pdf" || file.type === "application/pdf") return clip(await pdfText(bytes));
  if (["docx", "xlsx", "pptx"].includes(ext)) {
    const files = unzipSync(bytes);
    return clip(ext === "docx" ? docxText(files) : ext === "pptx" ? pptxText(files) : xlsxText(files));
  }
  if (ext === "rtf") {
    return clip(
      new TextDecoder()
        .decode(bytes)
        .replace(/\\par[d]?/g, "\n")
        .replace(/\\'[0-9a-f]{2}/gi, "")
        .replace(/\\[a-z]+-?\d* ?/gi, "")
        .replace(/[{}]/g, ""),
    );
  }
  return null;
}

// ---- writing --------------------------------------------------------------------------------------

const MIME: Record<string, string> = {
  txt: "text/plain", md: "text/markdown", csv: "text/csv", json: "application/json", html: "text/html",
  svg: "image/svg+xml", xml: "application/xml", yaml: "text/yaml", yml: "text/yaml", css: "text/css", js: "text/javascript",
  ts: "text/plain", py: "text/x-python", sh: "text/x-shellscript", sql: "text/plain", ics: "text/calendar",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
};

function paragraphs(markdown: string): string {
  const out: string[] = [];
  for (const raw of markdown.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const clean = (t: string) => encodeXml(t.replace(/\*\*(.*?)\*\*/g, "$1").replace(/`([^`]*)`/g, "$1"));
    if (heading) {
      const size = [40, 32, 28][heading[1].length - 1];
      out.push(`<w:p><w:r><w:rPr><w:b/><w:sz w:val="${size}"/></w:rPr><w:t xml:space="preserve">${clean(heading[2])}</w:t></w:r></w:p>`);
    } else if (bullet) {
      out.push(`<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:t xml:space="preserve">• ${clean(bullet[1])}</w:t></w:r></w:p>`);
    } else {
      out.push(`<w:p><w:r><w:t xml:space="preserve">${clean(line)}</w:t></w:r></w:p>`);
    }
  }
  return out.join("");
}

function docxBytes(markdown: string): Uint8Array {
  const parts: Record<string, Uint8Array> = {
    "[Content_Types].xml": strToU8(
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`,
    ),
    "_rels/.rels": strToU8(
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`,
    ),
    "word/document.xml": strToU8(
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paragraphs(markdown)}</w:body></w:document>`,
    ),
  };
  return zipSync(parts);
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i += 1; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const colName = (n: number) => { let s = ""; for (let x = n + 1; x > 0; x = Math.floor((x - 1) / 26)) s = String.fromCharCode(65 + ((x - 1) % 26)) + s; return s; };

function xlsxBytes(csv: string): Uint8Array {
  const rows = parseCsv(csv).map((row, r) =>
    `<row r="${r + 1}">${row.map((v, c) => {
      const ref = `${colName(c)}${r + 1}`;
      return v !== "" && !isNaN(Number(v)) && !/^0\d/.test(v) ? `<c r="${ref}"><v>${Number(v)}</v></c>` : `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${encodeXml(v)}</t></is></c>`;
    }).join("")}</row>`).join("");
  const parts: Record<string, Uint8Array> = {
    "[Content_Types].xml": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`),
    "_rels/.rels": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`),
    "xl/workbook.xml": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>`),
    "xl/_rels/workbook.xml.rels": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`),
    "xl/worksheets/sheet1.xml": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows}</sheetData></worksheet>`),
  };
  return zipSync(parts);
}

/** Saves a file the model wrote. `docx` is built from Markdown and `xlsx` from CSV; other names are saved as text. */
export function downloadGenerated(name: string, content: string): void {
  const safe = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").slice(0, 120) || "file.txt";
  const ext = safe.includes(".") ? safe.split(".").pop()!.toLowerCase() : "txt";
  const bytes: Uint8Array = ext === "docx" ? docxBytes(content) : ext === "xlsx" ? xlsxBytes(content) : strToU8(content);
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: MIME[ext] ?? "application/octet-stream" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = safe;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** A code block whose language line is `file:<name>` is a file the model wants to give the user. */
export function fileNameOf(language: string): string | null {
  const m = language.match(/^file:(.{1,120})$/);
  return m ? m[1].trim() : null;
}
