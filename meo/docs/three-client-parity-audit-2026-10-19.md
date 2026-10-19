# Three-client feature parity audit — 2026-10-19

Scope: `meo-ai/main` at `db553f1fa1216cdf59dead1d3e82119ccca6ee49`, plus this PR's Projects changes. Source inspection only; **not** proof of production endpoint availability, live OAuth, desktop-to-cloud synchronization, on-device permissions, or physical Android/browser acceptance.

Web means `meo/web/client` React, Desktop means `meo/app` C++/QML + MeoUI, Android means `meo/android` Compose. Product entry identities are owned by `meo/ui-schema/navigation.json`; settings labels/order/search metadata by `meo/ui-schema/settings.json`. Each renderer must still connect actual APIs/capabilities. Legend: **Implemented** means a corresponding code path exists; **Partial** means it lacks required workflows; **Unavailable** means a placeholder or no binding exists. None of these words imply a deployed or end-to-end verified release.

| Feature | Web | Desktop | Android | Unresolved parity / authority |
|---|---|---|---|---|
| Account sign-in | Browser OIDC/session implementation | Account broker `RequestAuthentication(connect_system)`; launches normal browser as needed | OAuth PKCE + secure session store, browser authorization | Live three-device browser-return/sign-out/revoke test; non-Linux broker availability |
| Guest/local mode | No: web requires session | Local AgentService and local settings may be used without Account | Guest *settings* page only; Chat uses Account | Avoid fake offline model for browser/Android |
| Chat, model selection & streaming | Meo API chat prepare/stream and provider broker metadata | Local AgentService and Meo Account broker integration | Meo API conversation/model/stream + consent | Server-owned turn durability; recover partial streams and retry without duplicate messages |
| Conversation history | Account API history/search, local draft cache | Local native history/search/rename/delete/Markdown export | Account history list/read | Native cloud ID mapping; consistent rename/export and multi-device resumption |
| Work/AgentRun | Account-authenticated remote AgentRun, SSE reconnect/cancel/decisions | Local AgentService + native approvals and runtime controls | Drawer entry, no full Work controller | Android remote Work, target device selection, durable cloud run ownership and recovery |
| Projects | **This PR:** cloud list/create/select/rename via authorized API | Device-local list/create/select/**rename in this PR** | **This PR:** account list/create/select/rename | Cloud ↔ local opt-in migration with identity mapping; instructions/files/chat membership/project memory |
| Skills / plugins / MCP | Account plugins+Skills CRUD, catalog discovery and reviewed grants; remote execution by API where configured | Local Skills/MCP runtime views and configuration | Account metadata + read grants; no Android MCP execution | Brokered capability model, enable/revoke parity, no prompt-based authority |
| Personalization & saved memories | UI for account scope; API adapter can report unavailable | Local memory and separate cloud personalization view | Account settings/memory CRUD | Verify same live endpoint contract and actor ownership on all three; archived/disabled data excluded from inference |
| Models / credentials | Account broker connections and models | Account D-Bus metadata, selected local model routing | Account list + models via OAuth | Account key vault only; no raw key replication or client-side secret stores |
| General appearance / keyboard | Browser-local theme, motion, Enter | Local persistent theme, motion, Enter | Local device theme, motion, keyboard | Add per-platform acceptance for system theme and IME, avoid syncing device-specific defaults blindly |
| App/connection management | Account plugin UI in Settings/Skills | Native local MCP and Account metadata | Account plugin inventory only | Distinguish configuration sync from executable local runtime availability |
| Attachments and artifacts | Markdown/code/table render and local export; full file upload not tied to inference | Native local file/response content paths | Native rich block rendering | Typed upload/extraction, file rights, binary storage, artifact lifecycle |
| Data & privacy, usage | Account links and unavailable states | Local diagnostics/activity, account site for security | Account link and feature-unavailable states | Consistent export/delete, actor-bound usage and privacy controls; show truthful unsupported states |
| Settings discoverability | Eight schema groups + search | Eight schema groups + search | Eight schema groups + search | One shared catalog, but **new logic is not auto-implemented in every renderer** |

## User-requested parity policy

1. Implement one **versioned Core/API feature contract** per operation, and one shared UI Schema entry for naming, categorization and discovery. Never maintain three independent product feature lists.
2. Each native adapter calls the owning capability; feature presence does not prove its runtime availability. No fake buttons, silent local fallbacks or implicit remote work.
3. Meo Account is optional for **local-capable apps**. Login begins inside Meo AI and uses the system browser for OAuth; credentials/session renewal remain with Account and platform secure stores. Web remains signed-in cloud client.
4. User-managed local projects/workspaces/memories are **not** uploaded on account login, or inferred equivalent to cloud objects. Migration requires preview, opt-in, mapping, retries and conflict handling.
5. Require Web+Qt+Android tests and real device/live environment checks before declaring three-way parity. Build CI passing is necessary but insufficient.

## P0 blockers before production promotion

- Account resource-token verification/ownership, existing production v53 API reconciliation and safe deployment; see `release-gap-audit-2026-10-18.md`.
- No verified public deployment of the Project API, settings and memory routes. UI must surface unavailable/network/errors rather than report saved state.
- Server-owned Chat request/turn commit and idempotent SSE reconnect; cross-account ownership tests and 3-device OAuth test.

## Next implementation order

1. **Projects Phase 2:** cloud project detail/instructions/memory and explicit conversation membership; native project cloud view **separate from local**, opt-in migration proposal, Web/Android state refresh and optimistic conflict strategy.
2. **Work Phase 2:** Android authenticated target/workspace selection and AgentRun event/approval UI; consistent native/cloud run IDs, replay/stop semantics; do not start another AgentService on reconnect.
3. **Skills/MCP Phase 2:** expand Android metadata to safe account-managed enable/revoke controls, align desktop local and cloud collections without copying machine-specific execution configs.
4. **Chat Phase 2:** common server-owned lifecycle, user/assistant persistence, retry and history actions, then files/artifacts pipeline.
5. **Settings Phase 2:** fully bound privacy/usage/device/account detail pages on each platform, revision conflict handling, explicit sync scope and diagnostics, then real multi-device acceptance.

### Acceptance checklist for this Projects change

- Web BFF permits only GET/POST `/projects`, GET/PATCH valid UUID `/projects/:id`, GET/POST `/projects/:id/memories`, and never proxies arbitrary paths or deletion; authenticated same-origin forwarding remains mandatory.
- Web and Android share Meo API account-scoped project list/create/rename. Android uses its existing secure OAuth session; no raw access token reaches a Composable.
- Qt desktop stores renamed local project with QSettings; rejects empty/unknown IDs, emits change signals and retains active-project semantics after reload. No silent account upload.
- Web client tests/typecheck/build, shared Schema generation, Android assemble, Qt CMake/CTest and real-device OAuth return must be reported **separately**.
