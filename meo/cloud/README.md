# Meo AI cloud

`meo/cloud/` owns AI-specific cloud state and service contracts. It does not own Meo Account authentication or raw provider credentials.

## Initial data model

The minimum server-side objects are:

- `conversations`: user-owned conversation identity and metadata;
- `messages`: ordered user/assistant/system-visible messages;
- `agent_runs`: remote/local agent execution attached to a conversation;
- `agent_events`: bounded/replayable execution progress metadata where needed;
- `devices`: AI-facing device registration metadata;
- `project_locations`: optional project-to-device/workspace hints;
- `memory_items`: later, only after a stable memory contract exists.

Account identity is referenced by the authenticated subject from Meo Account. Provider calls use the Account provider broker rather than storing a second copy of API keys.

## AgentRun minimum contract

An AgentRun should carry at least:

```text
id
conversation_id
device_id
workspace_id? / project_location_id?
executor
status
local_request_id?
last_event_seq
created_at
started_at?
finished_at?
```

Statuses should map cleanly onto the existing local AgentService lifecycle without pretending cloud state can roll back local side effects.

## Security rules

- Every cloud row is owner-scoped to the authenticated Meo Account subject.
- Browser clients never receive provider API keys.
- Device credentials are separate from provider credentials.
- Remote execution requires an explicitly registered device and capability set.
- Approval decisions must be bound to the exact AgentRun/request/decision identifiers.
- Cloud reconnect/resume must never replay a completed side-effecting request as a new local request.

## First acceptance

Two browser sessions signed into the same Meo Account should observe the same conversation and messages. A device-originated AgentRun event should appear in that conversation without giving the browser direct access to the device's local loopback service.
