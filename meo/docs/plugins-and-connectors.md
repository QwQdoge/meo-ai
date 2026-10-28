# Apps & Skills: plugins, connectors, skills

This is how Meo AI's plugin store works end to end. The core (`core-rs/src/cloud`) owns all of it;
the web, desktop and Android clients only draw the page the core describes (see
[cloud-core-view.md](cloud-core-view.md), "Store page") and send actions back.

## What can be installed

| Kind | What it is | Where it comes from |
| --- | --- | --- |
| Connector (MCP) | A hosted MCP server the model can call as a tool: GitHub, Cloudflare, Supabase, Neon, Google Drive, Linear, Notion, Vercel, Figma, Hugging Face, Canva, Dropbox, Zapier, plus read-only docs servers. | `core-rs/src/cloud/plugin_store.json`, the public MCP registry (searched in Discover), or an address you paste in Import. |
| Skill | Instructions the model follows (a `SKILL.md`). | Inline in the store file, or fetched from any public GitHub repository when you install or import it. |
| Bundle | Several skills and/or a connector in one install. The **Meo Essentials** bundle holds the file-generation rules, Anthropic's docx/xlsx/pdf/web-artifacts/frontend-design skills and Vercel's web-design and React skills. | `plugin_store.json`. |

OneDrive is listed as "Coming soon": Microsoft has no hosted MCP server to connect yet.

## The store page

Tabs: **Discover** (Essentials, Connect your services, built-in entries, MCP registry results, with
a search box and category filter), **Installed** (toggle, Connect/Reconnect/Disconnect, API token,
Remove), **Import** (a GitHub link to a `SKILL.md` or its folder, or the https address of a remote
MCP server). First-party entries carry an `icon`: a brand mark (`svg` path from simple-icons) or a
named glyph; entries without one get a letter tile.

## Connecting an app

Installing an app does not sign you in anywhere by itself. Installed cards show **Connected** or
**Not connected** and the button that fixes it:

| App | Connect button does |
| --- | --- |
| Cloudflare, Supabase, Neon, Linear, Notion, Vercel, Figma, Hugging Face, Canva, Dropbox, Zapier | Opens the service's own authorization page (OAuth with PKCE); the grant is saved encrypted in Meo API and refreshed automatically. Installing starts this right away. |
| Cloudflare, Supabase, Neon | Also: **API token** to paste a token instead. |
| GitHub, Google Drive | Opens Meo Account (sign-in methods) where you link that account; Meo API uses the linked account's token. |
| Docs servers | Nothing to connect. |

## How the model uses an app

1. Before each message the core lists the tools of every enabled, hosted app (all at once, cached
   until the plugin list reloads; failures are cached too and named with what to do).
2. The tool instructions gain a **Connected apps** list and one tool: `app {app, name, args}`.
   This works in Chat and Work, with or without an open folder.
3. The model ends a reply with a ` ```meo-tool ` block; the core asks (or not) according to the
   permission mode. Tools whose names start with `list_`, `get_`, `describe_`, `search`, `read_`,
   `fetch` or `explain_` are treated as read-only and run without asking; everything else asks like
   a command.
4. The core calls Meo API (`tools/prepare`, then `tools/call`); the result comes back to the model
   as data, never as instructions.
5. If the message names an enabled app (for example "Neon"), the automatic web search is skipped so
   the model uses the app instead of searching the name.

Failures are reported with a fix: not linked, no token, credential rejected, or "Meo API has not
allowed this server or tool".

## Server policy (operator)

Meo API is default-deny. A server needs an entry in `MEO_MCP_TRUSTED_ENDPOINTS`, tool patterns in
`MEO_MCP_ALLOWED_TOOLS` and, for standing consent, `MEO_MCP_READ_ONLY_TOOLS`. See meo-api
`docs/api-reference.md`, "Hosted MCP servers". To add a connector:

1. Check it answers `401` with protected-resource metadata and supports dynamic client registration.
2. Add its authorization server and scopes to `SERVERS` in meo-api `src/mcp-oauth.ts`.
3. Add the endpoint and tool patterns to `wrangler.jsonc`, deploy meo-api.
4. Add an entry (with `icon`, `skills`, `"oauth": true`) to `plugin_store.json` and the endpoint to
   `OAUTH_ENDPOINTS` in `app.rs` so the card shows Connect.

## Skills

A skill is stored as text on your account and sent with your requests while it is enabled. Imported
skills come from a third party: read them first. Scripts inside a skill are never executed by Meo
API; the Work runner on your own computer is the only place commands run.

## Local development

- Core tests: `cargo test --features "client cloud" --lib` in `meo/core-rs`.
- Desktop (macOS): needs Qt 6.9+ (Homebrew `qt`), MeoUI built against it, and
  `CXXFLAGS="-include arm_acle.h" MACOSX_DEPLOYMENT_TARGET=14.0`; see `desktop-rs/`.
- Web: the core is compiled to WASM only by the "Meo Web client" workflow; deploy its
  `meo-web-site` artifact with `wrangler pages deploy`.

## Not done yet

OneDrive (no hosted server), Google/GitHub in-place linking from the store (it opens Meo Account),
desktop and Android have not been exercised with live connectors, and the store has no ratings or
updates for installed skills.
