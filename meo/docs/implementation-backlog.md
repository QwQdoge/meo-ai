# Meo AI Implementation Backlog

Status: ordered planning list, 2026-11-22. Items are intentionally small. Do not execute the whole backlog in one agent run.

Latest source audit: [repository-audit.md](repository-audit.md) (canonical). Read its verified findings before choosing a task.

## Checks per repository (verified 2026-11-23)

Run the narrowest line for the task's repo; report which one ran.

| Repo | Focused check |
| --- | --- |
| `QwQdoge/meo-api` | `npm run typecheck`; offline route/provider tests: `npm run test:offline`; live provider calls: `npm run test:integration` (separate, needs real keys). |
| `QwQdoge/meo-ai` Rust core | in `meo/core-rs`: `cargo fmt --check`; `cargo test --locked --all-features` |
| `QwQdoge/meo-ai` docs-only | Path/link check plus a focused grep for the conflicting phrase. |
| `QwQdoge/meo-ai` UI schema | `node meo/ui-schema/generate.mjs --check` |

Cross-repo tasks (most of Priority 0/1) change `meo-api` first, then the `meo-ai` contract and client view. Record the API contract change in `meo-api` docs in the same task; never ship a client that assumes an unmerged API shape.

## How the next agent must work

1. Read root AGENTS.md, meo/docs/product-architecture-plan.md, this file and the relevant contract before editing.
2. Confirm the current main head and re-check target files. This plan is a map, not permission to ignore newer code.
3. Work on exactly one task ID at a time. Do not combine unrelated provider, UI, storage and refactor work.
4. Mark one item [~] only when work starts. Mark [x] only after the focused check passes and relevant docs are updated.
5. Keep changes narrow. Prefer one vertical slice: contract → implementation → one client surface → focused tests.
6. Do not change production Neon data, Cloudflare bindings, secrets, billing settings or deploy production without a separate explicit request.
7. Never put keys, tokens, user content or local filesystem paths in commits, logs, test snapshots or screenshots.
8. Do not add a second source of truth. Search for existing API, schema and UI contract before adding a table or setting.
9. If a task needs a database migration, write the migration and offline tests first; do not apply it to production as part of the code task.
10. After each task, report files changed, tests run, limitations and the next single task. Stop before starting the next task.

The repository AGENTS.md workflow controls branch/commit behavior. Do not create a branch or PR unless the owner asks.

## Priority 0 — correctness and safety

### MEO-001 — Reconcile architecture documentation

- [x] Status: done 2026-11-23 (meo-ai `main`): one active/paused map across the docs
- Files: AGENTS.md; README.md; docs/ownership.md; meo/README.md; meo/docs/architecture.md; meo/docs/product-architecture-plan.md
- Work:
  - Make root AGENTS.md the contributor authority.
  - State that meo/core-rs/src/cloud/ is the active cloud-first AppCore.
  - Label meo/cloud/, meo/device/, meo/service/, meo/runtime/, meo/system/ and meo/adapters/ as compatibility/paused unless a newer owner decision changes this.
  - Correct the stale C++ desktop description to current meo/desktop-rs Rust + Qt/QML/MeoUI.
  - Keep Newelle provenance and migration gates.
- Result:
  - `docs/ownership.md` gained a "Current status (2026-11-23)" block naming active vs paused trees; the C++ desktop, C++ migration-rule and split-gate claims now describe `meo/desktop-rs`; gate 5 no longer asks packaging to launch the paused Python AgentService.
  - `meo/README.md` states the active cloud-first path and marks "Phase B AgentService" as paused compatibility; `meo/docs/architecture.md` is now an explicit historical document (2026-10-08) with the current facts in a banner and its `meo/app` section labelled historical.
  - `meo/docs/unified-platform.md` repository map and `meo/docs/unified-platform-roadmap.md` status now match root AGENTS.md; `meo/docs/capabilities.md` no longer credits a removed C++ client; `meo/docs/repository-audit.md` marks its documentation-drift findings reconciled.
  - AGENTS.md itself already carried the authority, paused list and repository map, so it was left as the source rather than duplicated.
  - Checks: relative-link/path check across 13 docs (0 broken) and a focused grep for the old C++/`meo/app` and "paused stack as primary" phrases (no remaining live claims).

### MEO-002 — Harden custom provider endpoint policy

- [x] Status: done 2026-11-23 (meo-api `main`): custom endpoints now fail closed
- Repo: QwQdoge/meo-api
- Files: src/ai-providers.ts; src/ai-broker.ts; src/types.ts; test/credentials.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md
- Result:
  - One policy, `src/ai-endpoints.ts::providerEndpoint`, shared by save/edit/discovery (`ai-providers.ts`) and inference/images/speech (`ai-broker.ts`); the two older duplicate host checks are gone.
  - `AI_CUSTOM_ENDPOINT_HOSTS` now fails closed: empty or missing denies every `openai_compatible` endpoint. Saved connections are re-checked on every use, so removing a host disables them.
  - Host rules reuse `src/ssrf.ts::forbiddenHost` (loopback, private, link-local, CGNAT, multicast, metadata, blocked suffixes); still HTTPS-only, port 443, no userinfo/query/fragment. Provider fetches keep `redirect: 'manual'`.
  - Error: `403 custom_ai_endpoint_not_enabled`; `400 ai_endpoint_not_permitted` / `400 invalid_ai_endpoint` for a malformed destination.
  - Checks: `npm run typecheck` and `node --import ./test/route-mocks.ts test/credentials.test.ts` (5 new cases: empty allowlist, unlisted host, listed host saved case-insensitively, model discovery, edit re-check).
  - Deployment precondition, not done here: `AI_CUSTOM_ENDPOINT_HOSTS` must list every approved host in the Worker before this Worker is deployed, or existing custom connections will be refused.
- Work:
  - Make custom endpoint allowlisting fail closed when no approved hosts are configured.
  - Apply the same policy during save, edit, test, model discovery and inference.
  - Keep redirects disabled and review IPv4, IPv6, localhost, private, link-local, unusual ports, userinfo, query and fragment cases.
  - Review DNS rebinding and Worker outbound behavior; string checks alone are not full SSRF protection.
  - Return a clear endpoint-not-approved error.
- Acceptance: no custom endpoint can be saved or called unless its host is approved; no provider key reaches an unapproved destination; focused security tests pass.
- Dependencies: none. Complete before broadening custom endpoint UX.

### MEO-003 — Add account-level API spend and abuse limits

- [x] Status: done 2026-11-23 (meo-api `main`) for authenticated budgets; stream-scoped concurrency split to MEO-003B
- Repo: QwQdoge/meo-api
- Files: src/entry.ts; src/chat.ts; src/ai-broker.ts; src/credits.ts; src/types.ts; test/rate-limit.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md
- Result:
  - New `src/actor-limits.ts` owns the per-account budget and nothing else. Keys are `user:<uuid>` plus `client:<id>` when the token proves an OAuth client, so another IP, device or account session does not reset the allowance. The window/count live on the Cloudflare binding (`ACTOR_AI_RATE_LIMIT`, `ACTOR_API_RATE_LIMIT`) rather than a new policy table.
  - Enforced on the work that spends provider capacity: broker `stream_invoke`/`invoke`/`generate_image`/`generate_icon_material_pack`/`transcribe`/`synthesize` (which also covers `/v1/chat/*` and `/v1/images/*`, as those call the broker), provider connection tests, file uploads, and web search/fetch. Ordinary reads are untouched.
  - Failure policy: a configured but unavailable expensive binding returns `503 rate_limit_unavailable` with `Retry-After: 30` instead of running unbudgeted; the ordinary binding fails open. Exhausted budgets return `429 actor_rate_limited` with `Retry-After: 60`.
  - No second spend authority: Meo-paid spend stays in `credits.ts`; the consent budget stays in `ai-broker.ts`. Missing bindings are visible as `not_configured`/`actor_rate_limits` in admin and service status.
  - Checks: `npm run typecheck`; `node --import ./test/route-mocks.ts test/rate-limit.test.ts` (unit keys/failure policy plus route proofs: cookie, bearer, two IPs same account, unavailable binding, reads unaffected); `test/credentials.test.ts`, `test/routes.test.ts`, `test/cloud-data-gate.test.ts` for regressions.
  - Deployment precondition, not done here: create the two Cloudflare Rate Limiting bindings and add them to the Worker before relying on the budgets. Without them the existing IP limits, consent budget and credit caps still apply and the admin status shows the gap.
  - Not included: true in-flight concurrency for streamed answers. That needs a lease tied to the SSE stream lifetime (release on stream close/cancel), which is its own testable slice. See MEO-003B.
  - Not included: device-credential budgets. Device pairing keeps its own bindings, but device relay calls (agent runs, realtime) still have no per-device + owning-account budget; add that with MEO-003B or as its own slice once the device auth path is confirmed.
- Acceptance: users cannot bypass spend limits by switching IP/device; ordinary reads are not blocked by AI spend limits; tests cover cookie, bearer, multi-device and limiter-unavailable cases.

### MEO-003B — Stream-scoped concurrency limit

- [ ] Status: planned; the concurrency half of MEO-003
- Repo: QwQdoge/meo-api
- Files: src/actor-limits.ts; src/ai-broker.ts; src/chat.ts; test/rate-limit.test.ts; a migration only if a lease table is chosen
- Work:
  - Hold one per-account lease for each in-flight streamed answer or provider call and release it when the stream closes, errors or is cancelled.
  - Refuse over-concurrency before any provider call with a stable code (for example `actor_busy`) plus `Retry-After`.
  - Reuse the existing `USER_HUB` Durable Object for the counter, or a lease table with expiry; never add a second account database.
  - Cover disconnect, cancel, timeout and Worker eviction so a crashed request expires its lease instead of blocking the account.
- Acceptance: N concurrent answers per account are allowed and N+1 is refused; a cancelled or dropped stream frees its slot; no lease outlives its request.
- Dependency: one decision on DO counter vs lease table.

### MEO-004 — Make file deletion and object lifecycle safe

- [ ] Status: planned; blocks full file-manager claims
- Repo: QwQdoge/meo-api
- Files: src/files.ts; src/credit-routes.ts; src/types.ts; migrations/ai/; test/routes.test.ts; test/cloud-data-gate.test.ts; docs/api-reference.md
- Work:
  - Specify actual object-store binding and object-key ownership.
  - Implement deletion or durable retryable cleanup for object-backed files.
  - Make metadata/quota updates transactional and safe on partial object-store failure.
  - Add orphan cleanup and idempotent delete behavior.
  - Do not claim binary upload is implemented until upload, download, quota and deletion all work.
- Acceptance: owned object-backed files can be deleted without orphaned objects; failed deletion remains visible/retryable; foreign IDs still return not-found.
- Dependency: storage-provider decision and offline object-store test harness.

### MEO-005 — Remove duplicate storage route ownership

- [x] Status: done 2026-11-23 (meo-api `main`): the Credit/Storage route is the only owner
- Repo: QwQdoge/meo-api
- Files: src/files.ts; src/credit-routes.ts; src/entry.ts; focused route tests; docs/api-reference.md
- Work:
  - Keep exactly one owner for GET /v1/storage.
  - entry.ts currently calls handleCreditRoute before handleFileRoute; verify the effective route and remove the shadowed duplicate implementation.
  - Keep storage quota, Meo Credits and upload-pause semantics in the Credit/Storage authority; file metadata endpoints must not maintain a second quota view.
- Result:
  - Confirmed `entry.ts` dispatches `handleCreditRoute` first, so `credit-routes.ts` already answered `GET /v1/storage`; the files copy was unreachable.
  - Removed the `storageStatus` function and the `/v1/storage` branch from `handleFileRoute`; `files.ts` now serves `/v1/files` metadata and content only, with a header comment naming the real owner.
  - Added three routing checks: the Credit view schema answers (plan/`used_bytes` including other apps/quota/tiers, and no `{storage:{…}}` shape), unauthenticated is 401 with no storage query, and a bearer without `meo:read` is 403.
  - Checks: `npm run typecheck`; `node --import ./test/route-mocks.ts test/routes.test.ts`; `node --import ./test/route-mocks.ts test/cloud-data-gate.test.ts`.
  - No change to quota, credits or upload-pause semantics; no migration, deploy or production data touched.

### MEO-006 — Audit and document third-party Meo API client onboarding

- [ ] Status: planned; cross-repository
- Repos/files: QwQdoge/MeoArch-account OAuth client registration and consent routes; QwQdoge/meo-api src/bearer.ts, src/account-access.ts, docs/api-reference.md; QwQdoge/meo-ai developer documentation.
- Work:
  - Verify how a developer registers an OAuth client, allowed redirect URIs, public-client PKCE, scopes, access-token lifetime, refresh/revocation and client ownership.
  - Document a minimal external-client example using meo:read and a separate opt-in meo:write grant.
  - Keep browser cookie sessions, native OAuth access tokens and device-pairing credentials distinct.
  - Do not introduce a permanent universal API key or expose Account/provider secrets.
- Acceptance: a developer can follow documented steps to obtain and revoke a least-privilege token; scopes are enforced server-side; no secret is stored in a client app bundle.

### MEO-007 — Add cursor pagination to file listing

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/files.ts; docs/api-reference.md; file route tests.
- Work:
  - Replace the fixed 200-row cap with stable cursor pagination ordered by updated_at and id.
  - Keep project_id and conversation_id filters actor-scoped.
  - Define bounded page size, next_cursor and invalid/expired cursor behavior.
- Acceptance: files beyond the first page are reachable without duplicates or omissions; cross-user IDs remain hidden; existing clients can migrate without silently truncating results.

## Priority 1 — provider and cost correctness

### MEO-010 — Define one normalized usage event contract

- [x] Status: done 2026-11-23 (meo-ai + meo-api `main`): the version-2 contract
- Repos/files:
  - QwQdoge/meo-ai: meo/core-rs/src/cloud/usage.rs; meo/core-rs/src/cloud/usage_import.rs; focused Core tests.
  - QwQdoge/meo-api: migrations/ai/0003_usage.sql; src/chat.ts; src/ai-broker.ts; usage route tests; docs/api-reference.md.
- Result:
  - Contract written down once in [usage-event-contract.md](usage-event-contract.md) and in `meo-api/docs/api-reference.md` §12.
  - `migrations/ai/0022_usage_event_contract.sql`: adds `event_version`, `usage_source`, `modality`, `ttft_ms`; token categories become nullable; `total_tokens` is generated and `null` when nothing was reported; existing rows are labelled `estimated` (Meo) or `imported` (importers).
  - API ingestion (`src/index.ts`): validates provenance and modality; rejects an explicit `unknown` that still asserts counts; rejects content/local-path metadata; legacy events without provenance are stored as `unknown` with their `0` placeholders turned into `null`; the existing unique `(user, source, source_event_id)` upsert remains the idempotency key.
  - Core producers: `chat_event` sends `usage_source: "estimated"` with cache/reasoning/ttft as `null`; the Codex importer sends `imported` and leaves cache writes `null`; the Claude importer sends `imported` and leaves reasoning `null`.
  - Dashboard now returns per-event provenance (`usage_source`, `modality`, `event_version`, `ttft_ms`) and refuses to treat an unknown total as a measured one.
  - Checks: `cargo test --lib usage` (11 passed); `npm run typecheck`; `node --import ./test/route-mocks.ts test/routes.test.ts` (5 new usage cases: declared source stored, unknown+counts rejected, legacy placeholders, metadata smuggling, negative/fractional counts).
  - Deployment precondition, not done here: migration `ai/0022` must run before the Worker that reads `total_tokens` is deployed.
  - Not included: provider-reported usage adapters (MEO-011) and pricing (MEO-012); no `provider_response` producer exists yet.
- Acceptance: every count has a declared source; duplicate ingestion does not double count; unknown counts are not fabricated as zero; fixtures cover supported provider formats.

### MEO-011 — Capture actual provider usage for supported adapters

- [x] Status: done 2026-11-23 (meo-api + meo-ai `main`): provider usage captured and persisted server-side
- Repo: QwQdoge/meo-api
- Files: src/ai-broker.ts; provider-specific usage normalizers; src/chat.ts; test/ai-endpoints.test.ts; provider fixtures under test/.
- Result:
  - `normalizeProviderUsage()` in `src/ai-broker.ts` handles the five shapes separately: OpenAI Responses (`response.usage` + `_details`), OpenAI Chat Completions, DeepSeek (`prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`), OpenRouter, and Gemini (`usageMetadata` with `thoughtsTokenCount`). The cached portion is subtracted from the prompt count so `total_tokens` does not double count, and a category the provider did not report is absent, not 0.
  - The normalized usage is forwarded in the `done` event and written by the server itself (`recordBrokeredUsage`, one row keyed by the consent request id, `usage_source: "provider_response"`), so a client that never reports cost still gets a truthful ledger row. Cancellation or failure writes nothing; re-sending the same id conflicts with itself.
  - The client event for the same call uses the same id and carries the provider counts, so it adds conversation/project attribution instead of a duplicate. Ingestion refuses to let an `estimated` event overwrite a `provider_response` row.
  - Core: `ChatEvent::Done(Option<Value>)` carries the usage; `usage::Usage` reads the contract keys; `chat_event_with_usage` emits `provider_response` when measured and `estimated` otherwise.
  - Checks: `node --import ./test/route-mocks.ts test/provider-usage.test.ts` (fixtures for all five shapes, idempotent row, no row without usage); `test/routes.test.ts`, `test/rate-limit.test.ts`, `npm run typecheck`; `cargo test --lib usage` (13 passed).
  - Not covered: provider billing reports (`usage_source` stays request-level) and price calculation (MEO-012). Helper calls still write an estimate from the client because the server row carries no role attribution.
- Acceptance: fixtures preserve input/output/cache/reasoning counts; cancellation/failure creates no completed event; success creates one idempotent event.

### MEO-012 — Add versioned model pricing and estimates

- [ ] Status: planned
- Repos/files:
  - QwQdoge/meo-api: new AI pricing migration/table, pricing service, usage dashboard, tests and API docs.
  - QwQdoge/meo-ai: meo/core-rs/src/cloud/usage.rs and usage view contract.
- Work:
  - Create a versioned price catalogue by provider/model/modality with source URL, currency and effective dates.
  - Store price snapshot ID on each event.
  - Calculate using integer fixed-point units (micro-USD), including cache and modality-specific units where supported.
  - Unknown prices produce unknown cost, not zero.
  - Expose estimate labels and price verification dates.
- Acceptance: historical estimates do not change when catalogue prices update; tests cover rounding, cache rates, missing rates, currency and date boundaries; UI never labels estimates as actual bills.

### MEO-013 — Add optional provider billing reconciliation

- [ ] Status: planned, opt-in
- Repos/files: QwQdoge/meo-api provider billing adapters, separate credential metadata, reconciliation schema/job, tests and docs; QwQdoge/meo-ai Usage UI.
- Work:
  - Research current official billing APIs and required permissions per vendor.
  - Treat OpenAI and Anthropic organization billing credentials as separate admin connections, not inference keys.
  - Treat DeepSeek balance as a balance signal, not historical invoice data.
  - Store provider-reported aggregates separately from estimated per-request cost.
  - Match only when provider data supports a defensible match; otherwise show aggregate difference/pending.
- Acceptance: Meo works without billing-admin credentials; no aggregate amount is fabricated into per-request charges; reconciliation is auditable/idempotent.

### MEO-014 — Add direct Anthropic provider support

- [x] Status: done 2026-11-23 (meo-api + meo-ai `main`): a real Anthropic Messages adapter
- Repo: QwQdoge/meo-api
- Files: src/ai-providers.ts; src/ai-broker.ts; provider request/response adapters; src/model-capabilities.mjs; test/credentials.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md.
- Result:
  - `provider: "anthropic"` → `api_style: "anthropic_messages"`, endpoint `https://api.anthropic.com/v1`, `x-api-key` + `anthropic-version: 2023-06-01`, destination `/messages`, catalogue via `/models?limit=1000` with `display_name`.
  - Request: top-level `system`, required `max_tokens`, base64 image source blocks, tools with `input_schema` and `tool_choice: {type: "auto"}`; finished turns replay as `tool_use`/`tool_result` (images allowed inside a tool result).
  - Stream: `content_block_delta` text, `input_json_delta` tool arguments collected into declared calls only, `stop_reason: "max_tokens"` mapped to the truncated signal, non-stream text from `content` blocks.
  - Usage: Anthropic reports `input_tokens` already excluding cached tokens, so no subtraction; `message_start` (input/cache) and `message_delta` (cumulative output) are merged across chunks.
  - Core: the AI connection picker offers Anthropic and labels it.
  - Checks: `test/anthropic.test.ts` (stored style, request shape, tools, stream/stop, text, split usage); `test/provider-usage.test.ts`, `test/routes.test.ts`, `test/rate-limit.test.ts`, `npm run typecheck`; `cargo test --lib usage`, `cargo test --lib services`.
  - Not covered: live provider calls (`test/ai-endpoints.test.ts` is integration-only, needs a real key); image generation through Anthropic is not offered because the image path only accepts OpenAI-compatible credentials.
- Acceptance: save/test, discovery, consent, stream, cancellation, tool support and usage have fixtures; unsupported features are reported honestly.

## Priority 2 — model profiles and provider UX

### MEO-020 — Make Model Profile routing status truthful

- [ ] Status: planned
- Repos/files: QwQdoge/meo-api src/model-roles.mjs, src/ai-providers.ts and profile tests; QwQdoge/meo-ai meo/core-rs/src/cloud/app.rs, meo/docs/presentation-model-routing.md and view fixtures.
- Work:
  - Keep existing Account-owned ai_model_profiles schema and role catalogue.
  - Distinguish saved preference, active profile and runtime-supported routing **per role**.
  - Verified 2026-11-23: `role_model()` in `meo/core-rs/src/cloud/app.rs` already routes `router`, `title`, `check` (profile role `judge`), `judge`, `agent` and `summary` from the active profile with model-health fallback; the answer path sends a per-request route. This is not a single-global-model runtime.
  - Remaining work is the honest surface plus the unrouted roles: `vision`, `image`, `image_edit`, `video`, `speech`, `transcription`, `embedding`, and explicit profile `default`/`fast`/`thinking`. Route a role only after the surface can name which roles are wired.
  - Validate connection ownership, enabled state and model capability at save and use time.
- Acceptance: the UI marks a role as actively routed only when `role_model` resolves it; unrouted roles say so; concurrent requests cannot race by mutating global model selection; disabled connections show repair state, not silent substitution.

### MEO-021 — Design connection and model catalogue UX

- [ ] Status: planned
- Repo/files: QwQdoge/meo-ai meo/ui-schema/settings.json, pages.json, navigation.json, meo/core-rs/src/cloud/app.rs and desktop/web/Android renderers. API contract remains in QwQdoge/meo-api.
- Work:
  - Settings → Models lists connections, status, masked hint, endpoint hostname, default model, last test and selected profiles.
  - Add/test/refresh/rename/replace/disable/delete actions use existing Account/API endpoints.
  - Catalogue shows context window, modalities, tool support and price-source freshness.
  - Billing-admin credentials remain separate from inference credentials.
- Acceptance: all clients render the same state/action contract; no client receives plaintext saved keys; errors and reconnect states are actionable.

## Priority 3 — plugin system

### MEO-030 — Define plugin manifest and lifecycle v1

- [ ] Status: planned
- Files: QwQdoge/meo-ai meo/core-rs/src/cloud/plugin_store.json, new manifest/schema module, Core tests and meo/docs/plugins-and-connectors.md; QwQdoge/meo-api existing plugin/Skill endpoints remain persistence source.
- Work:
  - Define typed kinds: provider adapter, connector, Skill, bundle and built-in capability.
  - Add versioned manifest validation, compatibility, publisher/integrity, permissions, network origins, settings and lifecycle.
  - Keep built-in catalogue, installed account records and runtime connection status separate.
  - Do not execute downloaded code in v1.
- Acceptance: invalid/unknown manifest fields fail closed; Skills cannot grant tools/permissions; disabled/removed plugins stop calls and revoke grants.

### MEO-031 — Unify plugin permission presentation

- [ ] Status: planned
- Files: meo/core-rs/src/cloud/app.rs; meo/docs/plugins-and-connectors.md; meo/ui-schema/pages.json; focused Core/API tests.
- Work:
  - One permission model for bundled tools, MCP connectors and future plugins.
  - Show data categories, effect level, destination and approval rule.
  - Re-check server-side authorization on every call.
  - Keep read-only standing grants separate from write/effectful one-time approval.
- Acceptance: UI state never grants authority; model-proposed tool calls cannot bypass approval mode.

## Priority 4 — file and workspace system

### MEO-040 — Define file/resource model

- [ ] Status: planned
- Repos/files: QwQdoge/meo-ai meo/core-rs/src/blocks.rs, meo/core-rs/src/cloud/app.rs and meo/docs/projects-and-environments.md; QwQdoge/meo-api src/files.ts, migrations/ai/ and docs/api-reference.md.
- Work:
  - Separate Chat attachments, Project files, Work artifacts, local workspace files and plugin assets.
  - Define metadata, versioning, checksum, storage state, scope, retention and deletion.
  - Keep local workspace paths device-only and use opaque references in cloud state.
- Acceptance: every file has one owner and scope; Project/Chat cannot access another user's file by guessing an ID; no local workspace file is uploaded without explicit action.

### MEO-041 — Complete binary upload/download lifecycle

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/files.ts; storage adapter and src/types.ts; new migration if required; file route tests; docs/api-reference.md.
- Work: bounded binary upload, object storage write, checksum, download authorization, deletion, quota for binary + extracted text, safe extraction jobs and retryable orphan cleanup.
- Acceptance: upload/download/delete works for one supported type in offline fixtures; partial failures are recoverable; concurrent uploads cannot bypass quota.

### MEO-042 — Build file manager surfaces

- [ ] Status: planned
- Files: QwQdoge/meo-ai meo/core-rs/src/cloud/app.rs, meo/ui-schema/pages.json, meo/ui-schema/features.json and all three renderers.
- Work: Project files, Chat attachments and Work artifacts views with distinct actions; show origin, size, type, storage location, scope and permission; provide preview/download/delete/export states.
- Acceptance: local workspace files are never mixed with cloud files; unsupported actions are visibly unavailable instead of dead buttons.

## Priority 5 — architecture and repository cleanup

### MEO-050 — Split AppCore monolith by domain

- [ ] Status: planned; only after contract tests
- Files: meo/core-rs/src/cloud/app.rs; new sibling modules under meo/core-rs/src/cloud/; meo/core-rs/src/cloud/mod.rs; focused tests.
- Work:
  - Inventory state ownership and action IDs first.
  - Extract one bounded domain at a time (usage, providers, plugins, projects/files, settings).
  - Keep public protocol and serialized view snapshots unchanged.
  - Do not rename everything or format the whole file.
- Acceptance: each extraction is behavior-preserving and tested; no duplicate state registry or action dispatcher.

### MEO-051 — Label legacy and active source trees

- [ ] Status: planned
- Files: README.md; meo/README.md; docs/ownership.md; meo/docs/architecture.md; optional root LEGACY.md only if it improves discovery.
- Work: label root Newelle tree and paused Python/device compatibility directories; explain meo/cloud/ versus meo/core-rs/src/cloud/; mark old provider/MCP registries compatibility-only where appropriate; do not move/delete legacy source.
- Acceptance: new agents can identify the active path without guessing; packaging dependencies remain intact.

## Suggested execution order

Ordering rule: a live security or correctness defect comes before documentation, a small duplicate-ownership fix comes before a feature, and a contract comes before any client UI. Size is relative (S ≈ under an hour, M ≈ a day, L ≈ multi-day), not a promise.

| Phase | Tasks | Size | Why here |
| --- | --- | --- | --- |
| 0 — live security | MEO-002, then MEO-005 | S, S | Empty allowlist still reaches arbitrary public hosts with the user's key; the shadowed `/v1/storage` route is a same-file pair. Both are contained. |
| 1 — documentation | MEO-001, MEO-051 (labeling only), MEO-006 | S, S, S | Cheap, unblocks every later task with one consistent map. Pair with labeling `presentation-model-routing.md` as the paused AgentService path, since it is the source of stale routing claims. |
| 2 — abuse and cost control | MEO-003, MEO-003B | L | One authenticated account must not be able to exhaust provider spend across devices, IPs or parallel streams. |
| 3 — usage truth | MEO-010 → MEO-011 (split by provider family) → MEO-012 | L | Contract first, then adapters, then pricing. Do not let `credits.ts` grow a second cost ledger; extend its summary with vendor-estimate fields. |
| 4 — provider coverage | MEO-014 → MEO-011 (Anthropic usage slice) | M | Anthropic is part of the claimed official set; its usage must land in the same ledger. |
| 5 — visible product | MEO-020 (corrected scope), MEO-021 | M, M | The only phase a user sees; depends on the truthful router state and the connection contract. |
| 6 — files | MEO-004 → MEO-041 → MEO-007 → MEO-040 → MEO-042 | L | Lifecycle and deletion before any file-manager surface, so no screen claims what the API cannot do. |
| 7 — plugins | MEO-030, MEO-031 | M | Manifest and permission model before third-party code, which stays out of v1. |
| 8 — cleanup | MEO-050, MEO-051 remainder | L | Only after contract tests or view snapshots exist; never one giant rewrite. |

Not on the critical path:

- MEO-013 (provider billing reconciliation) is research-first and depends on optional vendor admin credentials. Timebox it as a spike; Meo must work without it.
- MEO-050 must not start until a characterization baseline exists. Capture golden view snapshots as its own small task first; `app.rs` is 23k lines, so a split without snapshots cannot prove behavior preservation.

This order fixes safety and correctness before adding more plugin features or polishing settings.

## Definition of done for every task

- [ ] Source of truth and ownership are clear.
- [ ] No second database or duplicated business logic was introduced.
- [ ] Authorization and data ownership are checked server-side.
- [ ] Error, unavailable, retry and cancellation behavior are defined.
- [ ] Focused tests/checks pass and are named in the task report.
- [ ] API/UI docs are updated.
- [ ] No secrets or user content were added to logs or commits.
- [ ] Rollback or safe-disable behavior is documented.
- [ ] Backlog status and next task are updated.
