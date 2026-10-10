# Meo AI account and data model

Status: source-of-truth ownership model for identity, provider credentials, conversations, devices and AgentRuns.

## Product identity

Meo AI has one user-facing identity: **Meo Account**.

The same account is used by:

- Web chat;
- native Meo AI;
- device registration;
- provider grants;
- conversation sync;
- remote AgentRuns.

LibreChat authentication is configured to trust Meo Account through OpenID Connect. LibreChat-local email/password registration is disabled for the Meo deployment.

## Authority split

### Meo Account owns

- authentication identity;
- OAuth/OIDC authorization;
- active account sessions and revocation;
- MFA/account-security policy;
- encrypted provider API credentials;
- provider credential metadata;
- durable consent/grant authority for use of those credentials.

### Meo AI owns

- conversation list and titles;
- message history;
- selected model/provider presentation;
- memory and project context;
- device registry presentation;
- project-to-device mappings;
- AgentRun orchestration and event history;
- user-visible approval UX;
- routing between cloud providers and local devices.

### Device owns

- actual local workspace bytes;
- local model runtime;
- AgentService execution handles;
- local capability availability;
- local system/tool policy enforcement.

### System owners keep privileged authority

Meo AI may request system actions through typed capabilities, but it does not absorb KWin/KIO/PulseAudio/Polkit/Repair/OmniStore privilege authorities.

## Provider credentials

A provider connection is represented to Meo AI by metadata only:

```text
credential_id
provider
display_name
endpoint
default_model
secret_hint
enabled
updated_at
```

The API key itself remains encrypted and broker-owned.

Provider credentials are never:

- returned to LibreChat;
- returned to the native QML app;
- persisted in Meo AI conversation storage;
- inserted into prompts;
- copied into device relay messages.

## Chat grants

The existing payload-bound one-shot consent flow remains suitable for sensitive, unusual or isolated operations such as image generation.

Interactive chat adds a reusable grant layer so ordinary conversation does not require confirmation for every message.

### Recommended modes

`ask_every_time`

- no reusable grant;
- exact request is prepared/approved/invoked;
- strongest friction and narrowest scope.

`session`

- default for interactive chat;
- one provider credential + allowed data categories;
- short expiry, normally tied to the active user session or a bounded number of hours;
- revocable immediately.

`persistent`

- explicit opt-in;
- remains usable across sessions until revoked or invalidated by policy/credential changes.

### Grant invalidation

A grant becomes unusable when any of the following applies:

- expired;
- revoked;
- account session/security policy requires reauthorization;
- credential was deleted or disabled;
- credential/provider revision changed in a way Account defines as security-sensitive;
- requested data categories are outside the grant;
- client identity does not match;
- account ownership does not match.

## Suggested Meo AI cloud tables

These are logical contracts; exact SQL migration names and deployment are separate implementation work.

### `ai_conversations`

- `id`
- `user_id`
- `title`
- `created_at`
- `updated_at`
- `archived_at`
- optional project association

### `ai_messages`

- `id`
- `conversation_id`
- `user_id`
- `sequence`
- visible role
- content envelope
- executor kind (`provider`, `agent_run`, `system`)
- model/provider metadata without secrets
- created timestamp

Messages should not persist provider API keys, bearer tokens, raw local environment variables or hidden tool credentials.

### `ai_chat_grants`

Prefer Account as the authoritative store if grants authorize Account-owned credentials. Meo AI may cache non-secret grant metadata for UX, but Account decides whether a grant is valid.

Logical fields:

- `grant_id`
- `user_id`
- `client_id`
- `credential_id`
- `mode`
- allowed data categories
- `issued_at`
- `expires_at`
- `revoked_at`
- grant schema version

### `ai_devices`

- `device_id`
- `user_id`
- display name
- operating system
- agent protocol version
- last seen
- online/derived presence
- public device key/fingerprint when device authentication is added

Presence is derived from relay connectivity/heartbeats rather than trusted from a client-supplied boolean.

### `ai_device_capabilities`

- device ID
- capability ID
- version/maturity
- non-secret metadata
- last catalog revision

### `ai_projects`

- project ID
- user ID
- display name
- optional project instructions/context

### `ai_project_locations`

Maps a logical project to a device-local workspace identifier.

Do not require cloud storage of the workspace path when the device can keep a private opaque workspace ID. If a path is stored for usability, treat it as private account data and never expose it across users.

### `ai_agent_runs`

- cloud `run_id`
- user ID
- conversation ID
- target device ID
- workspace/project reference
- permission mode
- requested executor/backend
- current cloud status
- bound local AgentService request ID
- last accepted local event sequence
- timestamps and safe terminal error code

### `ai_agent_events`

Store only events required for reconnect/audit/product history. Large raw terminal streams may need retention limits or chunk storage rather than unbounded rows.

## RLS / authorization model

All exposed Meo AI tables are user-owned and must enforce row-level ownership. Authentication alone is not authorization.

At minimum:

```text
row.user_id == authenticated user id
```

Server-only relay and broker operations should use a private/service boundary and still validate the effective user/device/run relationship before mutating user state.

Never trust a browser-supplied `user_id` to choose ownership.

## Device enrollment

Recommended first version:

1. user signs into Meo Account on the device;
2. local `meo-agentd` asks Meo AI Cloud for an enrollment challenge;
3. user confirms the device in an authenticated Meo surface;
4. Cloud issues a device credential bound to user + device ID;
5. `meo-agentd` stores the device credential in an OS-appropriate secret store;
6. the daemon opens an outbound relay connection;
7. Cloud marks presence based on the live authenticated connection.

Do not store the user's general Meo Account refresh token as the long-lived daemon credential if a narrower device credential can be used.

## Device permission modes

Product-level modes:

### Ask

Every effectful tool action requires an explicit decision.

### Smart

Read-only and clearly reversible low-risk operations can proceed; destructive, privileged, external-publish, credential, install and similar actions require confirmation according to typed policy.

### Full Access

Only for explicitly trusted device/workspace contexts. It still does not bypass underlying OS/Router/Polkit authority.

These modes configure policy; they are not themselves security authority.

## Conversation portability

A conversation belongs to Meo AI Cloud, not one model and not one frontend.

A single conversation can contain responses from different executors:

```text
user
assistant via GPT
user
assistant via Claude
user
AgentRun on Legion
assistant summary
```

Web and Native clients should be able to reopen the same conversation.

Local AgentService conversation identity may be associated with a Cloud conversation as execution metadata, but Cloud identity remains stable if a local backend changes.

## Memory ownership

Memory is a later Meo AI Cloud contract, not provider-owned state.

Separate at least:

- user memory;
- project memory;
- conversation-pinned context;
- device context.

Providers receive only memory selected for a request and allowed by its data categories/grant.

## Deletion and sign-out

Signing out from a Web/Native client should stop that client's session but should not necessarily delete conversations.

Account deletion must eventually cascade or explicitly delete Meo AI cloud-owned rows while preserving only records legally/security-wise required and already designed for retention.

Revoking a device credential disconnects remote access without deleting the device's local files.

Deleting a conversation must not delete local source repositories or undo completed Agent effects.

## Cost model

Personal-use default:

- model inference paid by user's BYOK account;
- local Agent compute paid by user's own hardware;
- Meo Cloud pays only for auth-adjacent traffic, conversation metadata/storage, relay bandwidth and modest server processing.

This is why BYOK + local execution is the preferred architecture for the personal project.
