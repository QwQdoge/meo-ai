# Meo AI Product Architecture Plan

Status: planning baseline, 2026-11-22. This is a design target, not a claim that every item is implemented.

Latest repository findings: [Repository audit — 2026-11-22](repository-audit-2026-11-22.md). The audit records verified implementation gaps; use it together with the ordered [implementation backlog](implementation-backlog.md).

This plan follows the current owner decisions in root AGENTS.md: one cloud-first product core, one shared view contract, thin native renderers, Meo Account as identity/credential authority, and Meo API as the authenticated product API. If a newer explicit owner decision conflicts with this plan, update the plan before implementation.

## 1. Product rules

1. One Meo AI across Chat, Work, Projects and Skills on Desktop, Web and Android.
2. Rust Core owns shared product behavior, state transitions, provider selection, tool decisions, request lifecycle and the view contract. Clients render and return typed actions; they do not create a second agent engine.
3. Pluginize optional capabilities. Do not pluginize the small set of services required for security, integrity and basic operation.
4. A plugin can offer a capability. It cannot grant itself permission, approve its own actions, read another user's data, bypass Account consent or execute privileged system operations.
5. Meo Account owns identity, sessions, encrypted provider credentials and account-level consent. Meo API owns Meo AI product data and authorization. Device-local workspace bytes remain on the device unless the user explicitly uploads or materializes something.
6. Prefer one source of truth per concept. Do not create a second provider-key store, profile system, usage ledger, file database or UI schema.
7. Every feature needs truthful unavailable, disconnected, permission-denied and error states. A catalogue entry is not proof that a feature works.

## 2. Core versus plugins

### Core services that must not be optional plugins

| Core service | Why it stays in Core |
| --- | --- |
| App bootstrap, version negotiation and feature discovery | The app must start before optional features load. |
| Authentication/session client and account identity | Every protected operation needs one trusted identity. |
| Meo API transport, request IDs, streaming, cancellation and reconnect | These define shared behavior and prevent duplicated side effects. |
| Permission and consent enforcement | Plugins and model output are untrusted; neither may grant authority. |
| Plugin registry, manifest validation, lifecycle and isolation boundary | A plugin system needs a trusted host. |
| Secure credential broker boundary | Keys must not reach clients, prompts, plugins or logs. |
| Workspace/file containment and path authorization | A plugin cannot decide which local files it may access. |
| Data ownership, migrations, audit events and usage normalization | These require consistent actor scope and durable records. |
| System capability boundary | Privileged actions remain with System AI Router and the owning system service. |
| UI Schema and ContentBlock protocol compatibility | Every client must interpret the same page and response contracts. |
| Update/signature verification and crash-safe recovery | Optional plugins must not replace the trusted update path. |

### Capabilities that should be plugins or registered extensions

| Capability family | Plugin form | Notes |
| --- | --- | --- |
| Model providers | Provider adapter | OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, approved compatible services and future providers. |
| Model catalogue and metadata | Provider catalogue adapter | Capabilities, context size, modalities, pricing hints and availability. |
| Search and research | Tool provider | Web search, website reading, academic search and specialist search. |
| Connected services | Hosted connector / MCP | GitHub, Google Drive, Cloudflare, Neon, Supabase, Figma, Canva and others. |
| Skills | Text-only Skill initially | Instructions and reference material; not executable authority. |
| Bundles | Collection manifest | Installs several Skills and connectors together. |
| Document import/export | File-format plugin | PDF, DOCX, XLSX, PPTX, Markdown, CSV and other formats. |
| Image, audio and video | Modality provider | Generation, editing, transcription, speech and video; each declares its billing unit. |
| Local inference | Device provider adapter | Ollama, llama.cpp and other local runtimes stay on-device. |
| Memory backends and retrieval | Storage/retrieval adapter | Core owns memory policy and user controls; a plugin may provide a backend. |
| Browser and external data sources | Connector/tool | Access is explicit, scoped and auditable. |
| Importers | Data-source plugin | Codex, Claude Code and other usage/history importers remain opt-in. |
| Optional interface contributions | Registered page/section contribution | Known renderer IDs and typed data only. No remote arbitrary HTML, QML, JavaScript or executable UI. |

### Plugin manifest v1

A future manifest should be versioned and declarative. Minimum fields:

- identity: id, version, name, description, publisher, kind, entrypoint
- compatibility: manifest version and supported Meo Core/API version range
- capabilities: stable IDs, input/output schema versions and supported surfaces
- permissions: requested data categories and effects; the manifest never grants them
- network: exact HTTPS origins required by a hosted plugin
- settings schema: typed, bounded settings only
- UI contributions: known page/section/toolbar slots and registered renderer IDs only
- dependencies, integrity, signature and update channel
- lifecycle: discovered, installed, connected, enabled, unavailable, failed or disabled

The host validates compatibility, publisher/integrity and permissions. Users can inspect what a plugin can read, change, send or execute. Disabling stops new calls and revokes active grants. Removing must not silently delete user data.

### Plugin security levels

1. Bundled trusted adapters: shipped with Meo, but still use the same capability and permission contracts.
2. Hosted remote connectors: HTTPS/MCP requests are brokered by Meo API; third-party tokens are not sent to clients.
3. Skills: text-only guidance. Skill text is untrusted context, never policy or executable code.
4. Third-party executable extensions: not in v1. Do not add downloaded code until signing, sandboxing, permission review, updates and rollback exist.

## 3. Profiles: keep different meanings separate

The word Profile currently refers to different concepts. Keep them separate in UI, data and code.

### Account profile
Identity and account presentation: display name, avatar, verified email, linked sign-in methods, subscription and security state. Owner: Meo Account. Meo AI reads safe metadata only. Never place provider keys, session tokens or security secrets here.

### Personalization profile
Assistant behavior: custom instructions, response language, memory use, response detail and user preferences. Owner: existing Meo API/Core settings contract. Memory content and memory-recall enablement are separate from conversation history. Preferences cannot change security policy or tool permissions.

### Model Profile
A named set of model choices for the roles already defined by meo-api/src/model-roles.mjs.

- Owner: Meo Account database and /v1/ai/model-profiles API.
- Existing implementation: up to 20 profiles per account; each role maps to { credentialId, model }; one profile can be active.
- Existing roles: default, fast, thinking, vision, image, image_edit, video, speech, transcription, agent, router, judge, title, summary and embedding.
- Do not create a competing roles table or local profile JSON store.
- Show whether a role is actually routed at runtime. A saved preference must not be labelled active routing when runtime only supports one global model.
- Profiles can be named Cheapest, Best quality, OpenAI, Claude, etc. These are user configurations, not hard-coded modes.
- Validate connection ownership, enabled state, model availability and required modalities. If a model disappears, keep the profile and show a repair state rather than silently substituting another provider.

### Work task profile
General and Code are task profiles inside Work, not account profiles or separate agent runtimes.

- General: research, documents, file organization and data tasks.
- Code: repository context, Git, terminal, build, test and debugging tools.
- A task profile selects guidance, Skills, suggested tools and safe defaults. It does not grant permission.
- Target device and active workspace remain visible and explicitly selected.

### Profile UX

- Settings → Models: connections, model catalogue and model details.
- Settings → Model Profiles: create, edit, duplicate, activate and assign each role.
- Chat composer: active Model Profile selector and clear current model label.
- Work composer: General/Code profile plus explicit target device/workspace.
- Settings → Personalization & Memory: instructions, response language and memory controls.
- Account/security remains a separate Account-owned destination.

## 4. Provider and API connection management

### Ownership and current implementation

Provider keys belong to Meo Account, not the Meo AI client. Existing Meo API routes include:

- GET/POST /v1/ai/credentials
- PATCH/DELETE /v1/ai/credentials/:id
- GET /v1/ai/credentials/:id/models
- POST /v1/ai/credentials/:id/test
- POST /v1/ai/credentials/:id/test-image
- POST /v1/ai/provider-broker
- Model Profile endpoints under /v1/ai/model-profiles

The Account database stores encrypted credentials. API responses contain metadata and a masked hint, not plaintext keys. Current code supports up to 20 named connections per account; Model Profiles reference connection IDs.

The provider map in meo-api/src/ai-providers.ts currently includes OpenAI, Gemini, DeepSeek, OpenRouter and OpenAI-compatible endpoints. Direct Anthropic/Claude support is not present in that map. This is a real adapter gap, not a UI-only toggle.

### Provider connection screen

Each connection should show:

- Provider name and icon.
- User-defined connection name, e.g. OpenAI personal, DeepSeek main, OpenRouter backup.
- Status: not tested, connected, expired/rejected, disabled or error.
- Endpoint type and safe hostname for custom endpoints.
- Masked key hint; never return or re-display the saved key.
- Default model and model catalogue last-refreshed time.
- Last successful request and last error code.
- Whether the connection is selected by any Model Profile.
- Whether it is an inference connection or a separate billing-report connection.

Actions: Add, Test, Refresh models, Rename, Replace key, Disable, Repair and Delete. Replacing a key is deliberate; a blank key field means keep current key, never erase it.

### Multiple keys and provider routing

- Provider is a vendor/protocol family. Connection is one credential + endpoint + user label.
- A user may have several Connections for the same Provider. Each has a stable ID and independent status.
- A Model is identified by provider, connection, model ID and capability metadata.
- A Model Profile maps roles to model choices. A route policy may add ordered fallbacks, but fallback must be explicit and visible.
- Never silently send the same prompt to another provider after failure if that changes the user's data-sharing choice. Cross-provider fallback needs an explicit policy/grant covering destination and data categories.
- OpenAI-compatible does not prove every model supports tools, vision, streaming or JSON mode. Probe and store capabilities conservatively.

### Security requirements

- Keys are encrypted and decrypted only inside the trusted server-side broker.
- Do not persist provider keys in Meo AI Core config, local project files, prompts, logs, screenshots or device relay messages.
- Do not return secrets to Desktop, Web or Android.
- Keep Account consent and credential revision checks on every brokered call.
- Custom endpoints require strict HTTPS validation, a mandatory host allowlist, redirect control and SSRF/DNS-rebinding review. An empty allowlist must not accidentally mean trust every public host.
- Editing/deleting a connection and changing a custom endpoint require the existing purpose-scoped reauthentication flow.
- Local model endpoints are device-owned and must not be sent through the cloud provider broker.
- Admin/billing credentials are a separate connection type with separate scope and explicit opt-in. Never ask for organization-admin keys just to make chat work.

## 5. Usage and cost: exact source of every number

Do not show one unqualified cost number. Distinguish three sources.

### Source 1: per-request provider usage

The provider response is the first source for actual token counts. Normalize each provider response into one event:

- input tokens, cached input tokens, cache-write tokens where available
- output tokens and reasoning tokens where available
- provider, model, connection ID and model role
- request ID, conversation/project ID and timestamp
- duration and time-to-first-token where available
- modality-specific units for image/audio/video/search
- usage_source: provider_response, estimated, imported or unknown

If the provider does not return usage, estimate it and mark it estimated. Never silently substitute text-length estimates for provider-reported usage.

### Source 2: Meo's versioned price catalogue

Meo calculates an estimated cost from normalized usage and a versioned price snapshot. Each price record needs provider, model, modality, input/output/cache rates, modality-specific units, currency, effective dates, source URL, checked time, catalogue version and verification status.

Use integer fixed-point units (for example micro-USD), not floating-point arithmetic. Store the price snapshot used for each request so historical totals do not change when prices update. Unknown prices produce unknown cost, not zero.

### Source 3: provider-reported billing

Provider billing is separate from per-request token counts.

- OpenAI organization Costs API requires an Admin API key and reports organization-level cost aggregates.
- Anthropic Usage and Cost APIs require an Admin API key and report organization-level usage/cost data.
- DeepSeek's documented balance endpoint reports account balance, not a complete historical cost ledger. Use response usage plus official prices for estimates unless a new official billing endpoint is verified.
- Other vendors must be researched individually before being marked supported.

Billing-report credentials are optional, separately stored and clearly labelled. Do not use a normal inference key as if it had organization billing permissions. Aggregate provider reports may not map exactly to individual requests; do not invent per-request reconciliation.

### Cost fields and UI labels

Keep at least:

- estimated_cost_microusd
- provider_reported_cost_microusd (nullable)
- currency
- price_snapshot_id
- usage_source and cost_source
- reconciliation_status: not_available, pending, matched, difference or manual_review
- reconciled_at

UI labels:
- Estimated cost — calculated from usage and Meo's price snapshot.
- Provider bill — reported by the provider account, where supported.
- Meo Credits — Meo-hosted services/credits, shown separately.
- Unknown — source did not provide enough information.

Never add Meo Credits to a vendor's USD bill. Never call an estimate an actual charge.

### Current usage gap

Meo Core chat_event() currently estimates token counts from text and sets metadata.estimated=true. The Meo API usage table has estimated_cost_microusd, but broker streaming usage is not yet a complete normalized and persisted ledger across providers. ai-broker.ts extracts a limited usage shape from streamed provider chunks; provider-specific formats such as nested Responses API usage and Gemini usage need dedicated adapters and tests.

Required path: provider usage → normalized event → Meo API persistence → versioned price snapshot calculation → dashboard. Imported Codex/Claude Code usage remains attributed to its source.

## 6. Meo API access and authorization

### Client access

- Web: Meo Account browser session and exact allowed web origins.
- Native: OAuth 2.1 Authorization Code + PKCE; use Meo Account-issued access tokens.
- Product routes: bearer scopes meo:read for reads and meo:write for mutations. Actor identity comes from the token.
- Device relay: narrow, revocable device credentials; never reuse a provider key or general account refresh token.
- High-risk Account operations: purpose-bound, short-lived reauthentication grants.
- Resources not owned by the caller return not-found where appropriate; do not leak another user's resource existence.

### Access rules

- Every query and mutation uses authenticated actor ID. Never trust client-supplied user_id.
- Credentials, prompts, message content, local paths, session tokens and secrets must not appear in logs.
- CORS is not authentication. Non-browser clients still need valid bearer tokens and scope checks.
- Plugin enabled state is not authorization. Each tool call checks ownership, connection state, grant, data categories and tool policy.
- Public API docs describe route, method, scope, request/response schema, errors, rate limits and idempotency.
- Add per-user/per-client rate limits and cost budgets in addition to IP limits. Expensive inference, uploads, connector calls and provider tests need abuse controls.
- Custom provider endpoints need a mandatory allowlist and SSRF review.
- Keep production database roles restricted and actor-scoped. Do not add client-side database access.

### Developer API access

Meo API access means a Meo Account OAuth client and scoped access token, not a provider API key. A developer integration should register a client, use PKCE where it is a public client, request only required scopes, support revocation and use a separate client ID. Do not invent a permanent universal API key with unrestricted access.

## 7. Files, Projects and Workspaces

These are different data types and must not be collapsed into one Files bucket.

| Type | Owner | Physical location | Default behavior |
| --- | --- | --- | --- |
| Chat attachment | Conversation/user | Account cloud storage only when uploaded | Visible in that conversation; removable with confirmation. |
| Project file | Project/user | Meo API cloud storage or explicit connected storage | Persistent across the user's signed-in clients. |
| Work artifact | Work run/project | Usually target device workspace | Stays on target device; upload/share only on explicit action. |
| Local workspace file | Device/workspace | Local filesystem | Never silently uploaded or indexed across devices. |
| Plugin/Skill asset | Plugin owner | Account plugin storage or trusted package | Obeys plugin ownership and size/type limits. |
| Export/archive | User request | User-selected destination | Created only after explicit export. |

A workspace is an opaque device-local reference, not a filesystem path in cloud APIs. Chat does not receive general workspace or shell authority. Work shows the target device, workspace and permission mode before acting.

### File service requirements

- Stable file ID, owner ID, project/conversation scope, display name, MIME type, size, checksum, timestamps and storage state.
- Upload, list, download, delete, rename and version operations with owner/scope checks.
- Binary object lifecycle: upload reservation, object write, metadata commit, integrity check, download authorization and deletion/cleanup.
- Text extraction is a derived preview/index, not the original file.
- Quotas account for extracted text and binary object bytes.
- Enforce size limits, MIME sniffing, extension consistency, safe archive handling and parser timeouts.
- File content is untrusted data, never trusted instructions.
- Delete removes object and metadata safely or queues retryable cleanup. Never leave an object orphaned or permanently block deletion.
- Define retention/export behavior when a conversation or project is archived/deleted.
- Search/indexing is opt-in and follows owner, project and permission boundaries.

### Current file gap

Meo API src/files.ts requires text content for upload even though several document MIME types are listed. It tracks object_key/object size in metadata, but deletion returns object_delete_not_configured when an object key exists. Binary storage and its full lifecycle need a dedicated implementation slice before the UI claims full file management.

## 8. Repository ownership map

| Path | Authority | Rule |
| --- | --- | --- |
| meo/core-rs/ | Shared Rust product core and cloud AppCore | New product behavior starts here. |
| meo/ui-schema/ | Shared navigation, pages, features and settings | Do not duplicate settings/navigation in clients. |
| meo/desktop-rs/ | Desktop renderer and platform integration | Presentation and device integration only. |
| meo/web/client/ | Web renderer | No second AI engine or provider-key store. |
| meo/android/ | Android renderer | Same product contracts; platform differences explicit. |
| meo/skills/, meo/prompts/, meo/usage/ | Bundled data, prompt assets and usage import | Not a second runtime authority. |
| meo/service/, meo/runtime/, meo/system/, meo/adapters/ | Paused/compatibility code per root AGENTS.md | Do not extend unless owner changes that decision. |
| meo/cloud/, meo/device/ | Compatibility device/AgentRun implementation | Do not confuse with active meo/core-rs/src/cloud/. |
| Root src/, modules/, data/, po/ | Newelle upstream compatibility tree | Preserve provenance; remove only after migration gates. |
| QwQdoge/meo-api | Versioned product API, AI data and usage | Separate private repository; changes need a matching cross-repo task. |
| QwQdoge/MeoArch-account | Identity, OAuth, security and encrypted provider credential authority | Never duplicate these authorities in Meo AI. |
| MeoUI / System AI Router | Shared controls/tokens and privileged OS execution | Consume their contracts; do not copy their authority. |

## 9. Delivery rule

Build one vertical slice at a time. Each slice defines owner, source-of-truth file, API contract, UI surfaces, migration needs, tests, rollback and acceptance criteria. Do not start a broad refactor while a smaller correctness/security task is unresolved. See implementation-backlog.md for ordered work and exact file targets.
