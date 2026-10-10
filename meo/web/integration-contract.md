# Meo AI Web integration contract

## Authority

Meo Account owns authentication/session identity and BYOK credential metadata,
encrypted provider keys, model discovery, endpoint validation and provider
execution. Meo AI Cloud owns conversation/message and AgentRun state. The Web
owns browser UI and calls both services through its authenticated same-origin
server adapter. The browser receives credential IDs and masked metadata only;
provider keys never enter the browser, Account access tokens stay server-side,
and neither appears in URLs, local storage or Mongo configuration.

## Account broker calls

The LibreChat API adapter forwards the authenticated server-side OIDC access
token to `POST {MEO_ACCOUNT_URL}/functions/v1/ai-provider-broker` with
`redirect: error` and `Cache-Control: no-store` handling.

- `list_credentials` returns enabled connection metadata.
- `list_models` returns normalized model IDs/metadata. `supported: false` means
  the UI must accept a manually entered model ID.
- `prepare_inference` returns a five-minute, payload-bound consent preview.
- `stream_invoke` includes only the approved request ID, payload hash and
  confirmation version. OpenAI-compatible providers stream `stream: true` SSE
  through Account; the broker normalizes text deltas and aborts its provider
  fetch when the downstream request is cancelled. Provider keys remain inside
  the broker. Buffered `invoke` remains available to other Account clients.

Chat purpose is `meo_ai_web_chat`. Categories are `chat_text` and, when history
is attached, `conversation_context`. The Account broker validates the complete
payload again at invocation time. No client supplied endpoint is accepted.

## Web routes and SSE

The authenticated same-origin adapter exposes:

```text
GET  /api/meo/connections
GET  /api/meo/connections/:credentialId/models
GET  /api/meo/conversations
POST /api/meo/conversations
GET  /api/meo/conversations/:conversationId/messages
POST /api/meo/conversations/:conversationId/messages
POST /api/meo/chat/prepare
POST /api/meo/chat/stream
```

`/chat/prepare` accepts a credential ID, model ID and bounded user/assistant
messages, then returns the Account consent summary. `/chat/stream` repeats that
payload with the approved consent fields and forwards provider-backed
`event: delta`, `event: done` and sanitized `event: error` SSE events. Disconnects
propagate to the Account broker and provider request; no response is buffered
before the first token.

The deep link is `/new?connection=<credential-id>&model=<model-id>`. Query
parameters are allowlisted to those two identifiers. No token or secret appears
in a URL. LibreChat's same-origin session must already be authenticated through
Meo Account OIDC.

## Conversation and future cloud boundary

Conversation history uses Meo Cloud `conversations` and `messages`, with the
Account verified user ID as owner. The server adapter forwards the Account
session only to the cloud service; every read and write is owner-scoped. New
conversations and user/assistant messages are persisted remotely, so refreshes
and another browser using the same Account see the same history. `localStorage`
contains only the selected conversation pointer. The separate AgentRun client
remains an integration seam for a later feature and resumes event streams by
`run_id` and cursor; ordinary text chat does not wait for AgentRun.

## Upstream pin and maintenance

This integration branch is based on LibreChat fork `origin/dev` commit
`4afd5e17f85e95d610e606c0cdfddf3b2ba97978` (`Keep Quiet Chat Streams Alive
Behind Idle-Timeout Proxies`, PR #16904). The product evaluation in `meo-ai`
recorded `e1dfc10449ff713faffacd60273fddcfe2c0a698` from upstream `main`; the
actual fork checkout was created from the newer `dev` snapshot, so upgrades
must record and compare against the pinned `dev` ancestor. LibreChat is
MIT-licensed; retain the upstream `LICENSE`, copyright notices and license text
in every release.

Meo patch surface:

1. `packages/api/src/meo/accountProviderClient.ts` contains the broker client and
   request validation.
2. `api/server/routes/meo.js` and two route registrations expose the authenticated
   same-origin API.
3. `client/src/components/Meo/MeoChat.tsx` and two React route entries provide
   provider/model selection, consent, chat and the deep link.
4. `meo/` contains environment/configuration and this contract.

For upgrades, fetch the `upstream` remote, review security and auth changes,
merge upstream into the Meo branch, reapply only this listed surface, run the
focused Meo adapter tests, API TypeScript check and client typecheck/build, then
review dependency and MIT attribution changes. Do not vendor a second LibreChat
tree into `meo-ai`.
