import { defineConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
if (!process.env.MEO_OUTPUT_ROOT)
  throw new Error("Set MEO_OUTPUT_ROOT before starting Vite.");

// Packages that form the React runtime — stable, large, cache independently.
const REACT_PKGS = new Set([
  "react", "react-dom", "react-router-dom", "react-router", "scheduler",
]);
// i18n runtime — loaded at startup, changes rarely.
const I18N_PKGS = new Set(["i18next", "react-i18next"]);
// Synchronous markdown pipeline — used on every chat render.
// micromark-* sub-packages are matched by prefix below.
const MARKDOWN_PKGS = new Set([
  "react-markdown", "remark-gfm", "remark-parse", "remark-rehype",
  "unified", "vfile", "mdast-util-from-markdown", "mdast-util-to-hast",
  "mdast-util-gfm", "hast-util-to-jsx-runtime", "hast-util-whitespace",
  "property-information", "space-separated-tokens", "comma-separated-tokens",
  "decode-named-character-reference", "zwitch", "devlop",
]);
// katex + remark-math + rehype-katex stay in the auto-generated dynamic chunk
// (they are only reachable via import("./mathPlugins") in rich.tsx).
// mermaid stays in its own auto-generated dynamic chunk (RichVisuals.tsx).

function manualChunks(id: string): string | undefined {
  if (!id.includes("/node_modules/")) return undefined;
  const pkg = id.split("/node_modules/").at(-1)?.split("/")[0] ?? "";
  if (REACT_PKGS.has(pkg)) return "vendor-react";
  if (I18N_PKGS.has(pkg) || pkg.startsWith("i18next-")) return "vendor-i18n";
  if (pkg === "lucide-react") return "vendor-icons";
  if (MARKDOWN_PKGS.has(pkg) || pkg.startsWith("micromark")) return "vendor-markdown";
  return undefined;
}

export default defineConfig({
  resolve: {
    alias: {
      "@meo-core": path.resolve(
        process.env.MEO_OUTPUT_ROOT,
        "meo-ai/build/web-core",
      ),
      "@meo-tokens": path.resolve(
        process.env.MEO_OUTPUT_ROOT,
        "meo-ai/build/web/meo-tokens.css",
      ),
    },
  },
  server: {
    host: "127.0.0.1",
    fs: { allow: [path.resolve(root, "../../.."), process.env.MEO_OUTPUT_ROOT] },
  },
  build: {
    rollupOptions: {
      output: { manualChunks },
    },
  },
});
