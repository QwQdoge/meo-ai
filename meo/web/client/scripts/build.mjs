import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (!process.env.MEO_OUTPUT_ROOT)
  throw new Error("Set MEO_OUTPUT_ROOT to the generated-output root.");
process.env.NODE_ENV = "production";
const output = path.resolve(process.env.MEO_OUTPUT_ROOT, "meo-ai/build/web");
execFileSync(process.execPath, [path.join(root, "scripts/prepare.mjs")], {
  cwd: root,
  stdio: "inherit",
});
execFileSync(
  process.execPath,
  [path.join(root, "node_modules/typescript/bin/tsc"), "--noEmit"],
  { cwd: root, stdio: "inherit" },
);
execFileSync(
  process.execPath,
  [
    path.join(root, "node_modules/vite/bin/vite.js"),
    "build",
    "--outDir",
    output,
    "--emptyOutDir",
    "false",
  ],
  { cwd: root, stdio: "inherit" },
);
