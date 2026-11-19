// The page side of "Meo AI for Chrome" (meo/browser-extension): the extension's bridge script on
// chat.meoarch.org says it is there, and browser tools go to it as window messages. The Rust core
// calls window.meoChrome.ready() / call(name, argsJson) (see core-rs cloud/chrome.rs).

let present = false;
let version = "";
let next = 0;
const waiting = new Map<string, (reply: unknown) => void>();

window.addEventListener("message", (event) => {
  if (event.source !== window || event.origin !== location.origin) return;
  const msg = event.data;
  if (!msg || typeof msg !== "object") return;
  if (msg.meoChrome === "ready") {
    present = true;
    version = String(msg.version ?? "");
  } else if (msg.meoChrome === "result" && typeof msg.id === "string") {
    waiting.get(msg.id)?.(msg.reply);
    waiting.delete(msg.id);
  }
});
window.postMessage({ meoChrome: "ping" }, location.origin);

declare global {
  interface Window { meoChrome?: { ready(): boolean; version(): string; call(name: string, argsJson: string): Promise<string> } }
}

window.meoChrome = {
  ready: () => present,
  version: () => version,
  call(name, argsJson) {
    const id = `c${++next}`;
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        waiting.delete(id);
        resolve(JSON.stringify({ ok: false, text: "error: the Meo AI extension did not answer within 60 s" }));
      }, 60_000);
      waiting.set(id, (reply) => { window.clearTimeout(timer); resolve(JSON.stringify(reply ?? { ok: false, text: "error: no answer" })); });
      let args: unknown = {};
      try { args = JSON.parse(argsJson || "{}"); } catch { /* bad JSON from the model: the tool says so */ }
      window.postMessage({ meoChrome: "call", id, name, args }, location.origin);
    });
  },
};
export {};
