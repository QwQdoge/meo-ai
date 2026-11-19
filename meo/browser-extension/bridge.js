// Runs only on chat.meoarch.org. Passes the page's browser-tool requests to the extension and the
// answers back. The page never gets the extension's APIs, only these messages.
(() => {
  const announce = () => window.postMessage({ meoChrome: "ready", version: chrome.runtime.getManifest().version }, location.origin);
  window.addEventListener("message", async (event) => {
    if (event.source !== window || event.origin !== location.origin) return;
    const msg = event.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.meoChrome === "ping") return announce();
    if (msg.meoChrome !== "call" || typeof msg.id !== "string" || typeof msg.name !== "string") return;
    let reply;
    try {
      reply = await chrome.runtime.sendMessage({ name: msg.name, args: msg.args ?? {} });
    } catch (e) {
      reply = { ok: false, text: "error: the Meo AI extension did not answer (" + (e?.message ?? e) + ")" };
    }
    window.postMessage({ meoChrome: "result", id: msg.id, reply }, location.origin);
  });
  announce();
})();
