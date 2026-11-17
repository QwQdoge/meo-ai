> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

# Meo AI core harness: design

Status: design + first slice implemented (2026-11-17). Read this before changing the agent loop, the
prompts or the tool pipeline. Companion docs: `agent-loop-design.md` (why the loop moved to native
tool calls), `agent-flow-reference.md` (what was taken from Codex and Claude Code).

Reference: **DeepSeek Harness** (`deepseek-ai/deepseek-harness`, MIT, "dsh"), read from source:
`docs/architecture.md`, `packages/core/system-prompt`, `packages/core/agent-loop`, `packages/core/tools`,
`packages/interaction/user-approval`, `packages/subagent/tool-subagent`, `packages/compaction`,
`packages/spill`, `packages/goal`. Also Codex (`openai/codex`, Apache-2.0) and Anthropic's public Claude
Code documentation. No leaked or proprietary prompts are used; every text here is Meo's own.

## 1. What a harness is, and the one rule that matters most

dsh's model: a **turn** is zero or more **steps**; a step is one model request plus the tools it calls;
the turn ends when nothing is owed. Everything the model sees is written to one append-only log first
("model-visible means logged"), so a request can always be rebuilt, resumed, forked or audited.

Meo maps that onto its cloud-first split:

| dsh | Meo today | Where |
| --- | --- | --- |
| Session log (`SessionEvent`, append-only) | Conversation messages + steps in Meo API; the run's `turns[]` (call/result round trips) in the core | `meo-api` conversations, `NativeRun.turns` |
| Turn / step | One user message / one model round (`AppCore::turn`) | `core-rs/src/cloud/app.rs` |
| `ctx.systemPrompt` sections + contexts | `prompt::Prompt` (sections + context parts) | `core-rs/src/cloud/prompt.rs` (new) |
| `ctx.tools` registry + `tools/pre-execute → execute → post-execute` | `NativeTarget` map → `agent::Tool` → `gate_in` → approver → host | `agent.rs`, `app.rs` (`agent_dispatch`), `workspace.rs` |
| `ctx.llm` adapter seam | Meo API broker (`/v1/chat/prepare` + `/stream`), provider keys in Account | `meo-api` |
| Approval policy + sandbox mode = permission preset | Composer level `ask / low / smart / all` + hard rules | `agent::Permission`, `gate_in` |
| Goal + round driver | `set_goal` / `update_tasks` + `<goal_round>` | `app.rs` (`goal_round_prompt`) |
| Subagent provider, depth limit | `subagent` tool, own rounds, fresh or forked context | `agent.rs` (`SubJob`), `app.rs` |
| Jobs (`ctx.jobs`) | `start_job / job_output / stop_job` | `jobs.rs` |
| Compaction (`compaction/*` events, lock) | `/compact`, auto after 24 messages via `summary` role | `compaction.rs`, Meo API `/context` |
| Spill (long output to a file + locator) | `read_more {id, from}` on a kept result | `agent::MAX_RESULT_CHARS`, `NativeTarget::ReadMore` |
| Time context | `clock_note()` | `app.rs` |

The rule Meo adopts as-is: **a prompt part that changes per request is context, and a capability the
model can use is a tool with its own schema and its own sentence of guidance.** Prompt text never
grants or enforces anything; `gate_in`, the approver and the server do.

## 2. Prompt architecture: four layers, each with one owner

```
┌ system ─────────────────────────────────────────────────────────────────┐
│ L1  meo-api assistantPrompt   identity, client, environment, how to help,│  server, cached
│                               answer format, Work guide                  │
│     + personal / project instructions (user-authored)                    │
└──────────────────────────────────────────────────────────────────────────┘
┌ user (per request) ─────────────────────────────────────────────────────┐
│     memory, summary, history          (data, never instructions)         │  server
│ L2  standing sections   ## Tools · ## How to work · plan · apps ·        │  core, static
│                         ## Project rules · ## Project state              │
│ L3  runtime context     folder map · local servers · permission (+change)│  core, per request
│                         · project + loaded AGENTS.md/.agent · clock      │
│     the user's message                                                   │
└──────────────────────────────────────────────────────────────────────────┘
 L4  tools[]   real JSON Schemas (native) — the call shape lives here, not in prose
```

- **L1 says who and where; L2 says how to work; L3 says what is true right now; L4 says what can be
  called.** A sentence belongs to exactly one layer. Before this change L1 said "you cannot run code"
  while L2 said "run commands in the folder": now the core reports `location: "local"` when a folder is
  bound and the server's Work guide switches to the device wording.
- **Same input, same L2 text** (tested), so provider prompt caches hit. Anything with a time, a path that
  changes or a level the user can switch is L3.
- **One set of working rules.** The native and fenced protocols used to keep two copies of "how to work"
  (`NATIVE_GUIDANCE` in `app.rs`, `HOW_TO_WORK` in `agent.rs`) that had drifted. They are now one list in
  `prompt.rs` (`RULES_COMMON`) plus the few lines that really differ per protocol.
- **A tool owns its sentence** (dsh `tool:bash`, `tool:edit`): on a native run the schema already says
  what a call looks like, so L2 only carries what a schema cannot ("check the exit code", "read before
  you edit", "start independent helpers together, do not poll"). A sentence appears only when its tool
  is offered.
- **The permission level is told, and a change is told once** (dsh `approval:policy` context and
  `setPolicy` notice). The model plans differently at Ask (few calls) than at Full access (ask before the
  irreversible). The sentence describes behaviour; `gate_in` still decides.

Section and context orders are allocated in `prompt::order` and `prompt::context_order`; a new part takes
a free slot there and is added with `prompt.section(name, order, text)` / `prompt.context(...)`. Empty
text removes a part; the same name shadows an earlier one.

## 3. The loop

```
user message
  └─ turn: understand (router brief, by thinking level)
       └─ step: prepare (consent hash over prompt+tools+turns) → stream
            ├─ text deltas → live progress
            ├─ truncated → <continue> (≤3)
            └─ tool_calls[1..n]
                 for each call, in order (≤ 8 per reply):
                     map name → NativeTarget → agent::Tool
                     gate_in(permission, tool, bound folders)  — hard rules first
                     approver (smart) / consent card (ask, low) / run (all)
                     run on host / API / app; long output kept → read_more
                 all results → one turn {text, calls, results} → next step
       no calls:
         goal active or task open → <goal_round> (bounded)
         said "next I will…"      → <continue_work> (≤4)
         changed files + /verify  → run check, failure goes back (≤3)
         thinking high/max        → grounding check against what was read (once)
         otherwise                → final answer, stored with its steps
```

Changes in this slice:

1. **Every call of a reply runs.** dsh hands a whole batch to `ctx.tools.execute()`; Meo answered
   every call after the first with "not run", which cost one extra model round per extra read. Now the
   calls run one after another (approval cards still one at a time), their results go back together, and
   more than 8 in one reply are answered "not run" (a reply of 30 reads is a loop, not a plan). The
   prompt tells the model independent calls may share a reply.
2. **An open folder runs on native tool calls.** The folder tools (`read_file`, `list_dir`, `search`,
   `search_replace`, `apply_patch`, `run`, jobs, `subagent`/`list_agents`/`send_message`, local `mcp`,
   `computer_*`) are real function definitions (`agent::local_tool_defs`) and map back through the same
   parser as a fenced block (`agent::native_local_call`), so gate, approver, diff preview, checkpoints and
   `/rewind` are unchanged. A provider without native tools still falls back to the fenced protocol for
   the same credential.
3. **Prompt registry** (`prompt.rs`) for both protocols, runtime context after the standing sections,
   the clock last.
4. **Server prompt agrees with the core:** `location: "local"` with a folder; Work guide wording for a
   device run; with native functions the task list is `update_tasks`, never a fenced list in the answer.

## 4. Experience: what the user should notice

| Before | After |
| --- | --- |
| "Read a.rs and b.rs" took three model rounds (the second call was refused) | One round, both results |
| Desktop Work relied on the model writing a ```` ```meo-tool ```` block; a wrong format or a missing block ended the task early | The provider's tool calls; "continue or stop" is structural |
| The model was told in one place it could run code and in another that it could not | One story per run |
| Switching to Full access mid-chat: the model kept asking, or did not know it could act | It is told the new level once, and the level on every request |
| Work answers ended with a hand-drawn checklist next to the live task card | Only the live task card |

## 5. Roadmap (in order; each is one change with its own test)

1. ~~**Real message history instead of a flattened transcript.**~~ **Done 2026-11-17** (`meo-api`
   `src/chat-history.mjs`). The stored conversation goes to the provider as its own user/assistant
   messages (summary first, old tool rows and notes as user-role data, roles merged, the saved copy of the
   current message dropped; 48,000 characters / 80 messages, old tool results shrink first, then the
   oldest messages go). The broker accepts `history` (validated, in the consent hash when non-empty) and
   sends it for Chat Completions, Responses and Gemini. The current message keeps the per-request parts
   (memory, files, web results, Skill, the core's tool sections). No client change: history is built on
   the server from the stored conversation.
2. ~~**Runtime context sent only when it changed.**~~ **Done 2026-11-17.** The core splits L2+L3 into a
   *harness snapshot* (standing sections, folder map, local servers, project, loaded rules, `.agent/`
   state) and the *volatile* part (permission level and its change, clock), which stays in the prompt.
   The snapshot goes as `harness: {text, anchor?}`. New or changed: no anchor, it leads the current
   message, and the saved message it came with becomes its anchor (SHA-256 of its trimmed text). Unchanged:
   the anchor is sent and `meo-api` puts the snapshot in the history at that message
   (`historyWithHarness` in `src/chat-history.mjs`), so it stays in the cached prefix instead of after it.
   If the anchored message left the window, it falls back to the current message. An older API that
   refuses the field gets the snapshot inside the prompt (`harness_unsupported`).
3. ~~**Hooks at the seams.**~~ **Done 2026-11-17** (`app.rs`). The end of a round is one ordered list,
   `STOP_CHECKS` (`AppCore::turn_stopping`, after Harness' `agent/turn-stopping`): cut off → goal round →
   empty final → stalled → `/verify` → grounding. The first that asks for another round wins and each
   returns its own `Continue` value (which also says whether the reply is stored). Checks run lazily, so
   the `/verify` command and the grounding model call only run for a reply that would be final. Two
   deliberate order changes from the old flag ladder: a stalled reply no longer runs `/verify`, and a
   failed `/verify` now goes back before a grounding revision. The result side is `post_execute` (keep
   long output for `read_more` → wrap as data → repeat reminder), with steering added in `agent_send`.
   A new check is a `StopCheck` variant and one arm in `turn_stopping`.
4. ~~**Spill to a file the model can read.**~~ **Done 2026-11-17** (`host.rs` `spill_into`, `post_execute`).
   A result longer than `MAX_RESULT_CHARS` with a folder open is saved whole at
   `.agent/spill/<time>-<tool>-<round>.txt` (written by the harness directly: no checkpoint, no diff card;
   the directory's own `.gitignore` is `*`; the newest 30 are kept), and the model is told the path and
   line count and reads it with `read_file` ranges or `search`, also after a restart and from a
   sub-agent. Without a folder (web, cloud chat) `read_more` keeps working from memory. Two bugs fixed on
   the way: native results were cut at 12,000 characters, which dropped the note saying where the rest
   is; and a long run could pass the server's 300,000-character limit for a run's rounds, which was
   answered `invalid_tool_turns` and silently switched the run to the fenced protocol. Older round
   results now shrink first (`bound_turns`, 240,000), the newest round stays whole.
5. ~~**Parallel read-only calls.**~~ **Done 2026-11-17** (`app.rs` `parallel_reads`, `agent_run_together`).
   From the next call of a native reply on, the run of `read_file` / `list_dir` / `search` (with a folder)
   and `web_search` / `web_fetch` calls that `gate_in` allows without a question runs at once
   (`join_all`). The batch stops at the first other call, so a write or command never runs before or
   beside a read the model put ahead of it; the calls after it go on one by one (and may start a new
   batch). Each call keeps its own round, step, kept result and spill file, and results go back in call
   order. Folder reads share the workspace lock, so they still take turns with each other; what they
   gain is overlapping with web fetches, and the batch is one step burst instead of one per call.
6. ~~**Delegation depth and fan-out as context**~~ **Done 2026-11-17** (`agent.rs` `delegation_context`,
   after dsh `SUBAGENT_DELEGATION`). Every sub-agent prompt now has a "Your place in the run" part before
   the task: its name, depth 1 of `SUBAGENT_MAX_DEPTH` (1), that the lead reads its report, that it
   cannot start sub-agents, ask the user or use the web and should leave those parts to the lead in its
   report, and the sub-agents beside it (`Beside::Together` for researchers running at once,
   `OneByOne` when a worker is in the call, `FollowUp` for `send_message`); a worker is told nobody else
   changes files meanwhile. The lead's `subagent` guidance (fenced, native sentence and the function
   description) says the same limits, so it keeps the web and user questions for itself. The refusal
   stays as the backstop and now says what to do instead.
7. **Per-model context window and `maxOutputTokens`** from the model catalogue, so compaction triggers on
   tokens, not on message count.
8. **Session-level events for replay** (dsh session log): store each step's request header (model,
   thinking, permission, tool names) with the answer's steps, so Details shows exactly what the model saw
   and a run can be resumed on another device from the log.

## 6. Rules for changing prompts

- Put a sentence in the layer that owns it (section 2). If it changes per request, it is context.
- A tool's guidance goes in `prompt::native_tools` / `fenced_tools`, guarded by whether the tool is offered.
- No rule for one kind of task (how to review a repository, which repo "Meo AI" is): that is the router
  brief's job (`understand`), per request.
- Keep it short: the standing folder prompt is capped by a test (`< 5,000` characters fenced).
- Prompts never grant capabilities and never replace `gate_in`, the approver or the server's checks.
- Change wording in one place: the server owns L1 (`meo-api/src/ai-prompts.mjs`), the core owns L2–L4.
