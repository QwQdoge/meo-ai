# Meo AI security and simple-UX contract

Status: source-of-truth product rules for Web, Native, Cloud and remote-device execution.

## Product goal

Normal use should feel like one AI, not a remote-computer control panel.

A user should normally be able to type:

> Check the meo-ai project and run the tests.

Meo AI should resolve the project, device, local workspace, executor and safe default permission policy automatically.

The user should not normally need to see or enter:

- device IDs;
- local filesystem paths;
- workspace IDs;
- AgentRun IDs;
- API credential IDs;
- relay URLs;
- capability IDs;
- raw tool payloads.

Those identifiers may appear in diagnostics or advanced settings, but they are not the primary interaction model.

## Default routing UX

1. If a project has exactly one online saved location, use it automatically.
2. If no project is supplied and exactly one eligible device is online, use it automatically.
3. If multiple eligible devices remain, ask one simple device-choice question.
4. If a project has no trusted local mapping, ask the user to open/connect the project on a trusted device. Never accept a browser-supplied path as a fallback.
5. Remember a successful project-to-device/workspace mapping so the same choice is not repeatedly requested.

Cloud `workspace_ref` values are opaque local workspace IDs. Real filesystem paths remain on the device.

## Default permission UX

`Smart` is the default.

- Low-risk read/search/status operations should proceed without repetitive prompts.
- High-risk or externally visible side effects require an explicit decision.
- `Ask` may be chosen by users who want confirmation more often.
- `Full Access` is never enabled merely by a browser request. It requires a trusted Account/device authorization and still does not bypass local owner or polkit checks.

One approval should describe the human-visible effect, not expose raw transport payloads.

Examples:

- Good: `Allow Meo AI to push this commit to origin/main?`
- Bad: `Approve tool option index 2 for capability git.push?`

## Security boundaries

### Browser/Web client

Must never receive or provide authoritative values for:

- provider API secrets;
- Supabase service-role keys;
- device bearer credentials;
- arbitrary local paths;
- arbitrary shell commands for the Relay transport;
- authoritative account user IDs.

The public AgentRun create schema is intentionally small:

- conversation ID;
- user text;
- optional project ID;
- optional device preference;
- permission mode preference.

Unknown fields are rejected.

### Meo Account

Owns:

- user identity and sessions;
- OAuth/OIDC;
- re-authentication;
- encrypted provider credentials;
- provider authorization/grants.

Device enrollment is an account-security operation and must require trusted re-authentication before a long-lived device credential is issued.

### Meo AI Cloud

Owns:

- conversations/messages;
- device metadata;
- project mappings using opaque workspace IDs;
- AgentRun orchestration;
- ordered AgentRun events;
- routing and product policy.

Service-role access is server-only. Because service role bypasses RLS, server-side reads must include explicit owner filters and database constraints must enforce tenant integrity where possible.

### Device

Owns:

- real filesystem paths;
- local workspace registry;
- local AgentService request lifecycle;
- local tools and model availability;
- final local execution constraints.

A cloud workspace reference must resolve to an already-known local workspace ID. Unknown values fail closed and are never interpreted as paths.

### System/application owners

Remain the final authority for privileged system effects. Meo AI policy does not replace polkit, application permissions, or typed System AI Router ownership.

## Remote execution invariants

- One cloud AgentRun binds to at most one local AgentService request.
- Reconnect must resume, not recreate, a side-effecting request.
- Device events have monotonically increasing per-run sequence numbers.
- Events remain pending on the device until the cloud acknowledges persistence.
- `(run_id, seq)` is unique in cloud storage so replay is idempotent.
- Cross-account resources should normally appear as not found, not reveal existence.
- Device credentials are separate from Account access tokens and provider credentials.
- Device credentials are stored server-side only as one-way hashes and may be revoked independently.

## Conversation mapping

A cloud conversation is mapped deterministically to a local compatibility conversation ID:

`meo:cloud:<sha256-prefix>`

The raw cloud ID is not used as an arbitrary legacy session key. Each device may maintain its own local execution state while the cloud conversation remains the product-level identity.

## Error UX

Prefer short actionable messages:

- `No suitable Meo device is online right now.`
- `Choose which of your online devices should run this task.`
- `Open this project once on a trusted device to connect its workspace.`
- `This action needs your approval.`

Do not surface raw stack traces, database errors, provider secrets, local filesystem paths, token contents, or internal policy payloads to normal users.
