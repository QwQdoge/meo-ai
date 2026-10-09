# Meo AI cloud

`meo/cloud/` owns AI-specific cloud state, remote AgentRun orchestration and the device relay. It does not own Meo Account authentication or raw provider credentials.

## Initial data model

The minimum server-side objects are:

- `conversations`: user-owned conversation identity and metadata;
- `messages`: ordered user/assistant/system-visible messages;
- `agent_runs`: remote/local agent execution attached to a conversation;
- `agent_events`: bounded/replayable execution progress metadata;
- `devices`: AI-facing device registration metadata;
- `device_credentials`: hashed, narrow device relay credentials;
- `device_enrollments`: short-lived browser-approved pairing requests;
- `project_locations`: optional project-to-device/opaque-workspace hints;
- `memory_items`: later, only after a stable memory contract exists.

Account identity is taken from a Meo Account access token verified against Supabase Auth. Provider calls should use the Account provider broker rather than storing a second copy of API keys.

## Cloud service

Install the isolated cloud dependency:

```bash
python3 -m pip install -r meo/cloud/requirements.txt
```

Required server-only environment variables:

```text
MEO_SUPABASE_URL
MEO_SUPABASE_PUBLISHABLE_KEY
MEO_SUPABASE_SERVICE_ROLE_KEY
```

Optional deployment configuration:

```text
MEO_ACCOUNT_URL=https://account.meoarch.org
MEO_ALLOWED_WEB_ORIGINS=https://chat.meoarch.org
MEO_BIND_HOST=127.0.0.1
PORT=8080
```

`MEO_ALLOWED_WEB_ORIGINS` is a comma-separated exact allowlist. The origin of `MEO_ACCOUNT_URL` is always included automatically. Public HTTP origins, credentials in origins, paths, query strings and fragments are rejected. Loopback HTTP is accepted only for local development.

Run behind an HTTPS reverse proxy:

```bash
python3 -m meo.cloud.server
```

The public API intentionally stays small:

```text
POST /v1/device-enrollments/start
POST /v1/device-enrollments/poll
GET  /v1/device-enrollments/{user_code}
POST /v1/device-enrollments/{user_code}/approve
POST /v1/agent-runs
POST /v1/agent-runs/{run_id}/cancel
POST /v1/agent-runs/{run_id}/decisions/{decision_id}
GET  /v1/device-relay              # WebSocket, meo-agentd.v1
GET  /health
```

Browser requests use the Meo Account bearer token. Device Relay uses a separate narrow `meo_dev_*` bearer token. Device credentials never authorize normal user APIs.

## Device enrollment

Enrollment is intentionally similar to a TV/CLI device flow:

```text
device -> start pairing -> short public code + one-time secret
browser -> sign in -> preview named device -> Allow
        -> recent account_security re-auth required at approval

device -> poll with one-time secret -> receive meo_dev_* exactly once
```

The database stores only SHA-256 hashes of pairing/device secrets. Enrollment expires after ten minutes. Long-lived device credentials default to ninety days and carry only `relay.connect` + `agent.run`; a device cannot request Full Access or arbitrary credential scopes during enrollment.

Consumption is performed by a row-locked service-role RPC so concurrent polling cannot mint two credentials. A consumed enrollment never replays plaintext credential material.

## AgentRun minimum contract

An AgentRun carries at least:

```text
id
conversation_id
device_id
project_id?
workspace_ref?        # opaque local workspace ID, never a filesystem path
permission_mode
requested_capabilities
status
local_request_id?
last_event_seq
created_at
started_at?
finished_at?
```

Statuses map onto the existing local AgentService lifecycle without pretending cloud state can roll back local side effects.

## Security and UX rules

- Every cloud row is owner-scoped to the authenticated Meo Account subject.
- Browser clients never receive provider API keys, service-role credentials, device tokens or local filesystem paths.
- Browsers submit ordinary AgentRuns as conversation + text + optional project; device/workspace routing stays server-owned.
- Cross-origin browser access uses an exact origin allowlist; wildcard CORS and cookie credentials are not enabled.
- Device credentials are separate from provider and account credentials.
- Remote execution requires an explicitly registered device and capability set.
- Full Access cannot be enabled by a browser payload; it requires a future trusted server-side re-auth authorization path.
- Approval decisions are bound to exact AgentRun/request/decision identifiers.
- Cloud reconnect/resume must never replay a completed side-effecting request as a new local request.

## First acceptance

A useful first end-to-end acceptance is:

1. run the pairing client on the Legion;
2. approve the named device in Meo Account;
3. confirm the narrow token lands in KWallet;
4. start `meo-agentd` and observe the device online;
5. from another browser, create one AgentRun with only conversation/text/project;
6. verify the correct Newelle workspace is selected locally without exposing its path to cloud;
7. stream text/tool events through the existing SSE endpoint;
8. require an explicit decision only when the local agent requests a sensitive action;
9. cancel and reconnect without duplicate execution.
