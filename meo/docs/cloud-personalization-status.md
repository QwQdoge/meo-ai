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
| Desktop Qt/MeoUI | Existing device-local memory preserved and clearly labeled | Secure account-scoped API transport and native cloud settings page |

## Desktop authorization blocker

The existing Meo Account desktop D-Bus interface uses an account-owned broker,
but **does not expose a safe Meo AI cloud settings request operation**.
Meo AI must not read Account's encrypted token store, leak bearer tokens to QML,
use an arbitrary inherited cookie, or bypass Account permission checks.

Preferred implementation:
1. Add a Meo Account broker operation for fixed-method, fixed-path
   `/v1/ai/settings` and `/v1/ai/memories` requests, bound to the authorized
   `org.meo.MeoAI` client and read/write scope.
2. Keep OAuth access and refresh tokens *inside* the Account broker.
3. Return only validated JSON data or structured errors over D-Bus.
4. Expose a C++ QObject adapter to QML, rendering native MeoUI controls.
5. Validate with two OS users, expired tokens, unauthorized callers,
   concurrent version conflicts, broker disconnect and service restart.

Do not infer cloud sync from the existing AgentService `memories` controls:
those are **on-device** memories and have different lifecycle and authority.

## Release gates

- Cloudflare live `meo-api` was confirmed as Worker v53; checked source
  bundle does not visibly contain the new settings/memory schema.
- Production 0011 schema exists but **new routes are not deployed**.
- GitHub main and deployed v53 authentication, streaming and OAuth patches
  must be reconciled before a Worker rollout; preserve full rollback.
- Do not mark P0 complete before signed-in Web and Android produce a real
  reply with memory and demonstrate restored history.
