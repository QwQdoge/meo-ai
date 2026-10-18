# Meo AI Web integration contract

## Source and authority

The product source is now `meo-ai/meo/web/client`. The import originates from
`QwQdoge/meo-ai-web` at `ae796b230ec17d65ab298523d9c1dd59cf714bb7`, with the
local Chat-context proxy repair included. File hashes and MIT attribution are
preserved in `client/import-manifest.json` and `client/LICENSE.librechat`.
The original LibreChat upstream lineage remains in the source repository and
its `UPSTREAM.md`; that backend is not required by this standalone React build.

The production Pages deployment remains on its existing source until explicitly
cut over. Do not delete or repurpose the old repository as part of this import.

Meo Account owns identity/session/OAuth and encrypted provider credentials.
Meo API owns actor-scoped data, Chat orchestration, context, consent/broker and
cloud tasks. Shared Meo AI behavior is developed in Rust Core; UI code only
renders shared state and uses platform adapters.

## Browser transport

The browser calls same-origin Pages Functions:

| Browser request | Upstream authority |
| --- | --- |
| `/oauth/openid` and callback | Account OAuth/OIDC PKCE |
| `/api/meo/session` | Encrypted HttpOnly browser session and Account UserInfo |
| `/api/meo/connections` and model discovery | Meo API provider broker |
| `/api/meo/conversations` and messages | Meo API conversation routes |
| `/api/meo/chat/prepare` and `/stream` | Meo API `/v1/chat/*` |

Chat forwards `credentialId`, `model`, optional `conversationId`, `prompt` and
consent unchanged. Context selection and provider request assembly do not live
in the edge. Do not revert to a direct inference-broker translation that drops
conversation identity.

Access/refresh tokens remain in encrypted `Secure`/`HttpOnly` cookies and on the
edge. Provider keys remain server-owned. No token, API key or secret is accepted
in query parameters or frontend storage. An upstream API 401 must not erase an
otherwise valid browser session.

The edge preserves incremental response bodies and cancellation signals.
Production provider cancellation, real Account login/refresh and saved history
still require separate end-to-end acceptance; mocked transport tests are not
proof of those behaviors. React's imported Chat still performs message writes
separately from inference; it is not a durable background AgentRun.

## Shared settings integration

The first new settings/memory domain API is implemented by the Rust loopback
Core for isolated candidate validation. The authenticated cloud API must adopt
that same domain contract with actor-scoped persistence before Web/Android can
claim account-wide settings or memory synchronization. The production BFF does
not forward unimplemented cloud settings routes, and never silently falls back
to loopback or localStorage.

Schema definitions, capability availability and server permissions are different
things. Do not treat a declared page or a successful local save as cross-platform
feature completion.
