// Builds the shared Rust cloud core for the browser (wasm32) into the output root.
// Requires: rustup target wasm32-unknown-unknown and wasm-bindgen-cli 0.2.129.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (!process.env.MEO_OUTPUT_ROOT)
  throw new Error("Set MEO_OUTPUT_ROOT to the generated-output root.");
const out = path.resolve(process.env.MEO_OUTPUT_ROOT, "meo-ai/build");
const target = path.join(out, "cargo-target-wasm");
const crate = path.resolve(root, "../../core-rs");
execFileSync(
  "cargo",
  [
    "build", "--release", "--locked",
    "--target", "wasm32-unknown-unknown",
    "--no-default-features", "--features", "wasm",
  ],
  { cwd: crate, stdio: "inherit", env: { ...process.env, CARGO_TARGET_DIR: target } },
);
execFileSync(
  "wasm-bindgen",
  [
    "--target", "web",
    "--out-dir", path.join(out, "web-core"),
    path.join(target, "wasm32-unknown-unknown/release/meo_ai_core.wasm"),
  ],
  { cwd: root, stdio: "inherit" },
);
