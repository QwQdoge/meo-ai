import { defineConfig, mergeConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import base from "../vite.config";
const here = path.dirname(fileURLToPath(import.meta.url));
// `@meo-core/meo_ai_core.js` resolves to the stub; everything else is the normal config.
export default mergeConfig(base, defineConfig({
  resolve: { alias: [{ find: /^@meo-core\/meo_ai_core\.js$/, replacement: path.join(here, "core-stub.mjs") }] },
}));
