# Account-synced Plugins, MCP & Skills (Meo AI)

Status: account-owned configuration and **text-only selected Skill guidance** implemented in code; database migration + production Worker/Web deployment and live cross-device QA are **not** performed by this change. A saved remote MCP endpoint is not proof of an active connection.

## Ownership

- Meo Account (Better Auth): identity, sessions, revocation, future per-provider OAuth grants/encrypted credential vault.
- Meo API (Worker, AI Neon DB): user-owned plugin records + bundled text Skills, versioned CRUD and read access.
- Meo AI (desktop / web / Android): feature entry points; an explicit Skill chooser; future capability broker.
- MeoUI: visual tokens and reusable Qt/QML controls, not a cloud database or credential authority.

Each plugin has exactly one account owner. The plugin's `skills` is a **one-to-many relationship**, with up to 32 Skill documents per plugin and up to 100 plugins per user (initial limits).

### Persistence

Migration: `meo-api/migrations/ai/0012_account_plugins_and_skills.sql`.

Routes exposed through `meo-api`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/v1/ai/plugins` | List account plugins and enabled Skill metadata |
| POST | `/v1/ai/plugins` | Create plugin with optional initial Skills |
| GET | `/v1/ai/plugins/:id` | Fetch one plugin and full Skill text |
| PATCH | `/v1/ai/plugins/:id` | Rename, describe, or enable plugin; version-checked |
| PUT | `/v1/ai/plugins/:id/skills` | Atomically replace saved Skill set; version-checked |
| DELETE | `/v1/ai/plugins/:id?expectedVersion=N` | Delete plugin and its Skills |

Web BFF: `meo-ai/meo/web/client/functions/api/meo/[[path]].js`; public web clients must use account-authenticated API, never direct database credentials. The AI database stores `user_id` as the account UUID without cloning account PII.

The `enabled` flag makes Skill guidance eligible for explicit selection; **it does not provide MCP tool authority**.

### Chat use (implemented in code)

1. Enable a plugin and its desired Skill(s) in the Skills page or Settings → Apps & Connectors.
2. Select a Skill in the Chat toolbar; `No skill` is the default.
3. Chat sends `skillId` to both `/v1/chat/prepare` and `/v1/chat/stream`.
4. Server verifies the requested Skill belongs to the authenticated account and both Skill + plugin are enabled. A missing/disabled/foreign Skill returns `skill_unavailable`.
5. The Skill's text joins user-authored reference context. It is **not** a system policy, a privileged command, or automatically executed code.
6. Chat prepare and execution use the same Skill selection; changes between them must remain subject to the existing inference-consent checks.

This is selected text-only Skills. It is **not** complete Agent Skills support for bundled scripts, references, arbitrary executable assets, or Skills loaded dynamically at runtime.

### Future MCP runtime / capability broker (not implemented)

```text
Meo AI Chat / Work (explicit selected tool)
  → Meo API (account auth, capability consent, chosen execution target)
  → MCP broker (registry metadata, tool schema discovery, rate limiting)
  → Remote HTTPS Streamable HTTP MCP server OR enrolled local AgentService
  → Permissions (read/write level, resource allowlist, confirmation, audit)
  → Validated tool result and provenance, streamed back to Chat / Work
```

- No remote MCP URL may grant unrestricted local filesystem / shell access.
- MCP endpoints: block DNS rebinding, private/reserved resolved IPs, redirects to private networks, oversized responses, and excessive timeouts. SSRF protection must happen **at execution time**, not only when storing the URL.
- OAuth tokens are encrypted Account-owned secrets, never `manifest`, `skills`, browser LocalStorage, chat messages, logs or sync payloads.
- Local `stdio` MCP servers require a signed-in target device with a local sandbox; web clients cannot execute local commands.
- Capability scopes, consent and revocation are server/runtime enforced, never decided by a prompt or `SKILL.md`.
- A remote device being offline must show `unavailable`, not silently run on another machine.
- Work tasks reuse authenticated resumable AgentRuns instead of introducing a second agent engine.
- Tool schema discovery and invocations need separate authorization and audit; never expose generic arbitrary HTTP fetch or command execution from a user-supplied manifest.

## Discovery sources

- Official MCP Registry: https://registry.modelcontextprotocol.io/ (server metadata, not a guarantee that a remote endpoint is callable). Registry API: `https://registry.modelcontextprotocol.io/v0.1/servers`. Respect paging and source metadata.
- Smithery: https://smithery.ai/servers (third-party directory; review verified/publisher information).
- skills.sh: https://skills.sh (Agent Skills, including multi-Skill Packs; packs may contain private Skill sources). Source format is `SKILL.md`, with optional references/scripts/assets.

Current UI links to official Registry and skills.sh for manual discovery. **One-click catalog install/import, registry search within Meo AI and automatic updates are not yet wired.** Do not copy or execute third-party Skills until source, license, version and any script privileges have been reviewed.

## Release/QA checklist

1. Review API/UI code + security model and production DB access grants.
2. Run the **authorized** migration with environment-based connection strings; do not post or commit URLs, keys or passwords.
3. Deploy Meo API + unified Meo AI client by the normal production pipeline.
4. Sign in on two separate devices with the same Meo Account; create a plugin and 2 Skills on device A, confirm device B can read them; edit on B and confirm A reloads changes.
5. Test isolation: account B cannot GET, modify, use or delete account A's plugin/Skill IDs.
6. Test disabled Skills, disabled plugins, invalid input, duplicate Skill names, URL restrictions, size limits and conflict responses (HTTP 409).
7. Test Chat explicit Skill invocation with prepare/stream consent, switch Skill mid-session, and delete while selected. Verify no user-controlled Skill can acquire system permissions.
8. Keep true MCP tool execution marked **not connected** until an audited capability executor is shipped and integration-tested.
