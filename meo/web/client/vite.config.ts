import { defineConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
if (!process.env.MEO_OUTPUT_ROOT)
  throw new Error("Set MEO_OUTPUT_ROOT before starting Vite.");
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
});
