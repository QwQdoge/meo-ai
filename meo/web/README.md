# Meo AI web

`meo/web/` owns the browser-facing Meo AI product integration. The first web
implementation uses LibreChat in the separate `QwQdoge/meo-ai-web` fork. The
pinned upstream commit, MIT attribution, patch surface and upgrade procedure are
recorded in [`integration-contract.md`](integration-contract.md). The large
LibreChat tree remains outside this Newelle-derived migration repository.

## First-version behavior

- Meo Account OIDC login through LibreChat's existing OpenID Connect support.
- Provider connection and model selection from Account metadata.
- Model ID manual fallback when a provider cannot list models.
- Text chat with Markdown/code rendering, responsive layout and Meo Cloud
  conversation history shared across devices for the same Meo Account identity.
- Account's payload-bound consent preview before every provider invocation.
- An authenticated same-origin adapter that forwards only the server-side
  Account session to `ai-provider-broker`; browser code sees credential IDs,
  masked metadata and chat text, never provider keys or Account access tokens.
- True OpenAI-compatible provider SSE through the Account broker. Disconnects
  abort the upstream provider request.

`meo/cloud/` conversation and message routes use the verified Account user as
the owner. `localStorage` stores only the active conversation pointer, never
canonical history. AgentRun cards and controls remain a later integration;
ordinary text chat does not depend on the AgentRun service.

## Roadmap beyond the first version

- Files and attachments where the Meo AI API supports them.
- Remote AgentRun cards with progress, cancellation and approval controls.
- Direct transport between Web and the AgentRun event API. The Web must not
  connect to local AgentService loopback endpoints.

## Integration policy

Do not vendor the LibreChat tree into `meo-ai`. Meo-specific behavior belongs in
this contract or the separately maintained `meo-ai-web` fork. Keep patches
small and run the fork's upgrade checks against the exact pushed commit.

## Runtime acceptance

Sign in with Meo Account, verify that `/new` accepts an owned connection/model,
send one consented provider request, reload and restore the conversation, then
open the same account in another browser and confirm it sees the same history.
Production acceptance also needs a working `chat.meoarch.org` DNS and Meo Cloud
conversation API. Local tests do not prove those external services.

## AgentRun event transport

Configure `MeoAgentClient.eventsUrl` as the cloud origin plus
`/v1/agent-runs/events`. The authenticated SSE endpoint takes `run_id` and
`after` (default `-1`); SSE IDs are the persisted per-run event sequence starting
at zero. Reads are scoped to the verified account and run owner. A stream can
close after 60 seconds; reopen `events(runId, lastEventId)` to continue the same
run, without calling `createRun` again. Cursor gaps surface an error instead of
silently skipping work. Closing a subscriber does not stop the AgentRun.

For offline network acceptance, install `meo/cloud/requirements.txt` and use
Node 24+, then run from the repository root:

```sh
MEO_AI_RUN_CLOUD_NETWORK_TEST=1 python3 -B -m unittest discover -s meo/tests -p test_cloud_network_integration.py -v
```

This exercises the production client and HTTP/WebSocket transport with test AI,
identity verification and storage. It does not prove browser OAuth, production
database access or provider execution.
