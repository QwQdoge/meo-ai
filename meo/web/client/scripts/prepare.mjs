import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (!process.env.MEO_OUTPUT_ROOT)
  throw new Error("Set MEO_OUTPUT_ROOT to the generated-output root.");
const uiRoot =
  process.env.MEO_UI_ROOT || path.resolve(root, "../../../../meo-ui");
const output = path.resolve(process.env.MEO_OUTPUT_ROOT, "meo-ai/build/web");
execFileSync(
  process.execPath,
  [
    path.resolve(root, "../../ui-schema/generate.mjs"),
    "--output",
    path.join(output, "schema"),
  ],
  { cwd: root, stdio: "inherit" },
);
execFileSync(
  process.execPath,
  [
    path.join(uiRoot, "tools/export-web-tokens.mjs"),
    "--bindings",
    path.resolve(root, "../../ui-schema/tokens.json"),
    "--output",
    path.join(output, "meo-tokens.css"),
  ],
  { cwd: root, stdio: "inherit" },
);
// The shared Rust core compiled for the browser (same core as desktop and Android).
execFileSync(process.execPath, [path.join(root, "scripts/build-core.mjs")], {
  cwd: root,
  stdio: "inherit",
});
