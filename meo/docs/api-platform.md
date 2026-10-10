# Meo AI API Platform

Status: source-of-truth design for the unified Web, Native, Cloud and Device API surface.

## Goal

Meo AI should present one product surface while keeping security authorities separated:

- Meo Account owns identity, sessions and encrypted provider credentials.
- Meo AI owns conversations, model selection, agent orchestration, device routing and product UX.
- Local AgentService owns execution lifecycle on a device.
- System AI Router and application/system owners keep privileged system authority.

A client must never receive a provider API key merely because it can use a provider.

## API layers

### 1. Meo Account / OIDC

Used by Web and Native clients for identity.

Required OIDC properties:

- Authorization Code + PKCE for public clients.
- `openid email profile` baseline scopes.
- exact registered redirect URIs.
- server-side validation of issuer, audience, expiry and session identity.

LibreChat is configured as an OpenID client and does not own a second user password database for Meo deployments.

### 2. Meo Account AI Provider Broker

Existing authority for BYOK provider credentials.

The broker owns:

- encrypted credential storage;
- provider endpoint allowlisting;
- key decryption only inside the broker;
- provider request execution;
- provider consent/audit records;
- model/provider metadata returned without secrets.

Meo AI sends credential IDs and grants, not API keys.

Target provider families:

- OpenAI;
- Anthropic through an Account adapter when added;
- Gemini;
- DeepSeek;
- OpenRouter;
- OpenAI-compatible endpoints approved by deployment policy;
- local providers remain device-owned rather than routed through the cloud broker.

### 3. Meo AI Cloud API

The Cloud API is the product API shared by Web and Native clients.

Suggested version prefix:

`/v1`

#### Identity

All user endpoints require a valid Meo Account access token. The API derives `user_id` from the token and never accepts an authoritative user ID from request JSON.

#### Conversations

- `GET /v1/conversations`
- `POST /v1/conversations`
- `GET /v1/conversations/{conversation_id}`
- `PATCH /v1/conversations/{conversation_id}`
- `DELETE /v1/conversations/{conversation_id}`
- `GET /v1/conversations/{conversation_id}/messages`
- `POST /v1/conversations/{conversation_id}/messages`

Message creation contains client intent and content. The server owns final message IDs and ordering.

Messages should record the executor separately from visible role, for example:

- provider/model response;
- local AgentRun;
- remote AgentRun;
- system-generated status.

#### Providers and models

- `GET /v1/providers`
- `GET /v1/models`
- `POST /v1/model-selection`

Cloud provider entries are derived from Account credential metadata. Local model entries are derived from online device capability catalogs.

The UI may present both in one model selector while preserving execution location metadata.

#### Chat grants

- `GET /v1/chat-grants`
- `POST /v1/chat-grants/prepare`
- `POST /v1/chat-grants/{grant_id}/approve`
- `DELETE /v1/chat-grants/{grant_id}`

Modes:

- `ask_every_time`: no reusable grant is created;
- `session`: expires automatically and is the recommended default;
- `persistent`: remains valid until revoked or policy changes.

A grant binds at least:

- user identity;
- Meo AI client identity;
- Account credential ID;
- permitted data categories;
- issue/expiry/revocation state.

Changing provider credential, client identity or requested data category requires a new authorization decision.

#### Inference

Preferred product API:

- `POST /v1/conversations/{conversation_id}/responses`
- streaming response over SSE initially; WebSocket may be added only where bidirectional semantics are required.

Request example:

```json
{
  "model": "provider/model",
  "credential_id": "...",
  "grant_id": "...",
  "content": [{"type": "text", "text": "Hello"}],
  "attachments": [],
  "mode": "chat"
}
```

The Cloud API validates conversation ownership and grant scope, then asks the Account broker to perform provider inference. It persists user/assistant messages in Meo AI storage, not in Account credential storage.

#### Devices

- `GET /v1/devices`
- `GET /v1/devices/{device_id}`
- `GET /v1/devices/{device_id}/capabilities`
- `GET /v1/projects`
- `PUT /v1/projects/{project_id}/locations/{device_id}`

Clients can see device metadata but cannot directly connect to arbitrary local ports.

#### AgentRuns

- `POST /v1/agent-runs`
- `GET /v1/agent-runs/{run_id}`
- `GET /v1/agent-runs/{run_id}/events?after=<seq>`
- `POST /v1/agent-runs/{run_id}/cancel`
- `POST /v1/agent-runs/{run_id}/decisions/{decision_id}`

Cloud AgentRun state mirrors, but does not replace, the local AgentService request state.

One cloud AgentRun may bind to exactly one local AgentService request ID. Reconnect resumes that binding; it must not silently create a replacement request and replay side effects.

### 4. Device Relay API

`meo-agentd` keeps an outbound authenticated connection to the Meo service.

Initial protocol can use WebSocket because the connection is bidirectional and long-lived.

Device -> Cloud messages:

- register/refresh capabilities;
- heartbeat;
- AgentRun accepted/rejected;
- local request binding;
- ordered AgentService events;
- approval requests;
- completion/failure/cancellation.

Cloud -> Device messages:

- dispatch AgentRun;
- cancel existing run;
- submit explicit decision;
- request replay after a known event sequence;
- refresh capability catalog.

Every message carries protocol version, device identity and run identity where applicable.

The relay never accepts an arbitrary shell command as its transport contract. Remote execution enters through an AgentRun/workspace/capability contract and is still constrained by local policy.

### 5. Local AgentService API

Existing loopback HTTP/SSE API remains the first local execution target. It already owns conversation/request/decision IDs and cancellation semantics.

`meo-agentd` acts as a transport bridge to this existing service rather than duplicating the agent engine.

Future local IPC may move from loopback HTTP to a stronger local boundary without changing the Cloud AgentRun contract.

## Streaming

Use SSE for provider and AgentService output where the client only needs server-to-client ordered events.

Use WebSocket for device relay because Cloud also sends dispatch/cancel/decision messages to the device.

Every stream event should include a monotonically increasing sequence number. Clients resume with the last accepted sequence and ignore stale/duplicate events.

## Idempotency

Mutating cloud APIs should accept an idempotency/request key where retries can happen across network failures.

Especially protect:

- message submission;
- AgentRun creation;
- approval decisions;
- provider invocation;
- cancellation.

A network retry must never imply executing a second tool/system effect.

## Error model

Public APIs should use stable machine-readable error codes and safe user messages. Raw provider errors, stack traces, request bodies, credentials and local filesystem details are not public API responses.

Suggested shape:

```json
{
  "error": {
    "code": "grant_expired",
    "message": "This AI connection needs permission again.",
    "request_id": "..."
  }
}
```

## Versioning

- HTTP API: `/v1/...`
- device relay envelope: `protocol_version`
- persistent grant schema: explicit schema version
- AgentRun event schema: explicit event type + version when the payload changes incompatibly

Do not make LibreChat-specific database structures the Meo public API. LibreChat is a Web client implementation, not the authority for Meo protocol contracts.
