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

- **Mode switch** (top of the sidebar, big segmented control): `Chat` = Claude, `Work` =
  Claude Code. Memory is shared; chat is conversation-first, work is task-first with a
  different workflow. Mode = route (`chat` vs `work`).
- **Sidebar order**: mode switch → search → **New chat** (prominent) → Plugins (skills +
  connectors) → Projects as a tree → plain Chats (Chat mode only; Work has no plain level,
  everything is filed under a project/category). A button collapses it to an icon rail
  (mode, new, plugins, projects, settings icons; chat list hidden).
- **Header**: conversation title with a menu for its detailed configuration.
- **Composer**: grows with the text up to half the page by default, user-resizable; `+`
  attaches; send button; voice button only when a speech model exists (TODO).
- **Controls row** (sliders wherever the choice is ordered, so they are quick to change):
  1. Permissions (Chat: tool-call approval) — Ask every time → Allow low risk → Auto choose
     → Allow all. (Work later adds per-tool rules.)
  2. right side: Model/profile select, Thinking level slider, Sub-agents toggle.
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

## TODO

- [ ] Work mode: real sessions/targets (local desktop executor, remote devices); no plain chats
- [ ] Permission levels `low`/`smart`/`all` need real tool calls to differ from "auto"
- [ ] Sub-agents: effect (prompt hints per thinking level, delegation)
- [ ] Thinking High/Max: tool planning + review loop in the core
- [ ] Model profiles (Meo Account) + Settings editor + AI-generated profiles
- [ ] Composer: drag-to-resize, max half page; voice input once a speech model exists
- [ ] Details card: tokens from provider usage, files changed, git status, environment
- [ ] Right drawer: browser control, changed files, sub-agents; movable
- [ ] Settings: token usage summary incl. Codex/Claude import (`meo/usage`)
- [ ] Code block highlighting polish
- [ ] Sidebar tree drag/drop categories
