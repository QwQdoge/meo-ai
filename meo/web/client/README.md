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


## Chat / Work and Agent connectivity

Chat and Work are first-class top-header modes. Work lists **account-owned
Project/device bindings**, not arbitrary paths discovered from the browser.
This requires Meo API `GET /v1/ai/workspaces` (Meo API PR #6). Devices shown
by this endpoint are registered, but **last-seen is not proof of being online**.
If no Project is bound to a trusted device workspace, Work explains why its
list is empty.

An optional server-only Pages environment variable enables task dispatch:

```text
MEO_AGENT_CLOUD_URL=https://<your-deployed-agent-cloud-origin>
```

Use the HTTPS origin of the separately deployed `meo/cloud` Agent relay
(no path, query or credentials). **Do not set this to `api.meoarch.org`**:
the Meo API AgentRun metadata endpoint does not dispatch device execution.
If the variable is missing or invalid, the authenticated Work status route
reports execution unavailable and the run button stays disabled.
Configuring the URL alone does not prove device online status or a working
deployment; test authorized account tokens, Relay/WebSocket connectivity and
end-to-end local Agent execution separately.

User-initiated Chat-to-Work actions copy a user draft/message to Work. The
user selects an account-owned workspace and confirms the task; the BFF
forwards `conversation_id`, `project_id`, text and `permission_mode=ask`
to the Agent service. The service chooses the actual eligible device and
resolves its opaque workspace reference; Web cannot select arbitrary local
paths or invoke shell operations. A remote AgentRun can be resumed using its
event cursor; disconnecting a viewer does not cancel work. Backend-issued
tool decisions are forwarded only with their exact ID and option index.

**Not yet supported:** autonomous model-initiated tool calls from Chat,
because Meo API's chat provider contract does not currently expose a trusted
Agent tool router. The explicit handoff is not represented as that feature.
Production Pages deploy, Agent cloud deploy, device pairing, account consent
and a live browser/device acceptance test are also separate steps.
