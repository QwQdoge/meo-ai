> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

# Meo AI UI redesign — Claude-style shell (user decision 2026-10-21)

Rule: do not invent a new design. Copy the Claude desktop app's layout and controls and
keep Meo's own naming/branding. All three clients (desktop, Android, Web) render the same
view from `core-rs/src/cloud`; features are identical except that only desktop can be
*controlled* (local Work, like Claude Code). Product structure lives in the core view, not in
renderers.

## Density rule (user feedback 2026-10-21: first pass was too big)

Copy Claude's quietness: no big filled buttons, plain small text rows, dates hidden in lists,
New chat is a plain accent row, the Chat | Work switch is a small pill, controls under the
composer are one line of grey text (`Allow all ▾`, `● Search`, `Auto ▾`, `Medium ▾`,
`○ Sub-agents`) and sliders/selects open in a small popup. The details card stays small and
lists only what has a value.

## Layout

```
┌ sidebar ───────────┬ page ─────────────────────────────────────┬ details card ┐
│ [ Chat | Work ]    │ title ▾ (chat config)         [card][more]│ tools used   │
│ Search             │                                           │ context/tokens│
│ + New chat (loud)  │ messages (Markdown, code highlight)       │ files changed │
│ Plugins (skills +  │                                           │ environment   │
│   connectors)      │                                           │ git state     │
│ Projects (tree)    ├───────────────────────────────────────────┤ resources     │
│ Chats (chat only)  │ composer: + attach · text (auto-grow,     │               │
│                    │   max half the page, drag to resize) · mic│               │
│ Settings / account │ controls: permission · …   model · think │               │
└────────────────────┴───────────────────────────────────────────┴──────────────┘
```

- **Mode switch** (top of the sidebar, big segmented control): `Chat` = conversation-first,
  `Work` = task-first. Memory is shared; Chat and Work have different execution scopes.
  Work contains **General** and **Code** task profiles; Code is a profile inside Work, not a
  third top-level mode or a separate Agent Runtime.
- **Sidebar order**: mode switch → search → **New chat** (prominent) → Plugins (skills +
  connectors) → Projects as a tree → plain Chats (Chat mode only; Work has no plain level,
  everything is filed under a project/category). A button collapses it to an icon rail
  (mode, new, plugins, projects, settings icons; chat list hidden).
- **Header**: conversation title with a menu for its detailed configuration.
- **Composer**: grows with the text up to half the page by default, user-resizable; `+`
  attaches; send button; voice button only when a speech model exists (TODO).
- **Controls row** (sliders wherever the choice is ordered, so they are quick to change):
  1. Chat: tool-call approval for lightweight tools. Work: permission mode and, when applicable,
     per-tool rules.
  2. In Work, show the task profile (General / Code), the explicit target device and active
     workspace. A saved device preference may preselect a target, but the selected device must
     remain visible and changeable for each task.
  3. Model/profile select, Thinking level slider and Sub-agents toggle.
- **Thinking level**: Low = answer/edit directly; Medium; High = plan which tools are
  needed, call them, have a model review; Max = more rounds of model and tool calls, slower.
  Higher levels add recommended-delegation hints to the prompt (prompts to be written).
- **Model profiles**: Meo Account AI profiles (e.g. all-OpenAI, all-Claude, smartest,
  cheapest). User-defined first, optionally AI-generated; every option editable in Settings.
- **Details card** (top right, appears when the first token of a reply arrives, can be hidden;
  remembers the last choice): tools used, context/tokens, files changed, environment (cloud
  device / local device / plain chat), git state, resources used (searched sites, files read).
- **Right drawer** (movable): full detail view; opens only for built-in-browser control,
  changed files or sub-agents; closable.
- **Settings** is one large card: categories on the left in groups (Preferences: General, Personalization & memory · AI: Models, Model profiles, Model routes, Connectors · Account: Usage, Account & security), one page on the right, close button top right. On phones the categories become a row of chips. The core owns the grouping (`page.nav`, `page.selected`, action `select_settings_section`).
- **Settings** also gets a token-usage summary (optionally merging Codex and Claude usage,
  `meo/usage`), laid out like the Codex profile screenshot.
- Chat area for now: text, Markdown, code formatting only.

## Status

Done: slash commands, starter prompts, answer steps (core + 3 clients).

Slice 1 (this change): root `sidebar` (mode switch, search, new chat, plugins, projects tree,
chats, collapse, settings), `composer.toolbar` controls (permission, thinking, sub-agents
flag, model), details card data, Web + desktop + Android renderers.
Behaviour wired: permission → provider consent (`chat.auto_consent`), thinking level → route
(`fast` / `thinking`) in Auto mode. Everything else below is stored but has no effect yet.

## Compared with Claude desktop (2026-11-07)

Checked against Claude's desktop docs and layout; done in `desktop-rs/qml/Main.qml`:

- The Chat | Work choice is one small pill with a sliding thumb (`ModeSwitch`), not two buttons.
- New chat is a plain accent row; projects and chats are quiet 13px rows (`NavRow`) with a hover menu.
- The composer is one rounded card: text on top, one control row inside (attach `+`, folder, permissions, search, sub-agents, model, thinking) and the send button at its end. The details card button is an icon.
- Standard shortcuts: New, Preferences (`Ctrl+,`), `Ctrl+B` sidebar, Find (search), Quit.
- Polish pass: MeoUI menus (motion popup) replace the plain Qt menus; the slider popup names every stop; message actions appear on hover (newest stays visible); pulsing dots while waiting for the first token; a jump-to-latest button; pressed and keyboard-focus states on sidebar rows and the mode pill; tooltips use the MeoUI delay; the sign-in page lists what Chat, Work and Skills do (`page.features`, from the core, translated in `ui-schema/locales`).
- One core, three thin renderers: the product view (including the sign-in feature list and the short UI strings) comes from `core-rs/src/cloud`; QML, the Web page and Compose only draw it. Web and Android got the same pass (sliding Chat | Work pill, plain New chat row, typing dots, jump-to-latest, Meo mark on the empty chat, sign-in features). The old second React client (`web/client/src/meo`, unreachable from `main.tsx`) was deleted. Canned views for offline checks are shared in `meo/ui-fixtures`; `web/client/demo` serves them through a stub of the WASM core.
- Settings (2026-11-07): categories now follow the MeoUI app-shell order: General, Appearance (theme, text size, reduce motion), Personalization, Notifications (answer-ready alerts), Keyboard shortcuts, then AI, Account and About last (version, license, upstream credits). A search box filters every category at once (`page.search`, action `search_settings`; a category name or keyword opens the whole category, otherwise matching controls are shown with their category). Theme, motion and text size are now applied on all three clients (desktop ignored them before). Still missing: Data & privacy (export/delete need Meo API), sign-in sessions, per-tool permission rules, an Advanced category.
- Settings layout (all three clients): the app sidebar is hidden on the settings page (it has its own navigation); items split at each heading into rounded group cards; a row is name + quiet description on the left and the control on the right (switch, compact dropdown, slider, key caps, buttons); long inputs sit under their name; hints are notes under the card. Items may carry `description` (from `ui-schema/settings.json`), `keys`, `tone` and `switch`.
- Projects (2026-11-07): see [projects-and-environments.md](projects-and-environments.md): a project links, per device, to a folder and a GitHub repository; its goal, to-do and notes live in `<folder>/.agent/` and are kept up to date by the model and editable on the project page; Start Work opens the project's folder. The project page also got its own navigation (before, only its first section was reachable).
- Desktop visual pass (2026-11-07), found by rendering light and dark side by side: `MeoTheme.onSurface` / `onSurfaceVariant` evaluate to plain black (a property named `on…` clashes with QML's signal-handler syntax), so muted text was black and dark mode unreadable; use `MeoTheme.contentOnSurface` / `contentOnSurfaceVariant`. `MeoText` has no default color, so `Main.qml` uses `Txt` (follows the theme). Theme choice (Settings > Appearance) now switches `MeoTheme` and the window palette itself, so it also works without the Meo desktop color plugin. Chat code fences render as code cards (language, copy, horizontal scroll); Plugins has underlined tabs, a compact search and equal-height cards with their buttons pinned to the bottom. Check dark mode offline with `{"prefs": {"appearance.theme": "dark"}}` in a fixture.
- Native platform parts only: the window keeps the system title bar (no frameless window), notifications use the platform service (`notify-rust`: freedesktop D-Bus on KDE/GNOME, Windows toast, macOS Notification Center), file and folder pickers are the system dialogs.

Offline check without the core, network or account: `desktop-rs/demo` builds `meo-ai-demo`, which loads the real `Main.qml` with canned views (`meo/ui-fixtures/*.json`, shared with the web demo: chat, new chat, Work, collapsed rail, offline banner, sign-in, settings) and can save screenshots:
`cmake -S meo/desktop-rs/demo -B build/demo -DCMAKE_PREFIX_PATH=<Qt> -DMEO_UI_ROOT=<MeoUI>` then `QT_QPA_PLATFORM=offscreen build/demo/meo-ai-demo --view meo/ui-fixtures/chat.json --shot chat.png`.

## TODO

- [ ] Chat reply states (audit: `chat-state-map.md`). Done 2026-11-09: wait label says "Waiting for the model" (no invented Thinking), one indicator, stopped steps say so. Next: core `kind` per step, `stopped`/`pending`/`skipped` statuses in all three clients, long-wait wording, persisted Retry card, copy failure feedback, reasoning event + expandable view, unclosed-Markdown stability, code/copy blocks, chart/diagram states (brief steps 4-5).
- [ ] Superagent-class features (Ultracode-style multi-agent workflows; DeepSeek-style long-horizon agent): wanted, after the chat-state work above. Needs design in the core first (orchestration.rs, sub-agent execution beyond read-only, budgets, verification passes); not started.

- [x] Work mode (cloud): a Work task is a conversation marked as Work (ids kept on the device, `move_to_work` / `move_to_chat` / `new_task`). Work page = the conversation page with its own sidebar list "Tasks" and starters. Every Work message is routed and planned (steps: low 1, medium 3, high 6, max 10), judged from medium up, and the model gets the Work guide. Prompts for both workspaces live in meo-api `src/ai-prompts.mjs` (samples in `docs/ai-prompts.md`). TODO: local desktop executor / remote devices, Work tasks synced across devices (today the marker is per device), sub-agent execution
- [x] Permission levels (checked against the code 2026-11-04): `chat.permission` = `ask` / `low` / `smart` / `all` is enforced by `agent::gate` in `core-rs/src/cloud/agent.rs`. Below `all`, catastrophic commands are denied, escalations (`sudo`, `curl`, `git push`, `rm -rf`, ...), paths outside the workspace and credential paths always ask; reads run on their own from `low` up; `low` asks for writes and commands, `smart` lets an approver model answer only allow / ask / deny, `all` allows everything. Covered by tests in `agent.rs`. TODO: per-tool rules for Work, and a per-connector (MCP / app) permission screen.
- [x] Sub-agents: the `subagent` tool runs a read-only research sub-agent with its own fresh context (`SUBAGENT_ROUNDS`, `run_subagent` in `app.rs`), only when the composer's Sub-agents toggle (`chat.subagents`) is on. TODO: prompt hints per thinking level, and delegation beyond read-only research.
- [~] Thinking levels: low routes to the fast model, high/max to the thinking model, and above low the core plans steps and judges (router, planned steps, judge). TODO: the full High/Max tool-planning + review loop below.
- [ ] Deferred (core/API, not UI): the hardest work belongs in Work mode. Chat shows the tool-call and web-search chain; done: when the router plans 3+ steps the core shows a banner "Open Work" (notice `actionLabel`/`action`, all three clients); TODO: actually move the conversation into a Work session once Work has real sessions. Then more levels, more tasks, a fuller prompt set, Work-mode orchestration (more steps than chat). Lives in `meo/core-rs/src/cloud` (`orchestration.rs`, `app.rs`) and meo-api `src/ai-prompts.mjs`, never in the clients.
- [x] Model profiles live in Meo API (`/v1/ai/model-profiles`, PR QwQdoge/meo-api#45): one named choice of connection+model per role (chat, lightweight, thinking, vision, create/edit images, video, speech, transcription, sub-agents, router, titles, summaries, embeddings). Nothing is generated by default. Settings > Model profiles lists, edits (every role, with what it is for and its accuracy/impact/speed/volume) and creates profiles; "Generate with AI" takes the user's wishes, the API builds the prompt (all roles + all models with capabilities) and validates the reply, the core only sends it through the consented chat path. Using a profile points the routes at its models; the active profile's `title` role is used for chat titles. Account (Flutter) will get the same editor from the same API. TODO: router, sub-agent, summary and embedding roles are stored but not used by the core yet; runtime fallback to another model when one fails.
- [ ] Composer: drag-to-resize, max half page; voice input once a speech model exists
- [x] Work folder button (desktop): the composer shows the open Work folder (or "Open folder") and picks one with the system folder dialog (`composer.workspace`, action `set_workspace`; same as `/workspace`).
- [~] Details card: environment shows "This device · <folder>" for Work, and "Tools used" counts Work tool rounds. TODO: tokens from provider usage, git status
- [ ] Right drawer: browser control, changed files, sub-agents; movable
- [x] Settings > Usage: reads `GET /v1/usage-dashboard` (totals, 30-day bars, breakdown, models, sources). Codex/Claude rows appear once their local logs are synced to the account (`python -m meo.usage.cli sync` / Account broker); the core does not read local logs. TODO: in-app import trigger on desktop
- [x] Plugins > Installed (core, all three clients; it used to be a Settings page, moved on the owner's decision 2026-11-07, Settings now only has Permissions): one list of every installed app, skill and MCP server with its state (kind, on/off, signed in, tool count and how many are read-only) and the same actions as the store's Installed tab (switch, connect / reconnect / disconnect, API token, remove), a button to Apps & Skills, and a note on how approvals follow the composer's Permissions. Before this the section had no items and was dropped from the page. TODO: show each app's tool list with its read/write class, standing always-allow consents (Meo API only lets a browser session create or revoke them), and an "add MCP server" shortcut that opens the Import tab directly.
- [x] Settings > Devices & Work (core, all three clients): this device (name, platform, whether it can run tasks), an editable device name (`remote.name`; changing it or the remote switch re-announces this device to the others), the remote-control switch, live-sync state, the other signed-in devices that announced themselves, the "Run Work tasks on" choice, and a safety note. Before this the section had no items and was dropped. Safety: a task sent from another device never runs with Allow all (it is capped to Smart on the host), so risky actions still reach the approver and the controlling device. TODO: devices that are offline or last-seen (devices exist only while online; the protocol has no goodbye), a per-device default permission for remote tasks, history of tasks run on other devices, pairing of devices outside the account (`meo/device`).
- [x] Export a conversation (core, all three clients): "Export" in a conversation's menu saves it as `meo-<title>.md` (the host's save hook, a browser download on the web, else the Downloads folder). Tool requests are left out. Found by comparing the action list with Claude, ChatGPT and DeepSeek; the other gaps there are still open and mostly need Meo API support: share links, edit branches (switching between versions of a message), answer feedback, voice, and showing a model's reasoning (the stream does not forward it today).
- [ ] Code block highlighting polish
- [ ] Sidebar tree drag/drop categories

## Performance of long chats (2026-11-07)

Measured on a 300-message chat (about 600 KB of view JSON, 200 chats in the sidebar), per streamed token:

| Where | Before | After | How |
| --- | --- | --- | --- |
| Web page (script time) | 512 ms | 2 ms | refreshes coalesced per animation frame; each message is a memoized component (only the streamed one re-renders); off-screen messages use `content-visibility` |
| Desktop QML | 40.6 ms | 9.4 ms | the host sends unchanged stored messages as `{id, same: true}` placeholders (`desktop-rs/src/message_delta.rs`); QML message blocks are read by position and updated in place instead of rebuilt |
| Core `view()` | 9.3 ms | 4.8 ms | the sidebar (a menu per chat) is cached by a hash of what it shows (`sidebar_key`); stored messages' parsed blocks are cached by content (`rendered`) |

Scrolling: a reader who scrolled up is no longer pulled to the bottom by the stream (web and desktop); sending a message follows again.
Measure again with `meo-ai-demo --view <fixture> --bench 30` (desktop, `MEO_BENCH_DELTA=1` for the placeholder path), `?perf=300&stream=40` on the web demo and `cargo test --release -- --ignored view_cost --nocapture` (core).

## Chat details (2026-11-07)

The composer is focused whenever a chat opens (new chat, switching chats), and each chat keeps its own unsent draft (`page.id` names the chat; web and desktop). Esc stops a running answer and ↑ in an empty box edits the last message you sent (`composer.editLast`). Links in answers open in the browser on desktop. Attached files are chips with a type icon, size and a remove button. A reader who scrolled up is not pulled down by the stream; sending a message follows the end again.

## Craft details (2026-11-07)

Taken from a teardown of Claude's desktop client that was passed to us (a video script, not something we verified ourselves), applied where it fits:

| Detail | What we do |
| --- | --- |
| Layers by lightness, not outlines | Cards, code blocks, chips and selects sit on the canvas with a tonal step and no border; a border remains only on popups (a hairline) and as a soft ring on the focused composer and search fields |
| Hairlines are one device pixel | Desktop: `window.hairline = 1 / devicePixelRatio`; web: `--hair` is 1 / 0.5 / 0.333 / 0.25 px at 1x / 2x / 3x / 4x |
| Scroll edges fade through seven eased stops | `EdgeFade` (QML) and a seven-stop `mask-image` (web) on the message list and the sidebar, shown only while there is more to scroll that way |
| Type | No synthetic bold or italic (`font-synthesis: none`), tabular digits for numbers that change (`Num` in QML, `font-variant-numeric` on the web), grayscale smoothing and a lighter weight (400 to 360, only effective with a variable font) in dark mode. Not done in QML: MeoUI's Roboto files are static, so there is no 360 to ask for |
| Five lengths of motion | 60, 120, 200, 300, 450 ms (`tTick` ... `tSlower`, `--t1` ... `--t5`); the waiting dots only change brightness; the system setting or Settings > Appearance > Reduce motion stops all animation (QML through `MeoTheme.motionDurationFor`, web through a global rule) |
| Opening the window | The base color is painted first (web: inline in `index.html`); while the saved session is read the view is a loading state (`page.kind = "loading"`, `sidebar.skeleton`) with the sidebar drawn as the last run left it, open or collapsed, so a signed-in user no longer sees the sign-in page flash and the real content lands in place. Hosts call `AppCore::expect_start()` after creating the core. Not done: the first native frame of the desktop window before QML loads |
| Not done | Search-bar buttons sized from their height with a 1 px inset on each side; per-theme font weights in QML |
