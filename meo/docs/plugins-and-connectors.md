> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

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

## Manifest v1 and lifecycle (MEO-030)

A manifest is a declarative description of one optional capability. It is defined and validated in
`core-rs/src/cloud/plugin_manifest.rs`; the built-in catalogue (`plugin_store.json`), the account's
installed-plugin records (Meo API) and the runtime lifecycle state stay three separate records.

Typed kinds: `provider_adapter`, `connector`, `skill`, `bundle`, `builtin`.

Fields: `manifest_version` (1), `id`, `version`, `name`, `description`, `publisher`
(`id`/`name`/`url`), `kind`, optional `compatibility` (`meo_core`, `meo_api` ranges), optional
`entrypoint`, `capabilities` (`id`, `input_schema`, `output_schema`, `surfaces`), `permissions`
(`data_categories`, `effects`), `network.origins`, `settings` (typed `text`/`number`/`boolean`/
`secret` fields with bounds), `ui` (`slot` + registered `renderer` id), `dependencies`,
`integrity` (`sha256:<64 hex>`), optional `signature`, optional `update_channel` (`stable`/`beta`).

Rules the validator enforces (unknown fields are errors, never ignored):

- A **Skill** is text: it may declare no capability, permission, origin, setting, UI contribution,
  entrypoint or dependency. Skill text is untrusted context, never policy or executable code.
- A **Bundle** exists to install others: it needs dependencies and has no capability or entrypoint.
- A **Connector** is a hosted service: it needs a hosted https entrypoint or declared https origin.
- A **Provider adapter** or **Builtin** is bundled in v1 and may not declare a remote entrypoint.
- Network origins are exact https origins (no path, query, fragment, userinfo or wildcard).
- **v1 loads no downloaded code.** There is no field for a script, archive or local path; an
  entrypoint that is not a hosted https service is rejected.
- `integrity` is required for distributed kinds; signatures are validated when present.

Lifecycle: `discovered → installed → connected/enabled`, with `unavailable`, `failed`, `disabled`
and terminal `removed`. Only `enabled` and `connected` accept calls; `disabled` and `removed` stop
new calls, and removing must not silently delete user data. Illegal transitions are rejected.

The manifest says what a plugin offers and asks for. It never grants anything: permission checks
happen per call, plugin enabled state is not authorization, and a manifest cannot approve its own
actions or bypass Account consent.

## The store page

Tabs: **Discover** (Essentials, Connect your services, built-in entries, MCP registry results, with
a search box and category filter), **Installed** (toggle, Connect/Reconnect/Disconnect, API token,
Remove), **Import** (a GitHub link to a `SKILL.md` or its folder, or the https address of a remote
MCP server). First-party entries carry an `icon`: a brand mark (`svg` path from simple-icons) or a
named glyph; entries without one get a letter tile.

## Servers on this computer (local MCP)

Not every service has a hosted MCP server. A local MCP server runs on the user's own computer as
their own user, and Meo reaches it over stdio. It is the only way to reach a service whose API is
local — a QQ bot (NapCat, LLOneBot, Lagrange expose OneBot on `127.0.0.1`), a home-automation hub,
a database.

Where it is configured: **Plugins > Installed > Servers on this computer**, next to the hosted
apps. Two ways to add one:

- **Add QQ (OneBot bridge)** adds the community bridge command with its address filled in; the
  access token goes in `ONEBOT_ACCESS_TOKEN` in the user's own file.
- **Add any server by its command** takes one command line, for example
  `uvx mcp-server-onebot`.

The file stays the source of truth (`$XDG_CONFIG_HOME/meo/mcp.json`, else
`~/.config/meo/mcp.json`), in the same shape Claude Desktop and [CC] use:

```json
{ "mcpServers": { "qq": { "command": "uvx", "args": ["mcp-server-onebot"],
                          "env": { "ONEBOT_HTTP_URL": "http://127.0.0.1:3000",
                                   "ONEBOT_ACCESS_TOKEN": "…" } } } }
```

A work folder's `.mcp.json` still overrides the user file by name. Editing through the app keeps
every other key in the file intact and writes beside the file, then renames, so a crash cannot
leave a half-written list.

Rules:

- **Nothing runs until Work calls it**, and only where a folder is open (desktop and the headless
  runner). The browser build has no local processes and does not show this section.
- A server runs as the user, so every call is a **command-level action** for the approval level:
  looking is free, acting follows the level. Its output is data, never instructions.
- A saved environment value may be a bot token. The card shows only the **fact** that a token is
  needed and the variable names — never a value — and the value is never rendered back to any
  client.
- **Check** starts the server once, lists the tools it reports and stops it, so "added" never
  reads as "working".
- Removing a server deletes only its entry in the user file; a folder file that defines the same
  name is left alone.

This is deliberately separate from manifest v1: a hosted connector declares an https origin, while
a local server is a process on the user's machine with a different trust model. Local servers are
not downloaded from the catalogue and cannot be installed by a manifest.

## Your own plugin indexes

The store ships a built-in catalogue and searches the public MCP registry. A user can also point
Meo AI at **their own index**: an https JSON document of data only, so a team or a community can
publish its own set without a Meo release.

Add it in **Plugins > Discover > Your sources**. Format (`version` must be `1`):

```json
{ "version": 1, "name": "My team",
  "entries": [
    { "id": "gh", "name": "GitHub", "description": "Repos", "kind": "mcp",
      "url": "https://api.githubcopilot.com/mcp/", "publisher": "meo" },
    { "id": "notes", "name": "How we write", "description": "Style", "kind": "skill",
      "skillUrl": "https://github.com/o/r/tree/main/skills/notes", "publisher": "me" }
  ] }
```

An entry is one of exactly two kinds:

- `mcp` with a public https `url` — installed like any hosted MCP server.
- `skill` with a `skillUrl` to a GitHub `SKILL.md` or its folder — read as text, never executed.

Rules:

- The index is fetched by **Meo API**, not the client, so its origin goes through the same SSRF
  guard as other user-supplied endpoints (public https only, no redirects, bounded body).
- The body is size-capped (512 KB, 200 entries) and validated. A bad entry is **reported, not
  trusted**: it is skipped with a reason and the rest of the index still loads.
- Nothing in an index is executable code. There is no field for a script, archive or local path;
  a `kind` other than `mcp`/`skill` is refused. This is why an index cannot install a DSH/Cordis
  plugin — those are code, and manifest v1 does not load downloaded code.
- One failing source is shown as failed and does not hide the others.
- The list of sources is a local, per-device preference (`~/.config/meo/plugin-indexes.json`),
  like the local MCP server list; the browser build has no file and shows none.

DSH's plugin ecosystem is Cordis packages that run inside DSH's own Node host; they cannot run in
Meo AI's Rust core. What both share is the MCP layer: an MCP server that DSH can connect to, Meo AI
can connect to as well (hosted or local stdio), and a Skill is plain text either way.

## Where it is managed

Everything about apps, skills and MCP servers lives on the **Plugins** page (Discover, Installed,
Import): install, switch on/off, sign in, sign in again, disconnect, remove, and see what each app may
do. **Settings > Permissions** holds only what applies to everything: the default approval level and
how approvals work, with a button that opens Plugins.

## Connecting an app

Installing an app does not sign you in anywhere by itself. Every installed card shows a status dot and
the button that fixes it. One function (`app_auth`) decides the state, so the badge, the dot and the
buttons always agree:

| State | Meaning | Primary button |
| --- | --- | --- |
| Connected | A sign-in is stored and has not been rejected | none (Reconnect stays available, quiet) |
| Not connected / Account not linked | Never signed in | Connect / Connect GitHub |
| Sign-in expired | Stored, but the service rejected it at use (expired, revoked, more access needed) | Reconnect |
| Needs sign-in (not supported yet) | A server Meo AI cannot sign in to answered that it needs it | none, and it says so |

A failed tool listing or tool call with an authorization error flips the card to *Sign-in expired* and
raises a notice with the Reconnect button. After you were sent to authorize, coming back to the window
reads the apps again and says "X is connected." (or use **Check again**). Turning on an app that is not
connected offers Connect. A new account with no apps is offered the Essentials bundle once.

Discover shows the same state on an installed app's card (its badge, a *Tools unavailable* badge when its tools could not be read, and the same primary Connect/Reconnect button) plus a **Manage** button that opens Installed, so "Installed" never reads as "working". A failed tool listing also puts the reason on the card.

Each connected card lists what the app may do: *Runs on its own* (list/get/search/read/fetch tools) and
*Asks first* (everything else), following the composer's Permissions.

| App | Connect button does |
| --- | --- |
| Cloudflare, Supabase, Neon, Linear, Notion, Vercel, Figma, Hugging Face, Canva, Dropbox, Zapier | Opens the service's own authorization page (OAuth with PKCE); the grant is saved encrypted in Meo API and refreshed automatically. |
| Cloudflare, Supabase, Neon | Also: **API token** to paste a token instead. |
| GitHub, Google Drive | Opens Meo Account (sign-in methods) where you link or re-grant that account; Meo API uses the linked account's token. |
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
