// Shape of the wasm-bindgen output of meo/core-rs (feature `wasm`).
declare module "@meo-core/meo_ai_core.js" {
  export default function init(input?: unknown): Promise<unknown>;
  export class WebCore {
    constructor(
      clientId: string,
      redirectUri: string,
      onChanged: () => void,
      openUrl: (url: string) => void,
    );
    start(): Promise<void>;
    view(): string;
    dispatch(action: string): void;
    free(): void;
  }
}
