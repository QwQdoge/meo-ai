// Offline stand-in for the WASM core: `WebCore` serves a canned view from meo/ui-fixtures so the
// page can be developed and screenshotted without the Rust build, the network or an account.
//   MEO_OUTPUT_ROOT=/tmp/out npx vite --config demo/vite.demo.config.ts   then open /?view=chat
const fixtures = import.meta.glob("../../../ui-fixtures/*.json", { eager: true, import: "default" });
export default async function init() {}
// ?perf=300 makes the open chat that long; ?stream=60 then streams 60 tokens into its last message
// (one every 50 ms) so the cost of an update can be measured: window.__streamDone is set at the end.
const params = new URLSearchParams(location.search);
const body = "This is a paragraph of an answer with **bold** text, a list:\n\n- one\n- two\n- three\n\n```rust\nfn main() { println!(\"hi\"); }\n```\n\nand more words to make it realistic. ".repeat(6);
export class WebCore {
  tick = 0;
  constructor(_a, _b, changed) {
    this.changed = changed;
    const n = Number(params.get("stream") || 0);
    if (n > 0) {
      const timer = setInterval(() => {
        this.tick++;
        this.changed();
        if (this.tick >= n) { clearInterval(timer); window.__streamDone = true; }
      }, 50);
    }
  }
  view() {
    const name = params.get("view") || "chat";
    const view = structuredClone(fixtures[`../../../ui-fixtures/${name}.json`] ?? {});
    const perf = Number(params.get("perf") || 0);
    if (perf > 0 && view.page) {
      view.page.messages = Array.from({ length: perf }, (_, i) => i % 2 === 0
        ? { id: `m${i}`, role: "user", text: `Question number ${i} about the router plan`, actions: [], images: [], blocks: [] }
        : { id: `m${i}`, role: "assistant", text: body, streaming: false, actions: [], images: [], blocks: [{ type: "markdown", text: body }] });
      if (this.tick > 0) {
        const last = view.page.messages[perf - 1];
        last.text = body + " token".repeat(this.tick);
        last.blocks = [{ type: "markdown", text: last.text }];
        last.streaming = true;
      }
    }
    return JSON.stringify(view);
  }
  dispatch(action) { console.log("action", action); }
  async start() {}
  free() {}
}
