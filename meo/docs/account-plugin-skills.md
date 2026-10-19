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
| POST | `/v1/ai/plugins/:id/tools/prepare` | Validate selected tool, generate short-lived server-side request bound to account and session |
| POST | `/v1/ai/plugins/:id/tools/call` | Atomically consume matching one-time approval before calling remote MCP |

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
- Every tool call is explicitly selected and reviewed in the UI; model-driven autonomous tool calling is NOT implemented.
- Requests have a **server-owned** 3-minute approval with user UUID, session UUID, plugin ID, tool name, arguments SHA-256 and endpoint SHA-256. No plaintext arguments are stored in the approval table.
- `call` atomically claims that matching request, checks plugin enablement and endpoint integrity, and marks outcome. Approval cannot be reused, even after timeout (remote side effects may have occurred).
- Prepared requests are bound to browser sessions during this beta; native/bearer calls need a separate designed approval UI and security review.
- Web plugin libraries refresh on tab return/focus, while keeping unsaved local Skill drafts intact.
- No OAuth, third-party headers/credentials, local stdio/CLI tools, legacy SSE fallback, prompts/resources, binary results, or long-running/resumable MCP sessions.
- Protocol preview targets `2025-06-18`; servers negotiating other versions may not work. For broader protocol support the maintained MCP SDK is preferred in a future integration.
- Tool results are untrusted output and never become privileged instructions.

**Default-deny (two layers):**

1. `MEO_MCP_TRUSTED_ENDPOINTS`: optional server/operator Cloudflare variable with comma-separated exact HTTPS MCP endpoints (including paths).
2. `MEO_MCP_ALLOWED_TOOLS`: optional server/operator JSON object mapping exact endpoint URLs to arrays of explicitly permitted tool names. Example (illustrative only): `{"https://trusted.example/mcp":["search","get_issue"]}`.

Both settings must permit a tool. Unlisted tool names return `mcp_tool_not_authorized`; missing tool policy returns `mcp_tool_policy_missing`. Listings only show approved tool names. Normal account users cannot add server pins or modify this policy via API. Do not put third-party secrets into either setting.

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
- The previous `confirmation: run_once` shortcut was removed. The new server-side approval is a single-use replay/parameter guard, **not cryptographic proof that a human clicked the UI**: an attacker with a valid browser session can still issue a prepare and a call. High-impact privileges require a separate authenticated reauthentication/approval authority and tighter scoped grants before release.
- Approval migration: `meo-api/migrations/ai/0013_mcp_tool_approvals.sql`. Its state must be present in `/v1/ready` before declaring the deployment healthy.

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
9. Confirm untrusted custom MCP URLs, endpoints without server pins, and tools without explicit policy all fail closed. Test one-time grants against account/session replay, changed args, expiry, disabled plugins, session transport, JSON/SSE parsing, redirects, sizes and external auth rejection.
10. Verify production schema includes migrations 0012 and 0013 and the operator explicitly configured both `MEO_MCP_TRUSTED_ENDPOINTS` and `MEO_MCP_ALLOWED_TOOLS` before marking any tool reachable. No automatic model tool execution is implied.
