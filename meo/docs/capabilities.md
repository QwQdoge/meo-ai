# Meo AI capabilities: Skills, Apps and Connectors

Meo AI presents reusable AI abilities through one capability model. Skills and
Connectors are different kinds of the same catalog item; they are not separate
agent engines.

## Product model

A **Skill** is a reusable workflow or set of instructions. It may describe how to
perform a task, what evidence to gather and how to present a result. A Skill does
not grant permissions and does not hold OAuth tokens.

A **Connector** is a brokered integration that can provide typed tools and data.
Its implementation may be:

- an official Meo integration;
- an MCP server adapter;
- a future Meo plugin;
- a local System AI Router capability provider.

All of these implementations map into the same `CapabilityDescriptor` in the
Rust core. The model and frontends do not get long-lived third-party credentials.

## User experience

Use one capability catalog across Web, desktop and Android.

### Chat and Work

The composer capability picker may show Skills and connected Apps/Connectors in
one surface, grouped by kind when useful. A user should be able to answer “what
can Meo use for this request?” without understanding MCP or internal providers.

Examples:

- `System diagnostics` — Skill
- `Google Drive` — Connector
- `GitHub` — Connector
- `Files (MCP)` — Connector backed by MCP
- `Meo System` — Connector backed by the System AI Router

Only capabilities selected for or relevant to the current request should enter
the model-facing capability context. The Context Engine should budget this
metadata separately from transcript and Memory content.

### Skills

`Skills` remains a primary product destination because Skills are reusable,
user-visible workflows. A Skill card can show required or recommended connected
Apps underneath it, but enabling a Skill never connects those Apps automatically.

### Settings > Apps & Connectors

Connection administration belongs in Settings. This is where users connect or
revoke accounts, inspect requested permissions, configure MCP servers and see
connection health. The same catalog entries are rendered here with administration
actions; this is not a second connector registry.

## Permission and execution rules

1. A Skill dependency never grants a Connector permission.
2. A disconnected Connector exposes no model tools.
3. `context_hint`, Skill markdown and MCP descriptions are model guidance only;
   they are never authorization policy.
4. System actions continue through the System AI Router typed request,
   confirmation, Polkit/owner and verification boundaries.
5. OAuth/access/refresh tokens remain in Meo Account or the owning broker and are
   never serialized in `CapabilityDescriptor` or sent to frontends.
6. A Connector can expose read, write and execute effects, but the owning
   authority still validates every invocation.
7. Web cannot pretend to have local-machine privilege. Local capabilities require
   an authenticated Meo device/Work target or an online integration.

## Stable contract

The authoritative contract is `meo/core-rs/src/capabilities.rs`.

Every descriptor has a stable `capability_id`, `kind`, origin, connection state,
permissions, optional typed tools, dependencies and a short deterministic
`context_hint`.

The Rust AgentService exposes:

- `GET /v1/capabilities`
- `GET /v1/capabilities/{capability_id}`
- `POST /v1/capabilities/{capability_id}/state` for the safe user-facing enabled
  flag only

Connector authorization and connection-state mutation are intentionally not part
of that generic state endpoint. They belong to the connector/account broker.

During migration, the original C++ client projects legacy `/v1/skills` and
`/v1/mcp-servers` metadata into the same `capabilities` shape. Those legacy
endpoints remain compatibility surfaces and should eventually disappear after the
Rust service/client path owns the supported release.

## Model-facing resolution

`CapabilityCatalog::resolve()` accepts the exact capability IDs selected for one
request. Resolution is deterministic and fails closed for disabled or disconnected
capabilities. It deduplicates typed tools and returns deterministic context hints.

Dependencies are informational and validation inputs, not implicit authority. If
a Skill lists `connector.drive` in `requires`, the caller still has to select an
enabled and connected Drive capability before Drive tools can be exposed.

## Next execution step

Provider tool-call parsing already exists in the Rust provider, but a provider
`tool_call` must not be treated as executed merely because it was parsed. The
execution loop must resolve the tool ID back to the selected Connector, dispatch
to that Connector's broker/Router, enforce confirmation and policy, preserve the
raw tool result for Context Engine recovery, then send the verified result back
to the model.

Until that brokered loop is complete, UI must not label a parsed provider tool
call as a completed Connector action.
