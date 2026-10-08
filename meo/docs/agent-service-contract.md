# Meo AgentService contract

Status: Phase B contract. This document defines the stable frontend/runtime boundary before GTK removal.

## Boundary

`Meo AI` is the Qt/QML frontend. `AgentService` owns the Newelle-derived agent runtime and runs as an unprivileged user service. The service does not gain OS authority from prompts, Skills, MCP descriptions, model output or frontend requests.

The first implementation may use loopback transport internally, but the semantic contract below must not depend on HTTP/SSE details. A later D-Bus implementation must preserve request identity, event ordering and cancellation semantics.

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

## Core methods

The transport should expose semantic equivalents of:

- `CreateConversation()` -> conversation id
- `ListConversations()`
- `ResumeConversation(conversationId)`
- `SendMessage(conversationId, text)` -> request id
- `CancelRequest(requestId)`
- `GetRequest(requestId)`
- `ChooseToolOption(requestId, decisionId, option)`
- `GetModels()` / `SetModel(conversationId, modelId)`
- `ListSkills()` / `SetSkillEnabled(skillId, enabled)`
- `ListMcpServers()`
- `GetAgentState()`

Model/provider credentials never cross this frontend contract as prompt text.

## Backend adapter

The backend adapter is the only service-facing seam to the inherited Newelle runtime. It exposes conversation existence/creation, message execution, tool-choice continuation, request-local cancellation, models, Skills and MCP metadata. UI objects, GTK widgets and provider credentials are not part of this interface.

Execution handles returned by the adapter are opaque to transports and frontends. The service owns the mapping from `request_id` to execution handle and never exposes that object as authority. Backends may complete synchronously or asynchronously; terminal service state must not retain a stale handle.

## Events

At minimum:

- `request.stateChanged`
- `message.started`
- `message.delta`
- `message.completed`
- `tool.requested`
- `tool.completed`
- `request.cancelled`
- `request.failed`

Events carry `request_id`; conversation-scoped events also carry `conversation_id`. Tool decisions carry a service-issued `decision_id` and must reject stale or mismatched responses.

## Tool pause semantics

`tool.requested` is a pause, not approval. The service waits for an explicit matching decision. Closing the frontend, losing the transport, timing out, or receiving malformed input must never be interpreted as approval.

Phase B continues to reuse upstream Newelle tool behavior while extracting the runtime, but the final service contract must not expose `/option N` as its stable API. Legacy Newelle `interaction_id` values are compatibility metadata only; they are never accepted as AgentService decision authority.

## Persistence and restart

Conversation history is durable according to the inherited Newelle storage policy. Request execution state is not automatically assumed durable.

After a service crash/restart:

- completed conversation history remains listable/resumable;
- any request whose execution outcome is uncertain must be surfaced as interrupted/failed, not silently replayed;
- external operations are queried from their owning service where a typed owner API exists rather than inferred from chat history.

## Headless acceptance gate

Phase B is accepted only when the runtime service can start and serve the contract without constructing a GTK/Adwaita/WebKit frontend. Legacy GTK frontend code may remain in the repository until parity removal; the headless runtime package/import graph itself must not depend on those UI modules.

CI statically checks `meo/service` for forbidden UI imports. This is only an import-boundary gate: it does not prove that the eventual Newelle adapter or provider runtime can execute headlessly. That still requires a real process-start acceptance test.

The acceptance suite must cover start, send/stream, tool pause/deny/approve, cancel in model wait, cancel while awaiting a tool decision, disconnect/reconnect, runtime crash/restart, conversation resume and invalid/stale decision IDs.
