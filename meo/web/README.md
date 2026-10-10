# Meo AI web

`meo/web/` owns the browser-facing Meo AI product integration.

The first implementation should reuse a mature open-source chat frontend instead of rebuilding chat UI primitives. The preferred evaluation target is LibreChat because its MIT license is straightforward for a personal fork/integration, but this directory is deliberately frontend-agnostic until an exact upstream commit and integration method are selected.

## Requirements

The web client must support:

- Meo Account authentication;
- normal streaming chat;
- model/provider selection without exposing provider secrets;
- cross-device conversation history;
- files/attachments where supported by the Meo AI API;
- first-class remote AgentRun cards with progress, cancel and approval actions;
- responsive desktop/mobile browser use;
- no direct access to local AgentService loopback endpoints.

## Integration policy

Do not copy a large upstream frontend into this directory without recording:

1. upstream repository and exact commit/tag;
2. license and attribution requirements;
3. whether integration is a fork, subtree, submodule, packaged dependency or API-only deployment;
4. a clear patch policy so upstream updates remain possible.

Meo-specific product logic should stay behind stable APIs where possible. Styling/branding patches are acceptable, but a deep fork that makes upstream security updates difficult is not the default plan.

## First acceptance

A browser session should be able to sign in with Meo Account, create a conversation, send a message through one configured provider, reload the page, and recover the same conversation.

## AgentRun event transport

Configure `MeoAgentClient.eventsUrl` as the cloud origin plus
`/v1/agent-runs/events`. The authenticated SSE endpoint takes `run_id` and
`after` (default `-1`); SSE IDs are the persisted per-run event sequence starting
at zero. Reads are scoped to the verified account and the run owner. A stream
can close after 60 seconds; reopen `events(runId, lastEventId)` to continue the
same run, without calling `createRun` again. Cursor gaps surface an error instead
of silently skipping work. Closing a subscriber does not stop the AgentRun.

For offline network acceptance, install `meo/cloud/requirements.txt` and use
Node 24+, then run from the repository root:

```sh
MEO_AI_RUN_CLOUD_NETWORK_TEST=1 python3 -B -m unittest discover -s meo/tests -p test_cloud_network_integration.py -v
```

This runs the production client and HTTP/WebSocket transport with test AI,
identity verification and storage. It does not prove browser OAuth, production
database access or provider execution.
