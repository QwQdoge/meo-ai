# Meo AI Web client

The Meo-owned React/TypeScript client now lives beside desktop, Android and Rust
Core in `meo-ai`. This imports the existing Meo product modules and browser OAuth
edge from `meo-ai-web`, with provenance in `import-manifest.json` and the retained
MIT notice in `LICENSE.librechat`. It does not import LibreChat's Express/Mongo
backend or the legacy static UI. The old repository remains intact for history
and deployment rollback; no production deployment is changed by this import.

Install with `npm ci` after dependency lock generation. Run `npm run typecheck`
and `npm test`. Build with `MEO_OUTPUT_ROOT=<output-root> npm run build`.
The build validates the shared UI Schema and stages generated output outside
source. Pages uses `functions/` for OAuth/HttpOnly sessions and minimal API
forwarding; static output comes from this React application. A production
cutover requires the registered callback, session secret and explicit deployment.

The approved eight-group settings structure is now integrated, including browser
preferences and existing Account connections. Navigation reads the shared schema,
and compact layouts use a left drawer. Shared personal instructions and memory
require an authenticated account-scoped API; missing routes remain visibly
unavailable. The local Core is not a browser fallback. See
`../../docs/settings-contract.md` for the exact client/backend adoption boundary.
New visual candidates are prepared under outputs before source promotion. Server errors,
unsupported capabilities and unfinished surfaces must remain truthful.
