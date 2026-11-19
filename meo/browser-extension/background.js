// Meo AI for Chrome: the browser tools Meo AI's web app asks for, run in this Chrome.
// Nothing runs until the user turns control on in the popup. Meo works in one tab it opened (or the
// tab the user chose with "use this tab"); chrome:// and the Web Store are never touched.

const BLOCKED = /^(chrome|edge|about|chrome-extension|devtools):|^https:\/\/chromewebstore\.google\.com/;
let meoTab = null;

async function enabled() {
  const { enabled } = await chrome.storage.local.get("enabled");
  return enabled === true;
}

async function workTab(create = true) {
  if (meoTab !== null) {
    try { return await chrome.tabs.get(meoTab); } catch { meoTab = null; }
  }
  if (!create) return null;
  const tab = await chrome.tabs.create({ url: "about:blank", active: true });
  meoTab = tab.id;
  return tab;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function settled(tabId) {
  for (let i = 0; i < 60; i++) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return tab;
    await wait(250);
  }
  return chrome.tabs.get(tabId);
}

async function inTab(tabId, func, args = []) {
  const tab = await chrome.tabs.get(tabId);
  if (BLOCKED.test(tab.url ?? "")) throw new Error("this page cannot be controlled (browser or extension page)");
  const [result] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return result?.result;
}

// ---- page-side functions (serialized into the page) ----

function pageSnapshot() {
  const roles = "a,button,input,select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=tab],[role=menuitem],[contenteditable=true]";
  let n = 0;
  const lines = [];
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const label = (el) => (el.getAttribute("aria-label") || (el.labels && el.labels[0] && el.labels[0].innerText) || el.innerText || el.placeholder || el.title || el.alt || el.name || el.value || "").replace(/\s+/g, " ").trim().slice(0, 80);
  document.querySelectorAll("[data-meo-ref]").forEach((el) => el.removeAttribute("data-meo-ref"));
  const walk = (node, depth) => {
    for (const el of node.children) {
      if (!visible(el)) continue;
      const tag = el.tagName.toLowerCase();
      if (/^h[1-6]$/.test(tag)) lines.push(`${"  ".repeat(depth)}heading "${label(el)}"`);
      if (el.matches(roles)) {
        const ref = `e${++n}`;
        el.setAttribute("data-meo-ref", ref);
        const kind = el.getAttribute("role") || (tag === "input" ? `input ${el.type || "text"}` : tag);
        const extra = tag === "a" && el.href ? ` -> ${el.href}` : tag === "input" && el.value && el.type !== "password" ? ` value="${el.value.slice(0, 60)}"` : "";
        lines.push(`${"  ".repeat(depth)}${kind} "${label(el)}" [ref=${ref}]${extra}`);
        if (n >= 400) return;
      } else if (["p", "li", "td", "label", "span"].includes(tag) && el.children.length === 0) {
        const t = el.innerText.replace(/\s+/g, " ").trim();
        if (t.length > 2) lines.push(`${"  ".repeat(depth)}text "${t.slice(0, 160)}"`);
      }
      walk(el, tag === "main" || tag === "section" || tag === "form" ? depth + 1 : depth);
      if (n >= 400) return;
    }
  };
  walk(document.body, 0);
  const text = lines.join("\n");
  return `Page: ${document.title}\nURL: ${location.href}\n\n${text.length > 40000 ? text.slice(0, 40000) + "\n… (cut)" : text}`;
}

function pageClick(ref) {
  const el = document.querySelector(`[data-meo-ref="${ref}"]`);
  if (!el) return `error: no element ${ref}; take a new browser_snapshot`;
  el.scrollIntoView({ block: "center" });
  el.click();
  return `clicked ${ref}`;
}

function pageType(ref, text, submit) {
  const el = document.querySelector(`[data-meo-ref="${ref}"]`);
  if (!el) return `error: no element ${ref}; take a new browser_snapshot`;
  if (el.type === "password") return "error: Meo does not type into password fields; ask the user to do it";
  el.scrollIntoView({ block: "center" });
  el.focus();
  if (el.isContentEditable) {
    el.textContent = text;
  } else {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, text);
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  if (submit) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    if (el.form) (el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit());
  }
  return `typed into ${ref}${submit ? " and submitted" : ""}`;
}

function pageKey(key) {
  const target = document.activeElement || document.body;
  for (const type of ["keydown", "keyup"]) target.dispatchEvent(new KeyboardEvent(type, { key, bubbles: true }));
  if (key === "Enter" && target.form) target.form.requestSubmit?.();
  return `pressed ${key}`;
}

function pageScroll(direction) {
  window.scrollBy({ top: direction === "up" ? -window.innerHeight * 0.8 : window.innerHeight * 0.8 });
  return `scrolled ${direction}`;
}

// ---- tools ----

const tools = {
  async browser_navigate({ url }) {
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return { ok: false, text: "error: give a full http(s) address" };
    const tab = await workTab();
    await chrome.tabs.update(tab.id, { url, active: true });
    await settled(tab.id);
    return { ok: true, text: await inTab(tab.id, pageSnapshot) };
  },
  async browser_navigate_back() {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet; use browser_navigate" };
    await chrome.tabs.goBack(tab.id);
    await settled(tab.id);
    return { ok: true, text: await inTab(tab.id, pageSnapshot) };
  },
  async browser_snapshot() {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet; use browser_navigate" };
    return { ok: true, text: await inTab(tab.id, pageSnapshot) };
  },
  async browser_click({ ref }) {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet" };
    const done = await inTab(tab.id, pageClick, [String(ref)]);
    await wait(600);
    await settled(tab.id);
    return { ok: !String(done).startsWith("error"), text: `${done}\n\n${await inTab(tab.id, pageSnapshot)}` };
  },
  async browser_type({ ref, text, submit }) {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet" };
    const done = await inTab(tab.id, pageType, [String(ref), String(text ?? ""), submit === true]);
    if (submit) { await wait(800); await settled(tab.id); }
    return { ok: !String(done).startsWith("error"), text: `${done}\n\n${await inTab(tab.id, pageSnapshot)}` };
  },
  async browser_press_key({ key }) {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet" };
    const done = await inTab(tab.id, pageKey, [String(key)]);
    await wait(500);
    return { ok: true, text: `${done}\n\n${await inTab(tab.id, pageSnapshot)}` };
  },
  async browser_scroll({ direction }) {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet" };
    return { ok: true, text: await inTab(tab.id, pageScroll, [direction === "up" ? "up" : "down"]) };
  },
  async browser_take_screenshot() {
    const tab = await workTab(false);
    if (!tab) return { ok: false, text: "error: no page is open yet" };
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    await wait(200);
    const url = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 70 });
    return { ok: true, text: "Screenshot of the page (attached).", images: [{ mime: "image/jpeg", data: url.split(",")[1] }] };
  },
  async browser_tabs({ action, index, url }) {
    const tabs = await chrome.tabs.query({ currentWindow: true });
    if (action === "select" && Number.isInteger(index) && tabs[index]) {
      meoTab = tabs[index].id;
      await chrome.tabs.update(meoTab, { active: true });
      return { ok: true, text: `Working in tab ${index}: ${tabs[index].title}` };
    }
    if (action === "new") {
      meoTab = null;
      const tab = await workTab();
      if (typeof url === "string" && /^https?:\/\//.test(url)) await chrome.tabs.update(tab.id, { url });
      return { ok: true, text: "Opened a new tab for Meo." };
    }
    return { ok: true, text: tabs.map((t, i) => `${i}: ${t.title} — ${t.url}${t.id === meoTab ? " (Meo works here)" : ""}`).join("\n") };
  },
};

chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  // Only the bridge on chat.meoarch.org sends tool calls.
  if (!sender.url || !sender.url.startsWith("https://chat.meoarch.org/")) return false;
  (async () => {
    if (msg?.name === "status") return respond({ ok: true, enabled: await enabled() });
    if (!(await enabled())) {
      return respond({ ok: false, text: "error: control is off. Ask the user to click the Meo AI extension icon in Chrome and turn on \"Allow Meo AI to control this browser\"." });
    }
    const tool = tools[msg?.name];
    if (!tool) return respond({ ok: false, text: `error: unknown browser tool ${msg?.name}` });
    try {
      respond(await tool(msg.args ?? {}));
    } catch (e) {
      respond({ ok: false, text: `error: ${e?.message ?? e}` });
    }
  })();
  return true;
});
