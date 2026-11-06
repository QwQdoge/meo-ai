> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

## Workflow rules from the owner (override anything below)

- Commit directly on the repository's current/default branch (`main` unless the repo is deliberately on another working branch). Do not create feature branches or PR branches unless asked.
- After committing, push immediately. Do not ask for permission to commit or push, and do not leave finished work uncommitted or unpushed.
- Keep verification minimal: run only the quick check for the touched code (typecheck or the one relevant test). Do not run full suites or write extra tests unless asked.
- Do the whole task in one pass; do not stop to ask routine questions that have an obvious default.
- Never put secrets, tokens or credentials in code, logs or commits.

## MeoUI specification (read before UI work)

- People: https://meoarch.org/docs/ . Agents: https://meoarch.org/llms.txt , then the Markdown pages it lists; start with https://meoarch.org/docs/meoui/for-agents.md (decision tables and checklists).
- Window chrome and toolbar, where app settings live and their categories, About, and open-source credits: https://meoarch.org/docs/meoui/app-shell.md .
- The canonical source is MeoUI `docs/design/`; the site is generated from it. If they disagree, MeoUI wins. Propose rule changes there, not in this repository.

# Meo AI contributor rules

Meo AI is one product (Chat, Work, Projects, Skills) across Web, Linux/Windows/macOS
desktop and Android. This repository is a fork of `qwersyk/Newelle`: preserve its
provenance and GPL-3.0 license. Read `docs/ownership.md` before changing layout,
the Newelle-derived root tree, compatibility adapters, packaging or the legacy split.

## Current direction (user decision 2026-10-20): cloud-first, one core

- Every client renders the view produced by `meo/core-rs/src/cloud/` (`AppCore`):
  account sign-in, Meo API calls, local cache, navigation/pages/settings and buttons.
  Clients send back the action object attached to each element; they hold no product
  logic. New pages, sections, settings or buttons belong in the core so all clients
  update without UI edits. View contract: `meo/docs/cloud-core-view.md`.
- Desktop is `meo/desktop-rs` (Rust + QtBridge + MeoUI QML generic renderer).
  Android binds the same core through JNI; Web through WASM.
- One Meo Account: provider keys live in Account/Meo API; the core only selects
  credential + model. Login reuses the cached refresh token, otherwise opens the
  browser (desktop client `meo-ai-native`, redirect `meoai://auth/callback`).
- **Paused (not used, do not extend):** local AgentService/Python (`meo/service`,
  `meo/runtime`, `meo/system`, `meo/adapters`), the C++ desktop client `meo/app`,
  local/remote device Work (`meo/cloud`, `meo/device`) and the Newelle tree. They stay
  in the repository until removed deliberately. Repair moves into the core + QML later.

## UI direction (user decision 2026-10-21)

Use the Claude desktop layout instead of designing our own: sidebar with a large Chat | Work
switch, search, prominent New chat, Plugins, Projects tree and chats; chat area with a
growing composer, controls row (permission, model, thinking, sub-agents) and a details card.
Spec, status and TODO: `meo/docs/ui-redesign.md`. Product structure goes in the core view;
the three renderers stay identical.

## Repository map

| Path | Role | Authority |
| --- | --- | --- |
| `meo/core-rs/` | Rust protocol, ContentBlocks, provider/stream/context/capability core | **Authoritative** shared core |
| `meo/ui-schema/` | Navigation, pages, features, settings, token aliases + generator | **Authoritative** product UI configuration |
| `meo/app/` | Desktop C++/Qt/QML + MeoUI client | Presentation + platform integration |
| `meo/web/client/` | React/TypeScript Web client + thin Pages edge (has its own `AGENTS.md`) | Presentation |
| `meo/android/` | Kotlin/Compose client over Rust (JNI) | Presentation |
| `meo/cloud/`, `meo/device/` | Remote AgentRun, device enrollment/relay to local AgentService | Compatibility; moving to Rust |
| `meo/service/`, `meo/runtime/`, `meo/system/`, `meo/adapters/` | Python AgentService, Router client, Newelle adapters | Compatibility; no new product architecture |
| `meo/skills/`, `meo/prompts/`, `meo/usage/` | Bundled Skills, prompts, usage import | Data / tools |
| `src/`, `modules/`, Meson/Flatpak files, `po/` | Newelle-derived engine | Compatibility only; patch through documented seams |

External authorities (never re-implemented here):

- **Meo API** (`QwQdoge/meo-api`, `api.meoarch.org`): cloud business entry — conversations,
  projects, memory, plugins/Skills, AgentRun, model broker; server-side authorization.
- **Meo Account** (`QwQdoge/MeoArch-account`, `account.meoarch.org`): identity, OAuth,
  sessions, encrypted BYOK. No second key store in Meo AI.
- **System AI Router** (`MeoArch-os-workspace/ai-router`, D-Bus `org.meo.AIRouter1` in
  `meo-kde/native/airouter`): typed privileged system capabilities, confirmation, Polkit.
- **MeoUI**: shared controls and token values. `ui-schema` references them, never copies them.
- **Packaging**: `meo-repo/packages/meo-ai`; ISO integration in `MeoArch-os-workspace`.

## Change rules

- New cross-platform behavior starts in the Rust/API contract, then is rendered in QML,
  Compose and React. A frontend-only feature that invents semantics is incomplete.
- Do not add a new provider, message type, tool state machine, sync feature, router,
  resource format or reconnect rule only to Python/C++. Python/C++ AI logic changes are
  limited to keeping a release working, adapters, unsafe-to-wait fixes and parity tests.
- Desktop stays C++/Qt/QML; replacing it with Rust UI bindings is not a goal.
- Navigation/settings placement, order and labels live in `meo/ui-schema/`; regenerate
  consumers instead of hard-coding them in a renderer.
- Prompts, Skills, MCP descriptions and UI Schema data are never security enforcement and
  never grant capabilities.
- Do not move/delete the Newelle tree as incidental cleanup; the split gates are in
  `docs/ownership.md`. Do not delete GTK while the core still imports Gtk/Adw/WebKit.

## Headless and system boundaries

- `meo/service/` and `meo/system/` must not import GTK, Adwaita, WebKit, `src.ui` or
  `src.ui_controller` (checked by `meo/tools/check_headless_imports.py`).
- Temporary Newelle wrappers belong in `meo/adapters/` and must not leak UI objects into
  service APIs.
- Frontends/transports never own request IDs, decision IDs or execution handles.
- SystemTool may call the typed `org.meo.AIRouter1` API, but Router daemon/executor
  ownership, KIO/PulseAudioQt/KWin integrations, Polkit and Repair authority stay out of
  this repository. Router caller binding requires Submit/Get/DecideRequest to reuse one
  session-bus connection; do not replace it with per-call subprocesses.

## Web, cloud and device

- `meo/web/` owns Web integration/upstream policy, never raw provider keys. The old
  `meo-ai-web` repository was deleted on 2026-11-04 (GitHub and local); do not recreate its
  Express/Mongo backend. Any Web deployment must be built from `meo/web/client`.
- `meo/cloud/` owns AI conversation/device/AgentRun contracts; Meo Account remains the
  authentication/session and BYOK authority.
- `meo/device/` bridges authenticated remote work to the local AgentService. It must not
  become a second agent engine, an unauthenticated remote shell or a Router replacement.
- One remote AgentRun binds to at most one local AgentService request; reconnect resumes
  that request/event stream and never submits a replacement (no duplicated side effects).
- Local workspaces stay local unless an explicit upload path says otherwise. Account login
  never silently uploads local projects, memories or workspaces.
- Realtime sync (e.g. Neon Realtime) is a future enhancement: stream tokens over the API
  transport (SSE), persist completed state, fan out only durable changes, keep fallback.

## Product and navigation

- Primary hierarchy is `Chat`, `Work`, `Projects`, `Skills` — task surfaces, not settings.
  Compact/mobile layouts use the same hierarchy in a left drawer (hamburger or edge swipe);
  no separate bottom-navigation model.
- `Chat` is conversation. `Work` is agentic execution with an explicit target device,
  visible progress, permission boundaries and resumable state. Never silently turn Chat
  into Work. Chat and Work share one activity UI contract, not one execution engine.
- `Projects` own persistent context/files/conversations; `Skills` own reusable visible
  capabilities. Provider config, model routing, memory management, MCP, diagnostics,
  account and connector administration belong in Settings.
- Attachments belong to a Chat, project files to a Project, Work outputs to Work artifacts.
- Desktop is the strongest local Work executor; Android has fewer local capabilities and is
  a first-class remote controller; Web never pretends to have local-machine privileges.
- Remote control requires authenticated device registration, revocable per-device sessions,
  scoped capabilities, visible target selection and explicit approval for privileged work.
- Connectors (official, MCP, plugin, Router provider) share one capability/permission model
  and receive brokered capabilities, not long-lived third-party tokens.
- Account: one-time device authorization, then silent refresh until logout/revocation/expiry.
  Secrets go to the platform secure store, never ordinary config files.
- Visual direction: restrained Pixel/Material — information first, quiet surfaces, limited
  accents, subtle motion, system reduced motion. Share protocol, data models and tokens; do
  not force one renderer.

## Context and token budget

- `meo/service/context_engine.py` owns provider-agnostic context selection (moving to
  `core-rs/src/context.rs`); keep provider SDKs, storage and UI outside the strategy.
- Raw messages and tool results are authoritative. Compaction is model-facing and
  non-destructive; every compacted tool result keeps a stable raw source reference.
- Keep recent turns verbatim when budget permits; rank older evidence by relevance, recency
  and importance; expand when selection confidence is low.
- Memory and transcript history are different data classes; structured task memory keeps
  source references and obeys user memory controls.
- Serialize static instructions/tool schemas deterministically, separate from dynamic
  context, so prompt caches hit. No timestamps/random IDs in the static prefix.
- Terse output only for internal planner/executor/subagent handoffs, never the final reply.
- Context diagnostics are aggregate-only (counts, ratios, strategy, confidence); never expose
  system prompts, private memory or raw tool output.
- New compression algorithms (TOMC, LCC, …) implement the strategy abstraction; check
  licenses before vendoring. Legacy backends that build history internally must not claim
  Meo context savings.
- Context tests cover recent-turn preservation, relevant-old-item selection, compaction raw
  refs, low-confidence fallback, diagnostic privacy and the terse-mode guard.

## Validation

Run the narrowest set for what changed (mirrors `.github/workflows/`):

| Area | Commands |
| --- | --- |
| Python compat | `python3 -m compileall -q src meo/service meo/system meo/adapters meo/runtime meo/tools meo/device`; `python3 meo/tools/check_headless_imports.py`; `python3 -m meo.runtime.main --self-check`; `python3 -m unittest discover -s meo/tests -p 'test_*.py' -v` |
| Desktop | `cmake -S meo -B build/meo -DMEO_UI_ROOT="${MEO_UI_ROOT:-$PWD/../meo-ui}" -DBUILD_TESTING=ON`; `cmake --build build/meo --parallel 2`; `QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software ctest --test-dir build/meo --output-on-failure --timeout 60` |
| Rust core | in `meo/core-rs`: `cargo fmt --check`; `cargo clippy --locked --all-features --all-targets -- -D warnings`; `cargo test --locked --all-features` |
| UI Schema | `node meo/ui-schema/generate.mjs --check` |
| Web | in `meo/web/client`: `npm ci`; `npm run typecheck`; `npm test`; `npm run build` |
| Android | in `meo/android`: `./gradlew :app:assembleDebug` |
| Windows | `.github/workflows/release-windows.yml` (MSVC + Qt 6.9.1, `vpk pack`); the installed app updates from GitHub pre-releases (`desktop-rs/src/updater.rs`) |
| Release | `.github/workflows/release.yml` builds Windows (installer + portable zip) and Android, attaches them to one Beta GitHub Release (draft unless `publish`); Linux goes through `meo-repo` |

Report mock/protocol tests, builds, real provider/agent execution, live OAuth, real devices
and live Plasma separately. No release, tag, signing or deployment is implied.

## Git and files

- This is a fork: open PRs with `gh pr create -R QwQdoge/meo-ai` (never upstream Newelle).
- Inspect `git status` and the nearest code/tests first; preserve unrelated work.
- Plans, audits and decisions go to `$MEO_DOCS_ROOT/Projects/meo-ai/`; generated output to
  `$MEO_OUTPUT_ROOT/meo-ai/{build,install,validation,packages,tmp}/`. Code-bound contracts
  stay in `docs/` and `meo/docs/`.

## MeoArch documentation map

- Docs site: https://meoarch.org/docs/ (MeoUI specification: app shell, settings pattern, page types, dynamic color, API lifecycle, localization). Agent entry points: https://meoarch.org/llms.txt and https://meoarch.org/docs/meoui/for-agents.md. The canonical source is the MeoUI repository `docs/`; if they disagree, the repository wins.
- Packaging and releases: https://github.com/QwQdoge/meo-repo - read its `AGENTS.md`, `docs/MEOARCH_IMPLEMENTATION_RUNBOOK.md`, `manifests/{beta,stable}/` and the "MeoArch repository release" workflow (https://github.com/QwQdoge/meo-repo/actions/workflows/release.yml).
- Release approval: the `sign-and-publish` and AUR jobs wait on the protected `release` Environment. After the owner confirms in chat, agents approve with `gh api -X POST repos/QwQdoge/meo-repo/actions/runs/<run>/pending_deployments -F environment_ids[]=<id> -f state=approved` (details in meo-repo `AGENTS.md`); the owner can also use Actions -> "Review deployments" -> `release`.
- Before tagging a component for release: its source archive must extract cleanly (no tracked build output such as `target/`, no absolute symlinks) and its CI must be green; tag the newest green commit.
- Other repositories: MeoUI (design system), meo-kde (Plasma shell), meo-ai (Meo AI), meo-api (cloud API), MeoArch-account (account app), MeoSettings, MeoArch-os-workspace (ISO/installer/repair), OmniStore, meo-login-manager, meo-repo (packages), meoarch-site (meoarch.org).

## Shared workspace rules (owner)

Source: the owner's local `projects/agent.md`, repeated here on purpose. These rules apply to every repository and win over generic caution in the rest of this file.

- "All repositories" means: the `projects` folder inside WSL Arch (`~/projects`), the Windows `projects` folder, and whatever `gh repo list QwQdoge` shows; confirm with `gh`.
- Reading a repository: `git pull` and `git push` first so it matches the cloud. If there are open PRs/branches, merge all of them. If a branch is large or needs a decision, ask once, then merge everything without asking again before each merge; after merging, ask whether to run tests. Exceptions: old dependency-bump branches and branches that are clearly unneeded.
- Work: update dependencies to the newest versions dynamically; only if a bug survives a real fix attempt, roll back and tell the user. Never create working branches: one shared workspace on the default branch, kept tidy. Push every piece of work to the cloud right away; always `git pull` then `git push`, no delay.
- Ask the user as little as possible: anything solvable by a simple attempt, or that matches the user's stated wishes, is done without asking. Ask only after repeated real attempts show the goal cannot be reached.
- Read every relevant document before working: local ones and https://meoarch.org/docs/ (agent entry: https://meoarch.org/llms.txt).
- Releases the owner asks for are authorized end to end (tag, manifest, dispatch, approve via `gh api .../pending_deployments`); do not stop for extra approvals.
- Never write personal or machine-specific details (usernames, absolute local paths, emails, VM or machine layout, secrets, resource ids) into repositories or published docs; keep them in local-only files (`~/.claude/CLAUDE.md`, the owner's local `projects/agent.md`).
