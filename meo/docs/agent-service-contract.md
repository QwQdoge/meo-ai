# Meo AgentService contract

Status: Phase B contract. This document defines the stable frontend/runtime boundary before GTK removal.

## Boundary

`Meo AI` is the Qt/QML frontend. `AgentService` owns the Newelle-derived agent runtime and runs as an unprivileged user service. The service does not gain OS authority from prompts, Skills, MCP descriptions, model output or frontend requests.

The current implementation uses loopback HTTP/SSE as a transport, but HTTP is not the product contract. A later D-Bus or other local transport must preserve conversation identity, request identity, decision identity, event ordering, reconnect semantics and cancellation semantics.

`AgentServiceCore` consumes a narrow `AgentBackendAdapter`. The service layer and adapter contract must remain importable without GTK/Adwaita/WebKit or Newelle UI modules. A compatibility adapter may still wrap the current GTK-era Newelle controller during extraction; that adapter is the temporary seam, not part of the stable frontend contract.

## Request identity and lifecycle

Every submitted turn receives a service-generated `request_id`. One request follows this state model:

- `queued`
- `running_model`
- `awaiting_tool`
- `running_tool`
- `cancel_requested`
- `cancelled`
- `completed`
- `failed`

Terminal states are `cancelled`, `completed` and `failed`.

After entering `cancel_requested`, the service must not start a new model turn or a new tool invocation for that request. It should interrupt cooperative model/tool work where supported and then enter `cancelled` when no further service-owned work will start.

Cancellation is not rollback. If an external owner has already accepted or committed an operation, cancelling the agent workflow must not claim that operation was reverted. The result/event must distinguish "agent stopped" from the state of any already-submitted external transaction.

Transport disconnect is also not cancellation. Losing the SSE connection stops delivery to that client only; the request remains owned by AgentService until it reaches a terminal state or an explicit `CancelRequest(requestId)` is accepted.

## Core methods

The stable semantic surface is:

- `CreateConversation()` -> conversation id
- `ListConversations()`
- `ResumeConversation(conversationId)`
- `SendMessage(conversationId, text)` -> request id
- `SubscribeRequestEvents(requestId, afterSequence)`
- `CancelRequest(requestId)`
- `GetRequest(requestId)`
- `ChooseToolOption(requestId, decisionId, option)`
- `GetModels()` / `SetModel(conversationId, modelId)`
- `ListSkills()` / `SetSkillEnabled(skillId, enabled)`
- `ListMcpServers()`
- `GetAgentState()`

Model/provider credentials never cross this frontend contract as prompt text.

## Current loopback transport

The Phase B HTTP implementation currently maps those semantics to:

- `GET /v1/conversations`
- `POST /v1/conversations`
- `POST /v1/conversations/{conversationId}/messages` -> initial SSE event stream
- `GET /v1/requests/{requestId}`
- `GET /v1/requests/{requestId}/events?after={sequence}` -> reconnect SSE stream
- `POST /v1/requests/{requestId}/cancel`
- `POST /v1/requests/{requestId}/decisions/{decisionId}` with `{"option_index": N}`
- `GET /v1/models`
- `POST /v1/conversations/{conversationId}/model` with `{"model_id": "..."}`
- `GET /v1/skills`
- `POST /v1/skills/{skillId}` with `{"enabled": true|false}`
- `GET /v1/mcp-servers`

The transport is intentionally local-only:

- the server refuses non-loopback bind addresses;
- request `Host` must resolve to the loopback spelling used by the service (`127.0.0.1`, `localhost` or `::1`);
- requests carrying a browser `Origin` header are rejected;
- CORS preflight (`OPTIONS`) is rejected;
- POST requests require `application/json`;
- the server emits no permissive CORS headers.

These rules reduce browser-originated localhost abuse and DNS-rebinding-style access. They do not turn the loopback transport into an authentication boundary. A future transport/authentication change must preserve the same AgentService authorization semantics rather than treating possession of a localhost socket as OS authority.

## Backend adapter

The backend adapter is the only service-facing seam to the inherited Newelle runtime. It exposes conversation existence/creation, message execution, tool-choice continuation, request-local cancellation, models, Skills and MCP metadata. UI objects, GTK widgets and provider credentials are not part of this interface.

Execution handles returned by the adapter are opaque to transports and frontends. The service owns the mapping from `request_id` to execution handle and never exposes that object as authority. Backends may complete synchronously or asynchronously; terminal service state must not retain a stale handle.

Backends may also begin producing callbacks before `send_message()` returns its execution handle. AgentService buffers those early callbacks until the handle is registered, so an immediate tool decision or cancellation can never observe a request without its backend handle.

## Events and reconnect

The current stream emits:

- `request.started`
- `message.delta`
- `tool.requested`
- `request.completed`
- `request.cancelled`
- `request.failed`

Every emitted transport event receives a monotonically increasing request-local `seq`. A client should remember the highest sequence it has fully processed. If its stream disconnects while the same AgentService process is still alive, it may reconnect with `after=<last_seq>` and receive only later retained events.

The in-memory event journal is deliberately bounded. A reconnect cursor older than retained history is rejected explicitly rather than silently skipping events. Cursor `0` means "start from the currently retained history". Terminal request journals are retained only for a bounded number of recent requests.

This is reconnect support, not durable request execution. An AgentService process restart discards request event journals and must not silently replay an uncertain model/tool request. Durable conversation history remains a separate concern.

The broader semantic contract may add `request.stateChanged`, `message.started`, `message.completed` and `tool.completed` without changing the request/decision model.

Events carry `request_id`; conversation-scoped events also carry `conversation_id`. Tool decisions carry a service-issued `decision_id` and stale, replayed or cross-request responses must be rejected.

`tool.requested` may also carry bounded `display_text` presentation context. It exists so the frontend can explain what the user is deciding; for Router-backed system confirmation this contains trusted Router title/target/impact data. `display_text` is never decision authority and must not replace the service `decision_id` or an owning subsystem's fingerprint/confirmation contract.

## Tool pause semantics

`tool.requested` is a pause, not approval. The service waits for an explicit matching decision. Closing the frontend, losing the transport, timing out, or receiving malformed input must never be interpreted as approval.

Phase B continues to reuse upstream Newelle tool behavior while extracting the runtime, but the stable service contract never exposes `/option N`. Legacy Newelle `interaction_id` values are compatibility metadata only; they are never accepted as AgentService decision authority.

## Models, Skills and MCP

Models and Skills are exposed as structured data from the owning Newelle managers/handlers rather than by parsing human-readable slash-command output.

Each model record carries `selection_scope`. `conversation` means switching that model is local to the addressed conversation. `profile` means the underlying backend stores the selection at profile/process scope and the frontend must not imply that only the current chat changes. The current Newelle compatibility adapter reports `profile` because Newelle's provider/model settings are shared. The conversation id is still required when setting a model so a stale/dead conversation cannot be used as a blind settings mutation channel.

Each Skill record carries both `enabled` and `configured_enabled`. `configured_enabled` is the persisted profile preference controlled by `SetSkillEnabled`; `enabled` is the current effective state after request/runtime overlays are applied. The current Newelle compatibility adapter also reports `selection_scope: profile`. If an active Newelle Mode overrides the profile preference, `override_source` is `mode`, allowing the frontend to explain why the effective state differs from the saved setting instead of pretending the user's preference changed.

The current compatibility adapter exposes Skills through `SkillManager`. Newelle's authoritative structured MCP ownership API has not yet been identified, so the real compatibility adapter may return an empty MCP list. AgentService must not invent MCP state by scraping UI/presentation data merely to make this endpoint non-empty.

Skill text, model output and MCP descriptions remain untrusted input. Enabling a Skill or MCP server never grants an OS capability by itself.

## Persistence and restart

Conversation history is durable according to the inherited Newelle storage policy. Meo-owned conversations carry a `meo_conversation_id` metadata field so the compatibility adapter can rediscover them after service restart without taking ownership of unrelated Newelle chats.

Conversation identity must be unambiguous. If more than one inherited chat carries the same `meo_conversation_id`, the compatibility adapter must not guess which record owns that identity. Ambiguous conversation IDs are excluded from listing/resume and rejected until the underlying metadata is repaired.

Request execution state and event journals are not automatically assumed durable. After a service crash/restart:

- completed conversation history remains listable/resumable;
- any request whose execution outcome is uncertain must be surfaced as interrupted/failed, not silently replayed;
- external operations are queried from their owning service where a typed owner API exists rather than inferred from chat history.

## Installed service

The fork installs a `meo-agent-service` launcher and `meo-agent-service.service` systemd user unit. The unit binds to `127.0.0.1:8765`, runs unprivileged with `NoNewPrivileges=yes`, and is not automatically enabled by this repository.

Distro packaging may decide enablement only after live session acceptance. Installing or enabling this user service does not grant system privilege; later OS actions remain behind the typed System AI Router, capability policy and owning system/app APIs.

## Headless acceptance gate

Phase B is accepted only when the runtime service can start and serve the contract without constructing a GTK/Adwaita/WebKit frontend. Legacy GTK frontend code may remain in the repository until parity removal; the headless runtime package/import graph itself must not depend on those UI modules.

CI statically checks `meo/service` for forbidden UI imports and dynamically checks the runtime import graph. Meson staged-install CI also verifies the launcher, runtime modules and user unit are installed to the expected paths. These gates do not prove that a real provider and every real tool can execute headlessly on a live MeoArch session; that remains a separate acceptance track.

The full live acceptance suite must cover process start, real provider send/stream, tool pause/deny/approve, cancel in model wait, cancel while awaiting a tool decision, disconnect/reconnect using event sequences, runtime crash/restart, conversation resume, invalid/stale decision IDs, systemd user-session start/restart and Plasma-session behavior.
