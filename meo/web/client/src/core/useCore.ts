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
        );
        core.current = instance;
        setView(JSON.parse(instance.view()));
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
