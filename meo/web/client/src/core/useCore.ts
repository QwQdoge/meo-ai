import { useEffect, useRef, useState } from "react";
import init, { WebCore } from "@meo-core/meo_ai_core.js";

export type Action = Record<string, unknown> & { type: string };
export type View = Record<string, any>;

const CALLBACK_PATH = "/oauth/openid/callback";
/** The address the tab was opened at, kept across the sign-in redirect. */
const WANTED = "meo.wanted_path";

/**
 * Runs the shared Rust core in the page. The page holds no product logic: it
 * renders `view` and forwards actions. Sign-in is a same-tab redirect; the
 * callback page hands its URL to the core and returns to `/`.
 */
export function useCore() {
  const [view, setView] = useState<View>({});
  const [error, setError] = useState<string | null>(null);
  const core = useRef<WebCore | null>(null);
  // The address bar follows the page the core shows (`view.path`) and opening an address opens that page.
  // It is not written until the address the tab was opened at has been applied.
  const synced = useRef(false);

  useEffect(() => {
    let disposed = false;
    let clock = 0;
    // Listeners added on the page itself are removed again when the core is dropped.
    const cleanups: Array<() => void> = [];
    const listen = (target: EventTarget, type: string, fn: EventListener, opts?: AddEventListenerOptions) => {
      target.addEventListener(type, fn, opts);
      cleanups.push(() => target.removeEventListener(type, fn, opts));
    };
    // The core reports a change for every streamed chunk. Reading the whole view and re-rendering
    // for each one froze long chats, so at most one refresh is done per animation frame (about
    // every 100 ms in a background tab, where frames do not run).
    let queued = false;
    const refresh = () => {
      queued = false;
      if (!disposed && core.current) setView(JSON.parse(core.current.view()));
    };
    const schedule = () => {
      if (queued || disposed) return;
      queued = true;
      if (document.hidden) window.setTimeout(refresh, 100);
      else requestAnimationFrame(refresh);
    };
    (async () => {
      try {
        await init();
        if (disposed) return;
        const wanted = location.pathname !== CALLBACK_PATH && location.pathname !== "/" ? location.pathname : null;
        if (wanted) sessionStorage.setItem(WANTED, wanted);
        const instance = new WebCore(
          "",
          `${location.origin}${CALLBACK_PATH}`,
          () => schedule(),
          (url) => location.assign(url),
          (title, text) => {
            if (typeof Notification !== "undefined" && Notification.permission === "granted")
              new Notification(title, { body: text, icon: "/meo-ai.svg" });
          },
        );
        // Only notify from the background; ask for permission on the first click.
        const report = () => instance.dispatch(JSON.stringify({ type: "set_foreground", visible: !document.hidden }));
        listen(document, "visibilitychange", report);
        if (typeof Notification !== "undefined" && Notification.permission === "default")
          listen(window, "click", () => void Notification.requestPermission(), { once: true });
        core.current = instance;
        setView(JSON.parse(instance.view()));
        instance.dispatch(JSON.stringify({ type: "set_locale", locale: navigator.language }));
        // Start reads the saved session at once and then syncs with the network (seconds). The address the
        // tab was opened at (/settings, a chat) is applied as soon as the saved session says "signed in",
        // without waiting for that sync.
        const starting = instance.start();
        const open = (path: string) => instance.dispatch(JSON.stringify({ type: "open_path", path }));
        const first = sessionStorage.getItem(WANTED);
        if (!first) synced.current = true;
        const applyWanted = async () => {
          if (!first) return;
          for (let i = 0; i < 300 && !disposed; i++) {
            const state = JSON.parse(instance.view()).auth?.state;
            if (state === "signed_in") {
              sessionStorage.removeItem(WANTED);
              open(first);
              synced.current = true;
              return;
            }
            // Signed out after start finished: the address waits for the sign-in redirect.
            if (state === "signed_out" && i > 40) return;
            await new Promise((done) => window.setTimeout(done, i < 40 ? 25 : 200));
          }
        };
        const applying = applyWanted();
        await starting;
        // Live sync with the user's other devices.
        instance.dispatch(JSON.stringify({ type: "realtime" }));
        // The core has no clock of its own: it delivers scheduled tasks and reports finished jobs on this tick.
        const tick = () => instance.dispatch(JSON.stringify({ type: "tick", utc_offset_min: -new Date().getTimezoneOffset() }));
        tick();
        clock = window.setInterval(tick, 15000);
        if (location.pathname === CALLBACK_PATH) {
          const url = location.href;
          history.replaceState(null, "", "/");
          instance.dispatch(JSON.stringify({ type: "auth_callback", url }));
        }
        // Back and forward buttons.
        listen(window, "popstate", () => { if (!disposed && core.current === instance) open(location.pathname); });
        // After a sign-in redirect the session arrives only now: the address is applied then.
        await applying;
        if (!synced.current && first && sessionStorage.getItem(WANTED)) {
          for (let i = 0; i < 75 && !disposed; i++) {
            if (JSON.parse(instance.view()).auth?.state === "signed_in") {
              sessionStorage.removeItem(WANTED);
              open(first);
              synced.current = true;
              break;
            }
            await new Promise((done) => window.setTimeout(done, 200));
          }
        }
        setView(JSON.parse(instance.view()));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();
    return () => {
      disposed = true;
      window.clearInterval(clock);
      cleanups.forEach((undo) => undo());
      core.current?.free();
      core.current = null;
    };
  }, []);

  // Follow the page in the address bar: a new entry for every page the user moves to.
  useEffect(() => {
    if (!synced.current || view.auth?.state !== "signed_in" || typeof view.path !== "string") return;
    if (location.pathname === view.path) return;
    // The bare address becomes the page it shows without an extra entry to go back through.
    if (location.pathname === "/") history.replaceState(null, "", view.path);
    else history.pushState(null, "", view.path);
  }, [view]);

  const act = (action: Action | null | undefined) => {
    if (action) core.current?.dispatch(JSON.stringify(action));
  };
  return { view, act, error };
}
