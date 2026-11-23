# Meo AI Repository Audit

Audit date: 2026-11-22  
Scope: source and documentation inspection of QwQdoge/meo-ai and QwQdoge/meo-api, plus the Meo Account ownership contract. This is not a production penetration test and does not prove live Worker bindings, production migrations or provider calls.

## 1. Executive summary

Meo AI already has a substantial architecture. Replacing it with a new generic gateway or a second provider/profile system would create duplication.

Highest-priority findings:

1. Usage is not yet a trustworthy cost ledger. Rust Core estimates tokens from text; provider stream usage is only partly normalized and is not automatically persisted as one complete per-request ledger.
2. Provider support was incomplete at audit time. OpenAI, Gemini, DeepSeek, OpenRouter and OpenAI-compatible were present; the direct Anthropic adapter was added on 2026-11-23 (MEO-014).
3. Custom endpoint policy needs hardening. The host allowlist is enforced only when AI_CUSTOM_ENDPOINT_HOSTS is non-empty. An empty value can permit otherwise-valid public HTTPS hosts. Review before expanding custom endpoint support.
4. File storage is incomplete. Upload is text-only and object deletion is not implemented for records with object_key.
5. The repository contains deliberate migration layers and conflicting documentation. Cleanup must be staged, not mass deletion.
6. meo/core-rs/src/cloud/app.rs is approximately 1.1 MB. This is a maintainability risk; split it by domain behind tests, not in one rewrite.

## 2. What already exists

### Meo AI

- meo/core-rs/: shared Rust Core and cloud AppCore.
- meo/ui-schema/: shared navigation, page, feature, token and settings configuration.
- meo/desktop-rs/: Rust + Qt/QML desktop client.
- meo/web/client/: React/TypeScript client.
- meo/android/: Kotlin/Compose client.
- Model roles, model selection, Projects, Skills, MCP plugin catalogue, usage import, workspace and file-related contracts already exist.
- Root README describes the native preview, model selection, usage/activity UI, Account integration and System AI Router boundary.

### Meo API

- Private Worker repository: QwQdoge/meo-api.
- Production topology is documented as Cloudflare Worker → Hyperdrive → Neon.
- Separate Account and AI databases.
- Authenticated versioned /v1 API; browser sessions and OAuth bearer tokens are supported.
- Native bearer scopes: meo:read and meo:write.
- AI credentials, model profiles, provider broker, usage dashboard, projects, files, plugins/Skills, device enrollment and AgentRuns have source implementations and documented routes.
- User-owned SQL queries generally bind the authenticated actor ID.
- Provider credential rows store encrypted key material; API metadata omits plaintext keys.

### Meo Account

Account remains the identity, session, security and encrypted provider credential authority. Meo AI should use credential IDs and broker grants, not copy keys into its own config or local project files.

## 3. Confirmed implementation gaps

### A. Usage and cost

Evidence:
- meo/core-rs/src/cloud/usage.rs: chat_event() estimates token counts from text and sets metadata.estimated=true.
- QwQdoge/meo-api/migrations/ai/0003_usage.sql: ai_usage_events stores token categories and nullable estimated_cost_microusd.
- QwQdoge/meo-api/src/ai-broker.ts: extractStreamUsage() recognizes a limited set of common usage fields and may emit usage in the stream done event.
- QwQdoge/meo-api/src/chat.ts: chat delegates to the provider broker and relays the stream; this path does not itself persist a normalized per-request usage event.
- POST /v1/usage-events and GET /v1/usage-dashboard exist, but ingestion allows estimates and does not distinguish provider-reported cost from Meo-calculated estimate.

Impact: Activity/Usage may be useful for approximate usage, but must not present every token count or cost as an actual provider bill.

Required direction: provider-specific usage adapters → normalized event → durable ingestion → versioned price snapshot → clearly labelled estimate; optional separate provider billing reconciliation.

### B. Provider coverage and connection model

Evidence:
- QwQdoge/meo-api/src/ai-providers.ts registers openai, gemini, deepseek, openrouter and openai_compatible.
- Up to 20 named credentials are supported per account. Names are unique per user (case-insensitive), so multiple connections to one provider are possible with different names.
- Model Profiles already store per-role {credentialId, model} choices and can be activated.
- Credentials are encrypted in the Account database and returned as non-secret metadata.

Impact: Do not add second providers, provider_keys or model_profiles tables in Meo AI. Direct Anthropic support landed in MEO-014; provider-specific usage capture landed in MEO-011.

### C. Custom endpoint policy

Evidence:
- src/ai-providers.ts validates HTTPS, rejects URL credentials/query/hash and common local/private address forms.
- The custom-host allowlist is applied only when AI_CUSTOM_ENDPOINT_HOSTS has entries.

Impact: An empty allowlist can mean broad public-host access. This is a security-policy ambiguity for a server-side broker that attaches user credentials.

Required direction: fail closed when allowlist is empty; document deployment allowlist entries; test IPv4/IPv6/local-host cases; review DNS rebinding and redirects. Do not claim full SSRF protection from string checks alone.

### D. Files and storage

Evidence:
- QwQdoge/meo-api/src/files.ts accepts a text field and stores extracted text. The supported MIME list includes PDF/DOCX/XLSX/PPTX, but this is not a complete binary upload pipeline.
- File metadata includes object-storage fields.
- deleteFile() returns 409 object_delete_not_configured if object_key exists.

Impact: The current API cannot truthfully claim full binary file lifecycle support. Object-backed files may be impossible to delete through this handler.

Required direction: define binary upload/download/delete lifecycle, quota accounting, orphan cleanup and retention behavior before shipping a full file manager.

### E. Meo API access and limits

Evidence:
- Browser CORS origins are limited to Account and Chat web origins.
- Native/third-party bearer clients need meo:read for reads and meo:write for mutations.
- High-risk Account actions use fresh purpose-scoped reauthentication.
- Device relay credentials are separate from user and provider credentials.
- Worker has IP-based API/AI rate limiters. Current entry code documents that ordinary API limiter failures fail open.

Impact: The identity and scope model exists, but coarse scopes alone are not a complete cost/abuse policy. IP-only limits do not stop one authenticated account from exhausting provider spend across devices.

Required direction: add actor/client-level rate and spend budgets, route-specific limits, idempotency for expensive operations and clear developer API docs. Keep privileged Account actions behind reauthentication.

## 4. Repository organization: messy or intentional?

The inspected tree contains 927 paths and includes both the active Meo architecture and a retained Newelle upstream tree. This is a deliberate migration strategy, not permission to treat every directory as current.

### Active product sources

- meo/core-rs/
- meo/ui-schema/
- meo/desktop-rs/
- meo/web/client/
- meo/android/

### Compatibility / paused sources

- Root src/, modules/, data/, po/ and legacy Meson/Flatpak files.
- meo/service/, meo/runtime/, meo/system/, meo/adapters/.
- meo/cloud/ and meo/device/ compatibility implementations.

Do not remove these folders until owner-approved migration gates and packaging dependencies are verified.

### Specific organization problems

1. meo/core-rs/src/cloud/app.rs is about 1.1 MB. Split incrementally by domain only after identifying state ownership and adding focused contract tests.
2. There are several plugin-related data sources with different jobs: root data/mcp_servers.json is upstream/legacy data; meo/core-rs/src/cloud/plugin_store.json is the built-in Meo catalogue; Meo API ai_plugins stores account-owned installed plugins. Document these boundaries; do not merge them into one mutable JSON file.
3. Usage has a Rust Core event path, a Python import tool under meo/usage/, Meo API ingestion/dashboard and provider-side billing. They need one normalized event contract, not several competing totals.
4. meo/cloud/ (compatibility) and meo/core-rs/src/cloud/ (active Core) have similar names but different ownership. Keep this distinction explicit.
5. Root src/ contains large legacy GTK/Newelle files such as src/controller.py and src/window.py. Do not move or reformat them as part of ordinary Meo feature work.

## 5. Documentation drift to reconcile

**Reconciled 2026-11-23 by MEO-001.** The items below are kept as the audit's original
finding; the current documents now agree. Re-check before relying on any of them.

The sources disagreed and needed a documentation-only task before code changes relied on them:

- Root AGENTS.md says cloud-first AppCore is authoritative and local AgentService/Python, device Work and Newelle UI are paused/not to be extended.
- meo/README.md still presents a maintained Phase B AgentService workflow and says the Newelle-derived service is kept for the Linux package.
- docs/ownership.md says the desktop application remains C++/Qt/QML, while root AGENTS.md and meo/README.md identify desktop-rs (Rust + Qt/QML/MeoUI) as the current desktop client.
- Root README and meo/README should distinguish the current cloud-first product path from retained compatibility paths.

Root AGENTS.md is the current contributor instruction; stale docs were reconciled in MEO-001 so a future agent does not extend a paused stack.

## 6. Do not do these cleanups

- Do not delete the Newelle root tree just to reduce file count.
- Do not move meo/core-rs/src/cloud/ into meo/cloud/.
- Do not create a second provider-key or model-profile database in Meo AI.
- Do not replace Meo API/Account with Supabase or a third-party gateway.
- Do not make every plugin a downloaded executable.
- Do not upload local Workspaces automatically.
- Do not label estimated usage as an actual bill.
- Do not split app.rs in one giant rewrite.

## 7. Audit outcome

The intended architecture is coherent, but several critical seams are incomplete or documented inconsistently. Prioritize usage correctness, provider coverage, custom endpoint security, file lifecycle and documentation reconciliation. Large UI redesigns and repository-wide cleanup should wait.
