import { useEffect, useRef, useState } from "react";
import init, { WebCore } from "@meo-core/meo_ai_core.js";

export type Action = Record<string, unknown> & { type: string };
export type View = Record<string, any>;

const CALLBACK_PATH = "/oauth/openid/callback";

/**
 * Runs the shared Rust core in the page. The page holds no product logic: it
 * renders `view` and forwards actions. Sign-in is a same-tab redirect; the
 * callback page hands its URL to the core and returns to `/`.
 */
export function useCore() {
  const [view, setView] = useState<View>({});
  const [error, setError] = useState<string | null>(null);
  const core = useRef<WebCore | null>(null);

  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        await init();
        if (disposed) return;
        const instance = new WebCore(
          "",
          `${location.origin}${CALLBACK_PATH}`,
          () => {
            if (!disposed) setView(JSON.parse(instance.view()));
          },
          (url) => location.assign(url),
          (title, text) => {
            if (typeof Notification !== "undefined" && Notification.permission === "granted")
              new Notification(title, { body: text, icon: "/meo-ai.svg" });
          },
        );
        // Only notify from the background; ask for permission on the first click.
        const report = () => instance.dispatch(JSON.stringify({ type: "set_foreground", visible: !document.hidden }));
        document.addEventListener("visibilitychange", report);
        if (typeof Notification !== "undefined" && Notification.permission === "default")
          addEventListener("click", () => void Notification.requestPermission(), { once: true });
        core.current = instance;
        setView(JSON.parse(instance.view()));
        instance.dispatch(JSON.stringify({ type: "set_locale", locale: navigator.language }));
        await instance.start();
        // Live sync with the user's other devices.
        instance.dispatch(JSON.stringify({ type: "realtime" }));
        if (location.pathname === CALLBACK_PATH) {
          const url = location.href;
          history.replaceState(null, "", "/");
          instance.dispatch(JSON.stringify({ type: "auth_callback", url }));
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();
    return () => {
      disposed = true;
      core.current?.free();
      core.current = null;
    };
  }, []);

  const act = (action: Action | null | undefined) => {
    if (action) core.current?.dispatch(JSON.stringify(action));
  };
  return { view, act, error };
}
