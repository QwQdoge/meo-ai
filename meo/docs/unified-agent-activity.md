# Unified Agent activity (Chat / Work / native)

Decision (2026-10-19): **one activity UI contract; not one execution engine**.

## Existing capabilities

- The Newelle compatibility integration in `src/integrations/agent_tools.py` runs
  a background subagent with a task, selected tools and an eventual result.
  The GTK `src/ui/widgets/subagent.py` widget already shows a collapsible
  execution transcript. This is **not yet a durable cloud AgentRun**; its
  thread/controller and GTK widget must not be copied into the Web frontend.
- Meo-owned `meo/cloud/` and `meo/device/` implement authenticated remote
  AgentRun dispatch, status transitions, bounded event replay, tool decisions
  and a single binding to a local AgentService request.
- Web Work now renders remote runs through `AgentActivityPanel`, a UI
  component that also supports real nested task nodes in its presentation
  model. **No nested tasks are synthesized or offered for execution today.**

## Separate relationship from execution location

These are independent axes. A remote subagent is valid.

| Dimension | Examples | Meaning |
| --- | --- | --- |
| Task relation | `root`, `subagent` | Who delegated the work? |
| Execution location | `local`, `remote`, `cloud` | Where is it executed? |
| State | `queued`, `running`, `awaiting_approval`, `completed`... | What actually happened? |
| Target | Project binding, verified device/environment | What owns resources? |

The shared UI displays a task summary, status, target, output, real activity
events, approval choices and cancellation/reconnect actions when the backing
runtime actually supports them. A parent task may contain expandable child
tasks using the same visual component. There should not be separate top-level
Chat/Work/Subagent destinations or duplicated "Remote" and "Subagent" screens.

## Future service-owned task protocol

Do not accept these fields as browser authority. A trusted AgentService must
issue and persist them:

- `task_id`, `parent_task_id` (optional), `root_run_id`, account/Project
  ownership and request-local correlation IDs
- `relation`, `execution_location`, server-resolved target binding and
  effective capability/permission subset
- versioned monotonically ordered events, terminal state and bounded output
  references; child events refer to the parent/root but never silently
  overwrite parent output
- activity events `task.created`, `task.started`, `task.progress`,
  `task.awaiting_approval`, `task.completed`, `task.failed` and
  `task.cancel_requested` must be documented and tested before the browser
  starts rendering child AgentRuns

A frontend **never** creates privileged child IDs, assumes a device is online
because it appeared in the workspace directory, grants access using a tool
description, or converts a browser disconnect into task cancellation.

## Permission and scheduling constraints

- A child can only receive the intersection of its parent's effective
  capabilities and destination-device policy, never their union.
- User confirmation remains required when a tool or device boundary demands
  it; subagent nesting does not waive confirmation.
- Parent cancellation is a *request* to propagate to children. The UI only
  displays a terminal cancelled state when acknowledged by the service.
- Set explicit concurrency, recursion-depth, time, and token budgets in the
  service before exposing autonomous multi-agent fan-out. Initial product
  targets could be depth 2 and up to 3 concurrent children, but those are
  **proposals, not current enforcement**.
- Cross-device subagents must use the same authenticated AgentRun relay as
  remote root tasks, with replay and user-owned event filtering.
- Main-agent synthesis must consume structured child results with stable
  source references; opaque model text is never an authorization grant.

## Delivery boundary

This initial UI refactor extracts a shared React activity renderer and
migrates the existing remote Work panel without changing dispatch, model
permissions or persistence. Web still cannot start a Newelle/GTK subagent.
Before adding a "Spawn subagent" action, expose a headless typed AgentService
operation, durable child-run/events endpoints, owner-scoped replay, approval
state and native/Web end-to-end validation. Native clients may implement the
same data contract in QML/MeoUI rather than importing React.
