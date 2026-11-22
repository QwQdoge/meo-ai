# Meo AI Implementation Backlog

Status: ordered planning list, 2026-11-22. Items are intentionally small. Do not execute the whole backlog in one agent run.

Latest source audit: [repository-audit-2026-11-22.md](repository-audit-2026-11-22.md). Read its verified findings before choosing a task.

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

- [ ] Status: planned
- Files: AGENTS.md; README.md; docs/ownership.md; meo/README.md; meo/docs/architecture.md; meo/docs/product-architecture-plan.md
- Work:
  - Make root AGENTS.md the contributor authority.
  - State that meo/core-rs/src/cloud/ is the active cloud-first AppCore.
  - Label meo/cloud/, meo/device/, meo/service/, meo/runtime/, meo/system/ and meo/adapters/ as compatibility/paused unless a newer owner decision changes this.
  - Correct the stale C++ desktop description to current meo/desktop-rs Rust + Qt/QML/MeoUI.
  - Keep Newelle provenance and migration gates.
- Acceptance: no document tells an agent to extend a paused stack as the primary path; one repository map is consistent.
- Check: documentation link/path check and focused grep for conflicting ownership phrases.

### MEO-002 — Harden custom provider endpoint policy

- [ ] Status: planned, security-sensitive
- Repo: QwQdoge/meo-api
- Files: src/ai-providers.ts; src/ai-broker.ts; src/types.ts; test/credentials.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md
- Work:
  - Make custom endpoint allowlisting fail closed when no approved hosts are configured.
  - Apply the same policy during save, edit, test, model discovery and inference.
  - Keep redirects disabled and review IPv4, IPv6, localhost, private, link-local, unusual ports, userinfo, query and fragment cases.
  - Review DNS rebinding and Worker outbound behavior; string checks alone are not full SSRF protection.
  - Return a clear endpoint-not-approved error.
- Acceptance: no custom endpoint can be saved or called unless its host is approved; no provider key reaches an unapproved destination; focused security tests pass.
- Dependencies: none. Complete before broadening custom endpoint UX.

### MEO-003 — Add account-level API spend and abuse limits

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/entry.ts; src/chat.ts; src/ai-broker.ts; src/credits.ts; src/types.ts; test/rate-limit.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md
- Work:
  - Keep IP limits, but add authenticated user + OAuth client limits.
  - Add request concurrency and rolling spend limits for inference, provider tests, uploads and connector calls.
  - Define limiter-failure policy per route; expensive operations must not silently become unlimited.
  - Return stable rate-limit/budget error codes with retry guidance.
  - Keep device credentials separate and rate-limit by device + account.
- Acceptance: users cannot bypass spend limits by switching IP/device; ordinary reads are not blocked by AI spend limits; tests cover cookie, bearer, multi-device and limiter-unavailable cases.

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

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/files.ts; src/credit-routes.ts; src/entry.ts; focused route tests; docs/api-reference.md
- Work:
  - Keep exactly one owner for GET /v1/storage.
  - entry.ts currently calls handleCreditRoute before handleFileRoute; verify the effective route and remove the shadowed duplicate implementation.
  - Keep storage quota, Meo Credits and upload-pause semantics in the Credit/Storage authority; file metadata endpoints must not maintain a second quota view.
- Acceptance: one route implementation owns /v1/storage; route tests prove the returned schema and authorization; no behavior change to storage billing.

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

- [ ] Status: planned
- Repos/files:
  - QwQdoge/meo-ai: meo/core-rs/src/cloud/usage.rs; meo/core-rs/src/cloud/usage_import.rs; focused Core tests.
  - QwQdoge/meo-api: migrations/ai/0003_usage.sql; src/chat.ts; src/ai-broker.ts; usage route tests; docs/api-reference.md.
- Work:
  - Define one versioned event with request ID, source, connection/provider/model, role, modality, exact token categories, duration and timestamps.
  - Add usage_source: provider_response, estimated, imported or unknown.
  - Preserve bounded safe provider usage metadata and source-event idempotency.
  - Never store prompts, response bodies, API keys or local paths in usage rows.
  - Keep imported Codex/Claude Code events distinct from Meo-generated events.
- Acceptance: every count has a declared source; duplicate ingestion does not double count; unknown counts are not fabricated as zero; fixtures cover supported provider formats.

### MEO-011 — Capture actual provider usage for supported adapters

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/ai-broker.ts; provider-specific usage normalizers; src/chat.ts; test/ai-endpoints.test.ts; provider fixtures under test/.
- Work:
  - Parse OpenAI Responses API, OpenAI Chat Completions, DeepSeek, Gemini and OpenRouter usage according to each provider's current documented response shape.
  - Do not assume one generic data.usage shape works for all.
  - Forward normalized usage in the stream completion event.
  - Persist usage through a server-owned path; do not trust the client to report cost.
  - When provider usage is omitted, mark estimated/unknown.
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

- [ ] Status: planned
- Repo: QwQdoge/meo-api
- Files: src/ai-providers.ts; src/ai-broker.ts; provider request/response adapters; src/model-capabilities.mjs; test/credentials.test.ts; test/ai-endpoints.test.ts; docs/api-reference.md.
- Work:
  - Add Anthropic Messages endpoint, headers, payload and streaming event parser.
  - Normalize model catalogue, tool calling, vision and usage only where supported.
  - Preserve Account credential encryption and consent flow.
  - Do not route Anthropic through a fake OpenAI-compatible adapter.
- Acceptance: save/test, discovery, consent, stream, cancellation, tool support and usage have fixtures; unsupported features are reported honestly.

## Priority 2 — model profiles and provider UX

### MEO-020 — Make Model Profile routing status truthful

- [ ] Status: planned
- Repos/files: QwQdoge/meo-api src/model-roles.mjs, src/ai-providers.ts and profile tests; QwQdoge/meo-ai meo/core-rs/src/cloud/app.rs, meo/docs/presentation-model-routing.md and view fixtures.
- Work:
  - Keep existing Account-owned ai_model_profiles schema and role catalogue.
  - Distinguish saved preference, active profile and runtime-supported routing.
  - Implement per-call role routing only when Core can invoke different models without mutating one global model setting.
  - Validate connection ownership, enabled state and model capability at save and use time.
- Acceptance: no role is shown as active routing if preference-only; concurrent requests cannot race by mutating global model selection; disabled connections show repair state, not silent substitution.

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

1. MEO-001 documentation reconciliation.
2. MEO-002 custom endpoint policy.
3. MEO-003 account-level rate/spend limits.
4. MEO-004 file object deletion lifecycle.
5. MEO-010 normalized usage contract.
6. MEO-011 real provider usage capture.
7. MEO-012 versioned price estimates.
8. MEO-014 Anthropic adapter.
9. MEO-013 optional provider billing reconciliation.
10. MEO-020 model profile runtime truthfulness.
11. MEO-021 provider settings UX.
12. MEO-030/031 plugin manifest and permission UX.
13. MEO-040/041/042 file manager.
14. MEO-050/051 cleanup and refactor.

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
