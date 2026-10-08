# Meo SystemTool contract

Status: Phase C interface preparation. This contract consumes the merged
`org.meo.AIRouter1` metadata/confirmation model from `meo-kde` without moving
Router executors into `meo-ai`.

## Ownership boundary

`Meo AI` may propose a typed capability request. It does not grant the
capability and does not execute the OS action itself.

The flow is:

`LLM / Skill -> SystemTool -> org.meo.AIRouter1 -> capability owner -> verify`

The Router remains authoritative for the executable allowlist, exact argument
schema, caller binding, request fingerprint, expiry, confirmation state and
irreversible-action policy. Capability owners remain authoritative for the
actual operation and verification result.

The agent-side SystemTool must use Router `SubmitRequest(capabilityId,
arguments)` semantics. It must not use Router `SubmitText()` as a second LLM or
natural-language parser for model-generated actions.

## Capability metadata

SystemTool accepts only Router descriptors containing:

- `id`
- `title`
- `owner`
- `effect`: `read`, `session`, `persistent`, `irreversible`
- `verification`: `owner-result`, `read-back`
- `maturity`: `preview`, `stable`
- `requiresConfirmation`

The descriptor is informational plus an availability snapshot. Metadata never
grants authority. The Router still re-validates the capability and its exact
typed arguments when a request is submitted.

`preview` is not silently promoted to `stable`. SystemTool may expose an
executable preview capability if the Router lists it; the UI should present its
maturity honestly.

## Request and confirmation semantics

SystemTool performs only transport-safe structural validation of its argument
object. It deliberately does not coerce or duplicate capability-specific types.
The Router owns exact typed argument validation.

An irreversible request may return `awaiting_confirmation`. SystemTool must not
auto-approve it. Approval or denial requires a separate explicit call carrying
the Router-issued request ID and fingerprint. Closing UI, transport failure,
model output, Skill text or MCP output are never approval.

Router request IDs are distinct from AgentService request IDs. Correlation may
be recorded for UI/audit purposes later, but neither identifier is authority for
the other subsystem.

## D-Bus client

`meo.system.dbus_router.DbusNextRouterClient` implements the RouterClient
protocol against the existing user-session service:

- bus name `org.meo.AIRouter1`
- object path `/org/meo/AIRouter1`
- interface `org.meo.AIRouter1`
- `ListCapabilities()`
- `SubmitRequest(QString, QVariantMap)`
- `GetRequest(QString)`
- `DecideRequest(QString, QString, bool)`

The client keeps one session-bus connection for its lifetime. This is a security
requirement, not an optimization: Router binds request lookup and confirmation
to the original D-Bus caller unique name. Per-call `gdbus`, `busctl`, or other
short-lived subprocess connections are therefore not valid implementations.

The adapter uses `dbus-next` and imports it lazily. MeoArch packaging that
enables SystemTool must install the corresponding `python-dbus-next` runtime
dependency. Missing D-Bus support fails closed when the SystemTool adapter is
constructed/used; ordinary AgentService chat does not silently gain or emulate
system authority.

QVariantMap arguments are encoded as D-Bus `a{sv}` without capability-specific
coercion. Scalars retain explicit D-Bus types (`b`, `i`, `d`, `s`). Empty or
mixed-type arrays are rejected when no unambiguous D-Bus element signature can
be inferred. The Router remains the final exact-schema validator.

## Headless boundary

`meo/system/` is part of the unprivileged headless AgentService side and must
not import GTK/Adwaita/WebKit or Newelle UI modules. CI applies the same static
headless import gate used by `meo/service/`.

## Not moved into meo-ai

This phase does not move `meo-ai-router`, KIO/PulseAudioQt/KWin/Plasma
executors, Polkit helpers, Repair, OmniStore or SystemTransaction authority into
`meo-ai`. `meo-ai` contains only the unprivileged typed client/agent boundary;
execution remains in the existing Router and owning components.
