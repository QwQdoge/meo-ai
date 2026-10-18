# Meo AI cloud personalization — integration status (2026-10-18)

## Architecture decision

- Web: React + TypeScript; native Linux/Windows/macOS: C++/Qt Quick/MeoUI;
  Android: Kotlin + Jetpack Compose.
- Common account behavior is specified by Meo API wire contracts and Rust
  models, **not** a shared Flutter/WebView renderer.
- UI navigation and MeoUI design tokens remain separate from user data;
  do not confuse product layout schema with cloud account preferences.

## Shipped to GitHub main (source)

| Layer | Implemented | Remaining validation |
| --- | --- | --- |
| Meo API | Versioned account settings + personal memory endpoints; context and consent categories | Reconcile and deploy over production Worker v53 safely |
| Neon AI | Production 0011 created settings and memory tables; limited-role grants verified | Migration ledger marker requires controlled migration-manager reconciliation |
| Web | Typed API adapter; functional Personalization/Memory editor; responsive sidebar; Pages CI | Signed-in E2E test against deployed unified API |
| Android | Native Compose account settings and memory UI, Kotlin API adapter, shared Chat orchestration | Release build and real-device account/login/sync tests |
| Rust Core | Shared serializable settings and memory contract | Use types in desktop bridge and end-to-end cloud transport |
| Desktop Qt/MeoUI | C++ `CloudPersonalizationBackend` and native `CloudPersonalizationPage`; Meo Account's bounded `StartAiPersonalizationOperation` D-Bus broker; device memory remains separate | Desktop native build and signed-in request/refresh/permission tests |

## Desktop bridge implemented (source, not production-proven)

- `MeoArch-account/desktop/src/aipersonalizationroute.h` restricts callers to
  fixed settings/memory methods, typed arguments, scoped read/write permissions,
  size and version constraints. Client-supplied URLs and tokens are forbidden.
- `AccountBroker::StartAiPersonalizationOperation` verifies the native
  `org.meo.MeoAI` caller executable and manifest's `ai_personalization`
  capability. OAuth access tokens remain inside Meo Account/KWallet. The
  request result includes private data only via owner-checked `GetRequest`,
  never via the public D-Bus completion signal.
- `CloudPersonalizationBackend` exposes native Qt/QML-safe state and actions
  for a dedicated MeoUI cloud settings page, separate from on-device memory.
- Edited instructions and toggles are not overwritten by intermediate
  request signals. Optimistic-concurrency conflicts and authorization failures
  have actionable UI messages.
- Cloud memory mutations are not usable in production until the reconciled
  Worker with `/v1/ai/*` support is deployed. Broker tests cover route
  validation; desktop build and full OAuth, D-Bus caller isolation and
  cross-user tests remain release gates.
- OS-specific token refresh, broker restart, expired credentials, concurrent
  edit conflicts, multiple-user isolation and AppImage/packaging path parity
  must be validated on real Linux installations.

## Release gates

- Cloudflare live `meo-api` was confirmed as Worker v53; checked source
  bundle does not visibly contain the new settings/memory schema.
- Production 0011 schema exists but **new routes are not deployed**.
- GitHub main and deployed v53 authentication, streaming and OAuth patches
  must be reconciled before a Worker rollout; preserve full rollback.
- Do not mark P0 complete before signed-in Web and Android produce a real
  reply with memory and demonstrate restored history.
