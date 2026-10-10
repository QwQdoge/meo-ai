# Meo AgentService contract

Status: Phase B contract with an early Phase C typed-SystemTool preview. This document defines the stable frontend/runtime boundary before GTK removal.

## Boundary

`Meo AI` is the Qt/QML frontend. `AgentService` owns the Newelle-derived agent runtime and runs as an unprivileged user service. The service does not gain OS authority from prompts, Skills, MCP descriptions, model output or frontend requests.

The current implementation uses loopback HTTP/SSE as a transport, but HTTP is not the product security contract. A later D-Bus or credentialled local transport must preserve conversation identity, request identity, decision identity, event ordering, reconnect semantics and cancellation semantics.

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

After entering `cancel_requested`, the service must not start a new model turn or a new tool invocation for that request. It should interrupt cooperative model/tool work where supported and then enter `cancelled` when no further service-owned work will start. The current Newelle compatibility adapter explicitly cancels a pending interactive `ToolResult` so an `awaiting_tool` worker does not stay blocked on its semaphore after Stop.

Cancellation is not rollback. If an external owner has already accepted or committed an operation, cancelling the agent workflow must not claim that operation was reverted. The result/event must distinguish "agent stopped" from the state of any already-submitted external transaction.

Transport disconnect is also not cancellation. Losing the SSE connection stops delivery to that client only; the request remains owned by AgentService until it reaches a terminal state or an explicit `CancelRequest(requestId)` is accepted.

## Core methods

The stable semantic surface is:

- `CreateConversation()` -> conversation id
- `ListConversations()`
- `ListMessages(conversationId)`
- `ResumeConversation(conversationId)`
- `SendMessage(conversationId, text)` -> request id
- `SubscribeRequestEvents(requestId, afterSequence)`
- `CancelRequest(requestId)`
- `GetRequest(requestId)`
- `ChooseToolOption(requestId, decisionId, option)`
- `GetModels()` / `SetModel(conversationId, modelId)`
- `GetModelRoles()` / `SetModelRole(roleId, modelIdOrNull)`
- `ListSkills()` / `SetSkillEnabled(skillId, enabled)`
- `ListMcpServers()`
- `GetAgentState()`

Model/provider credentials never cross this frontend contract as prompt text.

`ListMessages` is a presentation-safe history surface. The compatibility adapter exposes only visible `user` and `assistant` text. Inherited `Console`, `Command`, `File`, `Folder`, tool-internal records and injected retrieval `<context>` blocks are not replayed into the native UI.

`GetAgentState` deliberately reports only state owned by AgentService itself: whether a backend is attached, active request count and per-lifecycle-state counts. It does not infer provider/model health merely because a backend object exists.

## Current loopback transport

The Phase B HTTP implementation currently maps those semantics to:

- `GET /v1/agent-state`
- `GET /v1/conversations`
- `POST /v1/conversations`
- `GET /v1/conversations/{conversationId}/messages`
- `POST /v1/conversations/{conversationId}/messages` -> initial SSE event stream
- `GET /v1/requests/{requestId}`
- `GET /v1/requests/{requestId}/events?after={sequence}` -> reconnect SSE stream
- `POST /v1/requests/{requestId}/cancel`
- `POST /v1/requests/{requestId}/decisions/{decisionId}` with `{"option_index": N}`
- `GET /v1/models`
- `POST /v1/conversations/{conversationId}/model` with `{"model_id": "..."}`
- `GET /v1/model-roles`
- `POST /v1/model-roles/{roleId}` with `{"model_id": "..."}` or `{"model_id": null}`
- `GET /v1/skills`
- `POST /v1/skills/{skillId}` with `{"enabled": true|false}`
- `GET /v1/mcp-servers`

The transport is intentionally local-only:

- the server refuses non-loopback bind addresses;
- request `Host` must resolve to `127.0.0.1`, `localhost` or `::1`;
- requests carrying a browser `Origin` header are rejected;
- CORS preflight (`OPTIONS`) is rejected;
- POST requests require `application/json`;
- the server emits no permissive CORS headers.

These rules reduce browser-originated localhost abuse and DNS-rebinding-style access. They do not turn the loopback transport into an authentication boundary. System authority remains behind the typed System AI Router and owning APIs; SystemTool stays opt-in until the final local IPC/authentication boundary is accepted.

## Backend adapter

The backend adapter is the only service-facing seam to the inherited Newelle runtime. It exposes conversation existence/creation, presentation-safe history, message execution, tool-choice continuation, request-local cancellation, models, Skills and MCP metadata. UI objects, GTK widgets and provider credentials are not part of this interface.

Execution handles returned by the adapter are opaque to transports and frontends. The service owns the mapping from `request_id` to execution handle and never exposes that object as authority. Backends may complete synchronously or asynchronously; terminal service state must not retain a stale handle.

Backends may begin producing callbacks before `send_message()` returns its execution handle. AgentService buffers those early callbacks until the handle is registered, so an immediate tool decision or cancellation cannot observe a request without its backend handle.

## Events and reconnect

The current stream emits:

- `request.started`
- `message.delta`
- `tool.requested`
- `tool.completed`
- `presentation.card`
- `request.completed`
- `request.cancelled`
- `request.failed`

Every emitted transport event receives a monotonically increasing request-local `seq`. A client remembers the highest sequence it has fully processed. If its stream disconnects while the same AgentService process is still alive, it may reconnect with `after=<last_seq>` and receive only later retained events.

The in-memory event journal is bounded. A reconnect cursor older than retained history is rejected explicitly rather than silently skipping events. Terminal request journals are retained only for a bounded number of recent requests.

This is reconnect support, not durable request execution. An AgentService process restart discards request event journals and must not silently replay an uncertain model/tool request. Durable conversation history is restored independently through `ListMessages`.

Events carry `request_id`; conversation-scoped events also carry `conversation_id`. Tool decisions carry a service-issued `decision_id`; stale, replayed or cross-request responses are rejected.

`tool.requested` may carry bounded `display_text` presentation context. For Router-backed confirmation this contains trusted Router title/target/impact data. `display_text` is never decision authority and must not replace the service `decision_id` or an owning subsystem's fingerprint/confirmation contract.

A non-interactive inherited `tool_result` is normalized as `tool.completed`; it must not be mistaken for an interactive approval request or fail the whole AgentService request after the tool already succeeded.

`presentation.card` is data-only presentation. The compatibility backend may emit `presentation_card` containing a bounded native card payload; AgentService normalizes it before the frontend sees it. The current schema accepts only the registered kinds `info`, `status`, `metric`, `file` and `system`, and only `card_id`, `kind`, `title`, `subtitle`, `value` and `detail` reach QML. Arbitrary QML, HTML, JavaScript, commands, URLs and action payloads are not part of this contract. Presentation cards carry no approval or capability authority.

## Tool pause semantics

`tool.requested` is a pause, not approval. The service waits for an explicit matching decision. Closing the frontend, losing the transport, timing out, or receiving malformed input must never be interpreted as approval.

Phase B continues to reuse upstream Newelle tool behavior while extracting the runtime, but the stable service contract never exposes `/option N`. Legacy Newelle `interaction_id` values are compatibility metadata only; they are never accepted as AgentService decision authority.

## Models, model roles, Skills and MCP

Models and Skills are exposed as structured data from their owning Newelle managers/handlers rather than by parsing slash-command presentation output.

Each model record carries `selection_scope`. `conversation` means switching that model is local to the addressed conversation. `profile` means the backend stores the selection at profile/process scope. The current Newelle compatibility adapter reports `profile` because Newelle provider/model settings are shared.

AgentService also stores non-secret model-role preferences for `title`, `judge`, `reasoning` and `execution`. A role record includes a preferred model, fallback model, workload class and whether true role-specific runtime routing is active. The current compatibility backend cannot safely run concurrent per-call model selections, so these records deliberately report `runtime_supported=false` and `routing_status=preference_only`. The UI may configure the future routing preference but must not claim the role is active until the extracted AgentCore/provider broker supports request-local model choice.

`title` is intended for cheap background naming/label work. `judge` is intended for structured classification, ranking and routing decisions. `reasoning` is the main planner/answer model. `execution` is the tool-capable implementation model. The Judge role is not a security authority: it must never authorize privileged operations, replace deterministic policy, grant capabilities or bypass human confirmation. Model selection also never changes tool permissions.

Each Skill record carries both `enabled` and `configured_enabled`. `configured_enabled` is the persisted profile preference; `enabled` is the current effective state after runtime/Mode overlays. If a Mode overrides the profile preference, `override_source` is `mode`.

MCP metadata now comes from Newelle's structured MCP configuration/integration (`mcp_servers` / `mcp_servers_dict`). The frontend contract deliberately exposes only a non-secret id, display label and whether the integration is currently loaded. Raw URLs, bearer tokens, custom headers, stdio environment variables and other connection secrets are not exposed through `ListMcpServers`.

Skill text, model output and MCP descriptions remain untrusted input. Enabling a Skill or MCP server never grants an OS capability by itself.

## Persistence and restart

Conversation history is durable according to inherited Newelle storage. Meo-owned conversations carry a `meo_conversation_id` metadata field so the compatibility adapter can rediscover them after service restart without taking ownership of unrelated Newelle chats.

Conversation identity must be unambiguous. If more than one inherited chat carries the same `meo_conversation_id`, the adapter does not guess ownership; the ambiguous identity is excluded until metadata is repaired.

The native client stores its current AgentService conversation id. On startup it requests the presentation-safe history and replays those messages into QML. A 404 clears the stale saved conversation id so the next send can create a new conversation instead of trapping the UI on a dead identity.

Model-role preferences persist separately as non-secret local configuration. They contain model identifiers only, not provider credentials. Provider/API credentials remain an Account/provider-broker responsibility and must not be persisted by QML or embedded in prompts.

Request execution state and event journals are not automatically durable. After a service crash/restart:

- completed conversation history remains listable/resumable;
- any request whose execution outcome is uncertain must be surfaced as interrupted/failed, not silently replayed;
- external operations are queried from their owning service where a typed owner API exists rather than inferred from chat history.

## Installed service

The fork installs a `meo-agent-service` launcher and `meo-agent-service.service` systemd user unit. The unit binds to `127.0.0.1:8765`, runs unprivileged with `NoNewPrivileges=yes`, and is not automatically enabled by this repository.

Distro packaging may decide default activation only after live session acceptance. The native client therefore still has an explicit AgentService preview endpoint/legacy compatibility split; switching the product default must happen together with a reliable installed-service activation path rather than merely changing a frontend environment-variable default.

## Headless acceptance gate

Phase B is accepted only when the runtime service can start and serve the contract without constructing a GTK/Adwaita/WebKit frontend. Legacy GTK frontend code may remain in the repository until parity removal; the headless runtime package/import graph itself must not depend on those UI modules.

CI statically checks stable headless layers for forbidden UI imports and dynamically checks the runtime shell. Meson staged-install CI verifies the launcher, runtime modules and user unit. Native CI covers transport, early cancellation, request recovery, conversation-history restore, structured service metadata and QML smoke behavior. Python protocol tests cover model-role persistence/HTTP semantics and presentation-card normalization.

These gates do not yet prove that a real provider and every real tool can execute headlessly on a live MeoArch session. Memory remains intentionally outside the stable frontend contract until an authoritative, non-UI Newelle memory surface is selected. The full live acceptance suite still covers real provider send/stream, tool pause/deny/approve, cancel in model wait, cancel while awaiting a tool decision, disconnect/reconnect, runtime crash/restart, conversation resume, invalid/stale decisions, systemd user-session start/restart and Plasma-session behavior.

See `presentation-model-routing.md` for the presentation block and multi-model evolution plan.
