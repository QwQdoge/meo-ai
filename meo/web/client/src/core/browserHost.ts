// Browser side of the Work tools: the Rust core calls window.meoHost for every file tool, and this
// file runs it on a folder the user picked with the File System Access API (Chrome, Edge, Safari 26+).
// Paths stay inside the picked folder, writes are remembered per turn (for the "files changed"
// count), and nothing leaves the browser: the folder handle never goes to the core or the network.

type Dir = FileSystemDirectoryHandle;
const MAX_READ = 200_000;
const MAX_SEARCH_FILE = 1_000_000;
const MAX_HITS = 100;
const MAX_LIST = 300;
const SKIPPED = new Set([".git", "target", "node_modules", ".cache", ".venv", "dist", "build"]);

let root: Dir | null = null;
let changed = new Set<string>();

function parts(path: string): string[] {
  if (path.startsWith("/") || /^[A-Za-z]:/.test(path)) throw new Error("path must be relative to the folder");
  const out: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") throw new Error("path leaves the folder");
    out.push(part);
  }
  return out;
}

async function dirOf(path: string[], create = false): Promise<Dir> {
  if (!root) throw new Error("no folder is open");
  let dir: Dir = root;
  for (const part of path) dir = await dir.getDirectoryHandle(part, { create });
  return dir;
}

async function fileHandle(path: string, create = false): Promise<FileSystemFileHandle> {
  const all = parts(path);
  const name = all.pop();
  if (!name) throw new Error("path is empty");
  return (await dirOf(all, create)).getFileHandle(name, { create });
}

async function readBytes(path: string): Promise<Uint8Array> {
  const file = await (await fileHandle(path)).getFile();
  return new Uint8Array(await file.arrayBuffer());
}

const isBinary = (bytes: Uint8Array) => bytes.subarray(0, 8000).includes(0);

async function* walk(dir: Dir, prefix: string): AsyncGenerator<{ path: string; handle: FileSystemFileHandle }> {
  const entries: Array<[string, FileSystemHandle]> = [];
  for await (const entry of (dir as any).entries() as AsyncIterable<[string, FileSystemHandle]>) entries.push(entry);
  entries.sort((a, b) => a[0].localeCompare(b[0]));
  for (const [name, handle] of entries) {
    if (handle.kind === "directory") {
      if (!SKIPPED.has(name)) yield* walk(handle as Dir, prefix + name + "/");
    } else yield { path: prefix + name, handle: handle as FileSystemFileHandle };
  }
}

const host = {
  supported: typeof (globalThis as any).showDirectoryPicker === "function",
  name: "",

  /** User gesture: ask for a folder. Returns its name. */
  async pick(): Promise<string> {
    const handle: Dir = await (globalThis as any).showDirectoryPicker({ mode: "readwrite" });
    root = handle;
    host.name = handle.name;
    changed = new Set();
    return handle.name;
  },

  /** Called by the core when a folder is needed. Succeeds only for the folder picked in this tab. */
  open(name: string): string {
    if (!root) throw new Error("Pick the folder first with the Open folder button.");
    if (name && name !== host.name) throw new Error(`The open folder is "${host.name}". Pick "${name}" again.`);
    return host.name;
  },

  newCheckpoint() { changed = new Set(); },
  changed(): number { return changed.size; },

  async readFile(path: string, start: number, end: number): Promise<string> {
    const bytes = await readBytes(path);
    if (isBinary(bytes)) throw new Error(`${path} is a binary file`);
    const truncated = bytes.length > MAX_READ;
    const text = new TextDecoder().decode(bytes.subarray(0, MAX_READ));
    const first = Math.max(1, start || 1);
    const last = end > 0 ? end : Infinity;
    let out = "";
    text.split("\n").forEach((line, i) => {
      const n = i + 1;
      if (n >= first && n <= last && !(i === text.split("\n").length - 1 && line === "")) out += `${String(n).padStart(5)}\t${line}\n`;
    });
    if (!out) out = "(no lines in that range)\n";
    if (truncated) out += "(file cut at 200 KB; ask for a line range)\n";
    return out;
  },

  async listDir(path: string): Promise<string> {
    const dir = await dirOf(parts(path));
    const names: string[] = [];
    for await (const [name, handle] of (dir as any).entries() as AsyncIterable<[string, FileSystemHandle]>)
      names.push(handle.kind === "directory" ? name + "/" : name);
    names.sort();
    const shown = names.slice(0, MAX_LIST);
    if (names.length > MAX_LIST) shown.push(`… ${names.length - MAX_LIST} more`);
    return shown.join("\n");
  },

  async search(pattern: string, path: string): Promise<string> {
    if (!pattern) throw new Error("the pattern is empty");
    const hits: string[] = [];
    const base = parts(path);
    const start = await dirOf(base);
    const prefix = base.length ? base.join("/") + "/" : "";
    outer: for await (const { path: file, handle } of walk(start, prefix)) {
      const f = await handle.getFile();
      if (f.size > MAX_SEARCH_FILE) continue;
      const bytes = new Uint8Array(await f.arrayBuffer());
      if (isBinary(bytes)) continue;
      const lines = new TextDecoder().decode(bytes).split("\n");
      for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].includes(pattern)) {
          hits.push(`${file}:${i + 1}: ${lines[i].trim().slice(0, 200)}`);
          if (hits.length >= MAX_HITS) { hits.push(`… stopped after ${MAX_HITS} matches`); break outer; }
        }
      }
    }
    return hits.length ? hits.join("\n") : "no matches";
  },

  async readText(path: string): Promise<string> {
    const bytes = await readBytes(path);
    if (isBinary(bytes)) throw new Error(`${path} is a binary file`);
    return new TextDecoder().decode(bytes);
  },

  async exists(path: string): Promise<boolean> {
    try { await fileHandle(path); return true; } catch { return false; }
  },

  async writeText(path: string, text: string): Promise<void> {
    const handle = await fileHandle(path, true);
    const writable = await (handle as any).createWritable();
    await writable.write(text);
    await writable.close();
    changed.add(path);
  },

  async remove(path: string): Promise<void> {
    const all = parts(path);
    const name = all.pop();
    if (!name) throw new Error("path is empty");
    await (await dirOf(all)).removeEntry(name);
    changed.add(path);
  },
};

export type BrowserHost = typeof host;
(globalThis as any).meoHost = host;
export default host;

// The core builds a file the assistant wrote and asks the platform to save it: here, a download.
(globalThis as any).meoSaveFile = (name: string, bytes: Uint8Array) => {
  const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
  const type: Record<string, string> = {
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    csv: "text/csv", json: "application/json", html: "text/html", svg: "image/svg+xml", md: "text/markdown",
  };
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: type[ext] ?? "application/octet-stream" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
};
