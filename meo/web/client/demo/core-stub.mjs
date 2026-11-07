// Offline stand-in for the WASM core: `WebCore` serves a canned view from meo/ui-fixtures so the
// page can be developed and screenshotted without the Rust build, the network or an account.
//   MEO_OUTPUT_ROOT=/tmp/out npx vite --config demo/vite.demo.config.ts   then open /?view=chat
const fixtures = import.meta.glob("../../../ui-fixtures/*.json", { eager: true, import: "default" });
export default async function init() {}
export class WebCore {
  constructor(_a, _b, changed) { this.changed = changed; }
  view() {
    const name = new URLSearchParams(location.search).get("view") || "chat";
    return JSON.stringify(fixtures[`../../../ui-fixtures/${name}.json`] ?? {});
  }
  dispatch(action) { console.log("action", action); }
  async start() {}
  free() {}
}
