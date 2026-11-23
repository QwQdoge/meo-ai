# Meo AI Repository Audit — 2026-11-22

> Superseded for maintenance by [repository-audit.md](repository-audit.md), the canonical audit that root AGENTS.md links. Keep this file only for its profile and product-structure notes and update the canonical file, not this one. The verified code findings below still held on 2026-11-23.

Status: read-only audit of the current default branches. This records verified code/documentation gaps; it does not claim that planned behavior is implemented.

Repositories reviewed:
- QwQdoge/meo-ai — product client, Rust Core, UI schema and architecture documents.
- QwQdoge/meo-api — authenticated product API, provider broker, files and storage routes.
- QwQdoge/MeoArch-account — identity and encrypted provider-credential authority (repository root inspected; detailed implementation review remains a separate task).

## Executive summary

Meo AI already has a meaningful architecture. Do not replace it with a new provider gateway, profile database or plugin runtime. The intended authority split is sound: Rust Core owns shared product behavior; Meo Account owns identity and encrypted provider credentials; Meo API owns AI product data and authorization; clients render shared contracts.

The biggest immediate problems are correctness and security, not missing screens:
1. Custom provider endpoint allowlisting currently fails open when the allowlist is empty.
2. The file API is text-first, not a complete binary file service; object-backed deletion is not implemented.
3. Storage status has duplicate route logic in files.ts and credit-routes.ts; entry.ts calls the Credit handler before the File handler.
4. Usage records exist, but the Meo Core currently estimates token counts from text. Provider-reported usage is not yet a complete normalized, persisted per-request ledger.
5. Anthropic is not a direct provider in the current provider map, despite being part of the desired official-provider set.
6. The large Rust AppCore file is a maintainability risk. Split it only after behavior contracts and tests exist.

## Verified findings

### Provider and key management

- Meo API already exposes credential list/create/update/delete, model discovery, test and image-test routes under /v1/ai/credentials.
- Credentials are stored in the Account database encrypted with the server-side AI_CREDENTIALS_MASTER_KEY. API metadata is masked; clients should never receive saved plaintext keys.
- The current provider map includes OpenAI Responses, Gemini, DeepSeek, OpenRouter and OpenAI-compatible. Anthropic is absent from the provider map.
- Multiple named credentials and up to 20 Model Profiles are already supported. Model Profile roles reference credential IDs and model IDs. Do not add another key store or profile table.
- Current custom endpoint logic only rejects a host not on the allowlist when the allowlist has at least one entry. An empty allowlist therefore does not fail closed. Fix this before expanding custom endpoint support.
- The endpoint check is string/URL validation, not a complete network-layer SSRF guarantee. Redirect behavior, DNS rebinding and outbound network policy need review.

### Profiles: required product meaning

Keep four distinct concepts; do not use one generic Profile object for all of them.

Account profile (Meo Account-owned):
- Display name and avatar.
- Verified email as read-only account metadata in Meo AI.
- Linked sign-in methods and account status as read-only metadata.
- Subscription/plan summary as read-only metadata.
- Security, sessions, password and account deletion remain Account-owned pages/actions.
- Never put provider API keys, access tokens or private security data in this profile.

Personalization profile (Meo API/Core-owned):
- Custom assistant instructions.
- Preferred response language.
- Response detail level and tone preference.
- Memory enabled/disabled preference and memory controls, kept separate from transcript history.
- These preferences may guide answers but must never grant tools, filesystem access or security permissions.

Model Profile (existing Meo Account-owned data):
- Name, description, active state and role-to-connection/model mapping.
- Existing roles include default, fast, thinking, vision, image, image_edit, video, speech, transcription, agent, router, judge, title, summary and embedding.
- UI must distinguish saved mapping from runtime-confirmed routing per role. A saved preference must not be labelled active routing. (Corrected 2026-11-23: the active Core already routes six roles through `role_model()`; the runtime is not a single global model. See [product-architecture-plan.md](product-architecture-plan.md) §3.)
- Show missing/disabled connection and unsupported capability as repair states; do not silently substitute another provider.

Work task profile (Meo Core-owned behavior):
- General and Code are task profiles inside Work, not account profiles or separate runtimes.
- They select task instructions, Skills, suggested tools and defaults only.
- Target device, workspace and permission mode must remain explicit for every Work task.

### Usage and cost

- The AI usage migration already defines ai_usage_events with per-user source/event ID, provider, model, role, token categories, duration and estimated_cost_microusd.
- The schema is a useful base, but it does not yet express all the required provenance and billing reconciliation states as first-class fields.
- Meo Core usage currently estimates token counts from text and marks metadata.estimated=true. These values must not be shown as provider-reported actual token usage.
- The product needs three visibly separate numbers: provider-reported usage, Meo-calculated estimated cost using a versioned price snapshot, and provider-reported billing aggregates.
- OpenAI and Anthropic organization billing reports require separate admin-level credentials. They are optional and must never be required for ordinary inference.
- DeepSeek balance is not a historical invoice ledger. Do not treat balance as per-request actual spend.
- Never convert a provider aggregate into per-request charges unless the provider data supports a defensible match.
- Keep Meo Credits separate from vendor currency costs.

### Meo API access and authorization

- API documentation defines browser cookie sessions and native/third-party OAuth 2.1 Authorization Code + PKCE bearer tokens.
- Bearer reads require meo:read; mutations require meo:write. Actor identity must come from the authenticated token, never a client-supplied user_id.
- Device pairing has a separate narrow device credential flow. Do not reuse provider keys or general account refresh tokens as device credentials.
- High-risk Account operations use purpose-bound reauthentication grants.
- CORS is limited to the known web origins, but CORS is not authentication. Native and external clients still require valid bearer tokens and scopes.
- There is no reason to introduce an unrestricted permanent universal Meo API key. Developer access should use registered OAuth clients, PKCE for public clients, narrow scopes, expiry and revocation.
- Add user/client rate limits, concurrency limits and spend budgets for inference, provider tests, uploads and connector calls. IP-only limits are not enough.

### Files and workspaces

- Current file endpoints are GET/POST /v1/files, GET /v1/files/:id/content, DELETE /v1/files/:id and GET /v1/storage.
- Upload requires a non-empty text field and stores extracted_text. Supported MIME labels include PDF and Office formats, but that does not mean original binary upload/storage is implemented.
- File listing is capped at 200 rows and has no cursor pagination.
- File content returns extracted text, not an original binary object download.
- Deleting a file with object_key set returns object_delete_not_configured and leaves the record in place.
- files.ts and credit-routes.ts both contain /v1/storage handling. entry.ts invokes handleCreditRoute before handleFileRoute, so the Credit route currently takes precedence. Remove the duplicate or make the ownership explicit.
- Chat attachments, persistent Project files, Work artifacts and device-local workspace files must remain distinct. Device-local paths must never be uploaded as cloud metadata or synced implicitly.
- Project environment docs correctly state that local folders remain on the device; this should remain a hard boundary.

## Recommended product structure

Primary navigation: Chat, Work, Projects, Skills/Plugins. Settings is a destination, not a competing product mode.

Settings groups:
- Preferences: General; Personalization & Memory.
- AI: Models & Connections; Model Profiles; Usage & Costs; Plugins & Permissions.
- Account: Account Profile; Security; Subscription.

Models & Connections should manage named connections, not raw keys as UI objects. A connection has provider, user label, endpoint kind/host, masked hint, enabled state, last test result and model catalogue freshness. A provider may have several connections. Billing-report credentials are a separate optional connection type.

Usage & Costs should show time range, provider/model/role filters, token categories, estimated cost, provider-reported billing, Meo Credits and reconciliation status. Every number must identify its source and confidence.

Plugins should include Discover, Installed and Import, with clear lifecycle state and requested permissions. In v1, keep Skills text-only and do not execute downloaded plugin code. Plugin state never grants authorization.

Files should not be one mixed bucket. Separate Chat attachments, Project files, Work artifacts, local workspace references and plugin assets. Show storage location, scope, owner, size, type, origin and available actions.

## Ordered implementation direction

1. Fix custom endpoint allowlist fail-open and verify outbound/redirect policy.
2. Add authenticated user/client rate and spend budgets.
3. Make one normalized usage event contract and capture actual provider usage for each supported adapter.
4. Add versioned pricing and clearly labelled estimates.
5. Add optional provider billing reconciliation using separate admin credentials.
6. Add direct Anthropic support with its own request/stream/usage adapter.
7. Make Model Profile routing status truthful, then complete the shared connection/settings UI.
8. Define plugin manifest and permission lifecycle before any third-party executable extensions.
9. Complete binary file upload/download/delete and storage lifecycle before building a full File Manager UI.
10. Split AppCore by domain only after contract tests; label compatibility trees without moving/deleting them.

## Important caution

This audit is based on repository source and documentation, not a live production deployment, production database inspection, or real provider calls. It does not verify deployed Worker bindings, production migrations, actual object-store configuration, OAuth client registration in the Account service, or current vendor billing permissions. Those must be checked in the corresponding task before marking implementation complete.

## Source files checked

- meo-ai: AGENTS.md, docs/ownership.md, meo/README.md, meo/docs/product-architecture-plan.md, meo/docs/implementation-backlog.md, meo/docs/chat-work-product-model.md, meo/docs/plugins-and-connectors.md, meo/docs/projects-and-environments.md, meo/docs/ui-redesign.md, meo/core-rs/src/cloud/usage.rs, meo/core-rs/src/cloud/storage.rs, meo/ui-schema/*.
- meo-api: src/entry.ts, src/ai-providers.ts, src/ai-broker.ts, src/chat.ts, src/files.ts, src/credit-routes.ts, docs/api-reference.md, migrations/ai/0003_usage.sql.
- MeoArch-account: repository metadata and root tree only; detailed auth/credential review is not included.

See implementation-backlog.md for task IDs and acceptance criteria.