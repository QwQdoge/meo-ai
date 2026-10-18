# Meo AI — release gap audit and next implementation order
**Audit date:** 2026-10-18  
**Source:** current GitHub `main` of `meo-api`, `meo-ai-web`,
`meo-ai` and `MeoArch-account`; Cloudflare deployed Worker; Neon AI schema.
**Policy:** Web = React/TypeScript, desktops = C++/Qt Quick/MeoUI,
Android = Kotlin/Compose, common business contracts = Rust Core and Meo API.
Pixel-inspired UI must prioritize information, accessibility and useful features.
Code is merged directly into `main`; production promotion is separate.

## Current verified facts

- Latest available GitHub CI builds passed for Meo API, Meo AI native,
  Android, Rust Core and Meo Account, but these are **not** production E2E tests.
- Production `meo-api` Worker is still v53
  (`7300d520-c42b-45fc-b403-ee1df15a161a`). Its source map lacks the
  unified `/v1/chat/*` orchestration and cloud personalization routes.
- Neon AI production already has `ai_user_settings` and
  `ai_personal_memories`, but schema ledger currently reports **zero**
  `ai/0011_user_settings_personal_memory.sql` entries. Do not rerun
  destructive DDL or bypass the migration safety gate.
- `meo-api/docs/worker-v53-reconciliation.md` identifies six source
  differences, especially OAuth resource-token validation. A previous
  attempt to submit the OAuth fix was blocked by tool safety controls.
  **Do not bypass that restriction or deploy main until reviewed.**
- Web `MeoDesktopApp.tsx` still hardcodes Chat, Work, Projects and Skills
  navigation and renders Work/Projects/Skills as `ModeLanding` sections.
- The current remote `meo-ai/main` has no `meo/ui-schema/` directory,
  despite the planned shared navigation/schema generator.
- The cloud Project backend already provides project list, create, fetch,
  edit and project memory read/create routes. Web `meo-pages` now forwards
  bounded `/api/meo/projects/*` to those APIs; a full projects UI is not
  implemented by that proxy change.
- Account personalization interfaces exist in React, Kotlin/Compose and
  C++/MeoUI, but have not been validated as a three-device signed-in flow.

## P0 — release safety (complete **before** production API promotion)

- [ ] **Strict OAuth resource-token validation** across account, AI Broker,
  and account-scoped Chat/Memory/Project routes. Verify signature, issuer,
  audience, expiry, scopes, account identity, bans/deletions and activation;
  support signed OAuth tokens without browser session `sid`. Never replace
  this with unverified UserInfo-provided scopes.
- [ ] **Build and test authenticated Chat** with two test accounts and an
  intentionally limited OAuth client. Cover wrong audience, expiry, insufficient
  scope, revoked/suspended account, missing session ID and cross-user access.
- [ ] **Match v53 production source** including authentication and stream
  behavior before controlled promotion; capture and retain rollback version.
  Do not overwrite v53 with an unverified dry-run bundle.
- [ ] **Staged deploy** unified `/v1/chat/prepare`, `/v1/chat/stream`,
  `/v1/ai/settings`, `/v1/ai/memories` and account-scoped conversation and
  project routes. Verify readiness and live provider streaming on each stage.
- [ ] **Cross-device acceptance**: sign in, create a chat, approve sending,
  generate real reply, refresh and restore history; edit instructions,
  disable/archive a memory, and confirm Web/Android/native reflect changes
  and the next model request excludes disabled data.
- [ ] Reconcile already-applied AI `0011` schema migration with
  `meo_schema_migrations` via approved migration workflow.

**P0 exit:** No user data leaks, no consent mismatch, no sign-out loops;
one reproducible signed-in end-to-end demo with rollback instructions.

## P1 — functional product, not placeholders

- [ ] **Shared UI contract and generator:** a versioned canonical schema for
  navigation, groups, order, icons, feature availability, routes and design
  tokens. Generate typed React/Kotlin/QML/C++ consumers. One `placement`
  or `order` edit must be proven to move Work consistently on all three
  platforms. Native layout remains native, not Flutter.
- [ ] **Real Projects:** list/create/rename/select; project instructions,
  chat membership, files and bounded project memory; empty/loading/error and
  permission states. Consume the existing server Project API.
- [ ] **Work:** actual job creation, status, progress, cancellation,
  interrupted-run recovery and policy-gated tool execution. A Work job must
  continue on the server after the Web tab closes where allowed, with
  idempotent recovery and audit; never simulate progress in UI.
- [ ] **Complete settings:** General, Appearance, Personalization, Memory,
  Models, Tools & MCP, Privacy & Data, Account & Security. Every visible
  action must map to a real persisted local/cloud operation or explicitly
  state that the capability is unavailable. Do not expose dead controls.
- [ ] **Skills and tools:** discoverability, detail, per-tool permissions,
  safe disable/revoke, execution status and error handling. No arbitrary
  unrestricted backend endpoint in the client.
- [ ] **Chat durability:** establish one server-owned turn lifecycle
  (pending/committed/failed/cancelled) and idempotent user/assistant message
  persistence so partial streams, retries, refresh and disconnects cannot
  duplicate or lose a turn. Today Web and Android both append messages from
  their clients after streaming; this is a remaining consistency risk.
- [ ] **Rich content:** stable Markdown, code, math, images, tables, charts,
  file previews and selectable/copyable text across native and Web renderers.
  Validate long messages and streaming performance on a real Android phone
  and Linux desktop.

## P2 — distribution and polishing

- [ ] Native Windows and macOS C++ packaging, updater/signing and
  platform-specific Account broker integration. Existing Linux CI is not
  proof of Windows/macOS readiness.
- [ ] Responsive behavior on desktop, mobile browser and foldable/tablet;
  keyboard, screen reader, reduced motion and localization tests.
- [ ] Coherent MeoUI design tokens/Pixel-inspired visual density, consistent
  empty states, error feedback and reliable navigation.
- [ ] Product analytics and privacy controls using no hidden credential
  telemetry; crash reports must redact personal content.

## Suggested next change set

1. Finish security-reviewed OAuth code and tests; this blocks safe deployment.
2. Deploy unified API in a controlled stage and run signed-in two-user smoke
   tests with rollback preserved.
3. Implement shared schema + generator, then wire Web navigation and
   native counterparts; prove the Work placement change.
4. Convert Projects landing page to functional API-backed UI.
5. Implement background Work lifecycle and turn persistence, then enable the
   Work UI.
6. Expand functional Settings and rich content parity after core paths are
   stable.

**Near-term delivery rule:** prefer a reliable Chat/Settings/History demo
over shipping new placeholder modules merely to make menus look complete.
