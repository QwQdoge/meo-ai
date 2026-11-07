# Harness alignment: Chat and Work like Claude Code, Codex and DeepSeek Harness

Status: design, first slice landed (planning is opt-in by effort). Owner goals, in the owner's words: keep Meo AI's principles; move Chat, Work and tool calling toward Claude Code, Codex and the Claude Agent SDK; reuse DeepSeek Harness (`dsh`) plugin concepts, and its plugins directly where possible; prompt handling must be safe and convenient; an agent that can only read cannot work and is useless.

## Why the current Chat and Work feel slow

- In auto mode every chat above Low and every Work task first runs a Router stage, then (High/Max) planned steps, then a judge. Each stage is a separate model call, so the first word of the answer comes after several round trips. The default thinking level is Medium, so almost every message paid for the Router.
- Work shows nothing while those stages run, so a task looks idle.

First slice (done): planning is opt-in by effort. Work plans from Medium up; Chat plans only at High and Max. At the default Medium a chat is one model call.

## Target loop (the Claude Code / Codex shape)

One loop: `model -> tool calls -> results -> model`, streaming from the first token, with the tool results fed straight back. Planning, sub-agents and checks are tools or opt-in modes of that loop, not mandatory stages in front of it.

| Piece | Target | Meo AI today |
|---|---|---|
| Turn | One streamed model call per step; tools run between steps | Router, plan, step, judge stages before the answer |
| Tools | A small, typed, well-described set: read, search, edit, write, shell, web, plus MCP | Capability registry with typed policy (keep) |
| Plan | A `plan` / `todo` tool the model calls when the task is big, shown live | Planner stage |
| Sub-agents | A `task` tool that starts a scoped worker with its own context | Read-only sub-agents |
| Progress | Every step streamed: thinking summary, tool call, output | Silent until stages finish |
| Context | Compaction when full, spill of big outputs to files | Compaction exists (keep) |
| Models | Role to model mapping (keep Meo's profiles), a fast model for light turns | Router picks the role |

Meo's Router idea stays as a cheap, local, rule-based choice of role (no model call), with an optional model-based router only at High/Max.

## DeepSeek Harness: what to reuse

`dsh` (MIT, TypeScript, Cordis plugin kernel) already has the pieces we want as plugins: `core/agent-loop`, `core/tools` with a guarded execution pipeline, `guard` and `sandbox` (approval policy), `mcp`, `skill`, `subagent`, `plan`, `todo`, `compaction`, `spill`, `workspace`, `shell`, `fs`, `schedule`, `browser-use`, `computer-use`. It ships profiles (`web`, `headless`, `sdk`, `acp`) and a JSON-RPC SDK server (`dsh --profile sdk`). It is a developer preview; compatibility-breaking changes are announced.

Plan:

1. Concepts first (no dependency): adopt the same seams in the Rust core: events for `agent/*`, `tools/pre-execute`, `tools/post-execute`; a guarded tool pipeline; plugin = a bundle of tools + skills + MCP servers + prompt sections that mounts and unmounts cleanly. Meo's existing `plugin_store.json` and MCP/skills model map onto this.
2. Desktop Work backend (optional dependency): run `dsh --profile sdk` as a sidecar and talk to it over its JSON-RPC SDK. Meo AI keeps the UI, Meo Account, model profiles and permission policy; `dsh` runs the loop and its plugins. Pin a version, vendor nothing, and keep the native loop as the fallback (Android and Web have no local Node, they already reach a desktop through the device bridge).
3. Reuse dsh plugins directly where they are pure tools/skills/MCP, through the sidecar; do not copy their source.

Open check before step 2: Node runtime packaging in the Windows installer and Arch package, and the sidecar's start-up time.

## Permissions: able to work, still safe

Read-only everywhere is not acceptable: an agent that cannot write or run commands cannot do the task. Use the Codex / Claude Code model of modes, chosen per project and shown in the composer:

| Mode | What runs without asking | What asks |
|---|---|---|
| Ask | Reads and searches inside the project | Edits, shell, network, anything outside the project |
| Workspace (default for Work) | Reads, edits and shell commands inside the project directory, with network off for shell; web search and fetch tools | Writes outside the project, destructive commands (delete trees, force push, `sudo`), network from shell, installing packages, secrets |
| Auto | Everything Workspace allows, plus allow-listed commands the user approved before ("always allow") | Same hard stops |
| Full | Everything, no prompts | Nothing; explicit opt-in per project, never the default, never on a remote device unless set on that device |

Hard stops stay in every mode except Full: deleting outside the project, credential files, and actions that leave the machine with personal data.

## Prompt injection: safe and convenient

Principle already in AGENTS.md: prompts, Skills, MCP descriptions and UI data never grant capabilities; permissions come from typed policy. Add:

- Instruction hierarchy: system and the user's own messages carry instructions; tool results, web pages, files, MCP output and skill bodies are data. They are wrapped in tagged blocks with their source, and the system prompt says content inside them is information, not commands.
- Taint and escalation, not blanket denial: once untrusted content (web, email, a file from outside the project, third-party MCP output) has entered the turn, an action it could be steering (shell, write outside the project, network send, MCP write) asks for approval even in Auto, and the approval shows what content triggered it. Reads and edits inside the project keep running.
- No secrets in context: keys and tokens stay in the secure store; tool output is scanned and redacted before it is sent back to the model.
- Approvals show the exact command or diff, so a "yes" is informed; "always allow" is by command prefix and project, revocable in settings.
- Sub-agents inherit the parent's mode and taint; they cannot widen it.

## Chat

Chat follows the same loop with a lighter tool set (search, fetch, files the user attached, memory, connected apps). No Router call for ordinary messages. "Move to Work" is offered when the model calls the `plan` tool with three or more steps, instead of a Router stage guessing.

## Order of work

1. Done: planning opt-in by effort.
2. Stream every step in Work as it happens (plan, tool call, output); show the first token immediately.
3. Replace mandatory stages with `plan` and `task` tools in the loop; local rule-based role choice.
4. Permission modes as above, with the taint rule.
5. Prompt sections and tool schemas assembled per turn (system-prompt section registry, as dsh does) with the instruction-hierarchy wrapping.
6. Evaluate `dsh --profile sdk` as the desktop Work backend; decide with a measured start-up time and a side-by-side run on the same task.
