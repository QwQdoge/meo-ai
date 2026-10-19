# Account-synced Plugins, MCP & Skills (Meo AI)

Status: account-owned configuration, text-only selected Skill guidance, MCP Registry search, manual GitHub SKILL.md import, and an operator-pinned remote MCP execution preview are implemented **in code**. Production DB migrations, Worker/Web deployment, OAuth authorization, native device parity and live cross-device QA are **not completed**. A saved endpoint is not proof of a live or authorized connection.

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
| GET | `/v1/ai/catalog/mcp?q=search` | Server-side, bounded official MCP Registry search |
| GET | `/v1/ai/catalog/github-skill?owner=...&repo=...&ref=...&path=.../SKILL.md` | Safe single-file public Skill preview |
| GET | `/v1/ai/plugins/:id/tools` | Discover tools only from operator-pinned HTTPS MCP endpoints |
| POST | `/v1/ai/plugins/:id/tools/call` | Explicit one-off MCP tool call with account authorization and confirmation |

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

### Remote MCP runtime preview (limited, implemented in code)

The Meo API includes a small Streamable HTTP JSON-RPC client with:
- MCP `initialize` handshake, `notifications/initialized`, session headers, `tools/list`, and `tools/call`.
- Bounded responses, short timeouts, manual redirects disabled, JSON and SSE response parsing.
- Account ownership and enablement checks for every operation.
- Every tool call is explicitly chosen and confirmed in the UI; model-driven autonomous tool calling is NOT implemented.
- No OAuth, third-party headers/credentials, local stdio/CLI tools, legacy SSE fallback, prompts/resources, binary results, or long-running/resumable MCP sessions.
- Protocol preview targets `2025-06-18`; servers negotiating other versions may not work. For broader protocol support the maintained MCP SDK is preferred in a future integration.
- Tool results are untrusted output and never become privileged instructions.

**Default-deny:** server execution requires the optional Cloudflare Worker env variable `MEO_MCP_TRUSTED_ENDPOINTS`, containing a comma-separated list of exact HTTPS endpoint URLs (including paths). Without this server-operator setting, tool discovery/calls fail with `mcp_endpoint_not_trusted` while saving/syncing the plugin still works. Do not expose this variable as an API parameter or let ordinary users modify it.

This strict pin list is a temporary beta guard, not a scalable OAuth/SSRF isolation architecture. A production-general plugin runner must use a dedicated, auditable egress authority capable of DNS resolution/private-range controls, origin constraints, redirect review, connection isolation, per-tool permission grants, usage limits and server-backed user approvals. Until that exists, arbitrary user-entered MCP endpoints remain **storage-only**.

#### Future Chat/Work capability broker (not yet implemented)

```text
Meo AI Chat / Work (explicit selected tool)
  → Meo API (account auth, capability consent, chosen execution target)
  → MCP broker (registry metadata, tool schema discovery, rate limiting)
  → Remote HTTPS Streamable HTTP MCP server OR enrolled local AgentService
  → Permissions (read/write level, resource allowlist, confirmation, audit)
  → Validated tool result and provenance, streamed back to Chat / Work
```

- No remote MCP URL may grant unrestricted local filesystem or shell access.
- OAuth tokens belong in encrypted Account-owned secrets, never `manifest`, `skills`, browser LocalStorage, chat messages, logs or ordinary sync payloads.
- Local `stdio` MCP servers require a signed-in target device with a sandbox; Web cannot execute local commands.
- Capability scopes, consent and revocation must be enforced by trusted server/runtime code, not prompts or `SKILL.md`.
- An offline remote device must be shown as unavailable. Work uses authenticated resumable AgentRuns, not a second agent engine.
- The beta `confirmation: run_once` API field is a UI intent signal, **not** proof of human approval against a malicious authenticated client. Do not rely on it for powerful privileges without server-issued, single-use approvals.

## Discovery sources

- Official MCP Registry: https://registry.modelcontextprotocol.io/ (server metadata, not a guarantee that a remote endpoint is callable). Registry API: `https://registry.modelcontextprotocol.io/v0.1/servers`. Respect paging and source metadata.
- Smithery: https://smithery.ai/servers (third-party directory; review verified/publisher information).
- skills.sh: https://skills.sh (Agent Skills, including multi-Skill Packs; packs may contain private Skill sources). Source format is `SKILL.md`, with optional references/scripts/assets.

The UI now searches the official Registry by name, shows package-only or template/authorization-dependent entries as manual setup, and can save compatible HTTPS Streamable HTTP endpoint metadata **disabled by default**. It can also preview one public GitHub `SKILL.md` and import only that text as a new Skill pack or an existing plugin's draft. It never imports scripts or auxiliary assets.

skills.sh currently documents a Vercel OIDC-authenticated API. As Meo API runs on Cloudflare, its API cannot be assumed anonymously available. The UI therefore links to skills.sh for manual browsing and uses fixed-origin public GitHub previews for imports. Smithery is also a directory link, not a configured execution broker. Automated package installation, registry publisher verification, updates, full Skills packs, auditing and OAuth remain future work. Catalog listings are **not** security trust labels.

## Release/QA checklist

1. Review API/UI code + security model and production DB access grants.
2. Run the **authorized** migration with environment-based connection strings; do not post or commit URLs, keys or passwords.
3. Deploy Meo API + unified Meo AI client by the normal production pipeline.
4. Sign in on two separate devices with the same Meo Account; create a plugin and 2 Skills on device A, confirm device B can read them; edit on B and confirm A reloads changes.
5. Test isolation: account B cannot GET, modify, use or delete account A's plugin/Skill IDs.
6. Test disabled Skills, disabled plugins, invalid input, duplicate Skill names, URL restrictions, size limits and conflict responses (HTTP 409).
7. Test Chat explicit Skill invocation with prepare/stream consent, switch Skill mid-session, and delete while selected. Verify no user-controlled Skill can acquire system permissions.
8. Validate fixed-origin catalog and SKILL.md import against GitHub Actions mock tests; separately test the remote MCP preview with an operator-pinned, controlled test endpoint.
9. Confirm untrusted custom MCP URLs and all endpoints without server pins fail closed; test tool-by-tool confirmation, session transport, JSON/SSE parsing, redirects, sizes and external auth rejection.
10. Verify the production Worker actually has required schema and explicit `MEO_MCP_TRUSTED_ENDPOINTS` before marking any MCP tool reachable. No automatic model tool execution is implied.
