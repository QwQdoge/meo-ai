# Agent flow reference: what Meo adopts from Codex, Claude Code and open-source agents

Status: research + adoption plan (2026-10-23). Nothing here is implemented yet unless marked **have**.

## Sources and what we do not use

Used: the Codex CLI project (open source, Apache-2.0) and write-ups of its Rust core; Anthropic's public Claude Code documentation (glossary, permission modes, compaction, subagents, checkpoints, hooks); open-source agents (OpenCode, Cline, Aider) for edit formats and loops; the academic taxonomy of 13 open-source coding agents (arXiv 2608.10934).

Not used: leaked system prompts or leaked proprietary source of ChatGPT / Claude Code. They are not licensed for reuse, they are often wrong or stale, and copying them would put the product at legal risk. Everything below is rewritten for Meo's own architecture (cloud-first core, Meo API broker, Account-owned keys, consent per request).

## The shared shape (all three)

1. **Loop.** A *thread* holds the conversation; a *turn* = one user submission; inside a turn the model streams, asks for tools, the harness runs them and feeds results back, until a reply with no tool call arrives (Codex: submission queue → turn loop → tool-result loop; Claude Code: gather context → act → verify → repeat).
2. **Tool router with a gate.** Every tool call goes: policy check → (sandbox) → execution → result appended to history. A refused call returns a refusal *to the model*, which adapts. Errors are results, not exceptions; the model decides how to recover.
3. **Permission modes** as the baseline (Codex: read-only / auto / full; Claude Code: default, acceptEdits, plan, auto, dontAsk, bypass) plus fine rules (deny → ask → allow, first match wins). Approval authority lives in the harness, never in the model.
4. **Structured edits.** Codex uses a patch envelope applied by a dedicated tool (diff shown, approve / reject); OpenCode uses exact search-and-replace; Aider uses git commits as the undo. All verify that the edit applied and show the diff.
5. **Context budget.** Track tokens; clear old tool outputs first, then summarise the history when near the limit (Codex ~95% of the window; Claude Code earlier). Keep the system prompt, project instructions (CLAUDE.md / AGENTS.md) and recent turns; reload instructions from disk after compaction.
6. **Persistence.** Sessions are append-only logs (Codex JSONL rollouts + SQLite state; Claude Code transcripts) so a thread can be resumed, forked and rolled back; Claude Code also snapshots files per prompt (checkpoints / rewind).
7. **Subagents.** Own context window, own tool allowlist, own system prompt, bounded turns; the parent gets only the final message. Plan/explore subagents are read-only.
8. **Verification loop.** Work is "done" when a check the harness can run passes (tests, build), not when the model says so.
9. **Instructions as data.** Project/user instructions and tool output arrive as reference messages (system reminders), never as system policy; prompt-injection defence strips or flags tool output.

## Where Meo is today

| Part | Meo now | Gap |
| --- | --- | --- |
| Turn loop | One streamed answer per turn; optional router → planned steps → judge (core `orchestrate`) | No model-driven tool loop: steps are planned by the router, not requested by the model mid-answer |
| Tool router + gate | Consent per request (`prepare` → `stream`, hash-checked) in Meo API; MCP tool *proposals* only (`mcpAuto`), never auto-run | No policy levels that change behaviour (`chat.permission` low/smart/all only differ for "ask") |
| Edits | None in the cloud core; desktop `meo-agent-service` + AgentRun bridge exist for local work | No structured edit tool, no diff/approval UI, no checkpoints |
| Context | Server-side context load (`loadContext`), memory/summaries as data, `context.rs` compaction of tool outputs (local) | No token budget in the cloud core, no summarise-on-threshold, `maxOutputTokens` fixed at 2048 |
| Persistence | Server conversations/messages; Work marker per device | Steps are not stored with the message; no rollback/fork; no task list synced across devices |
| Subagents | Settings switch + prompt hint only | No execution |
| Verification | Judge score (generic prompt) | No runnable checks |
| Instructions | Personal + project instructions in system prompt, memory as data | OK; tool output not yet flagged as untrusted for the planner |

## Adoption plan, in order

Each slice is small, testable without a provider and ends in a visible change on all three clients (they render core view JSON).

1. **Persist the plan with the answer.** **have** (2026-10-23): the answer is stored after the check, as content blocks: a `text` block, one `tool_activity` block per step (router, planned steps, answer, check with its percentage) and a `source_group` per step's links; `list_messages` reads them back, so a reload or another device shows the same steps and Details links (no API change; `answer_blocks` / `steps_from_blocks` in `core-rs/src/cloud/api.rs`). Task list **have** (2026-10-23): the Work guide (meo-api `workGuide`) asks every Work answer to end with a fenced `meo-tasks` block (`[x]` done, `[>]` in progress, `[ ]` to do), keeping and updating the previous list. The list lives in the answer text, so it syncs with the messages; the core draws it as a Markdown task list in the message and lists the newest one in Details ("Tasks · done/total"), `richtext::tasks`. Work marker **have** (2026-10-23): conversations carry a server `mode` (`chat`/`work`, meo-api migration 0015); the core stores it when a conversation moves or a task is created and follows the server's list, copying this device's older device-only Work markers up once. Live after 0015 is applied and the Worker deployed; until then clients keep their local markers. *Codex: rollout items; Claude Code: TodoWrite.*
2. **Context budget in the core.** Estimate tokens per request, drop/clear old tool outputs and search results first, then summarise the oldest turns with the `summary` role model when over ~70% of the model's window; keep instructions and the last turns; show "Context" bar (already in Details) from real numbers; `/compact` command. Raise `maxOutputTokens` per model/role. *Codex auto-compact; Claude Code compaction.*
3. **Permission modes that mean something.** Define for the broker: `read` (no writes), `edits` (writes to the open workspace after approval), `auto` (an approver model decides, ask the user on scope escalation or low confidence), `all`. The mode is evaluated by the API/device, shown in the composer chip, and the acting model only sees refusals. **Default for Chat and Work: `auto`** (owner decision 2026-10-23). *Claude Code modes, Codex approval policy.*
   - "The model confirms" means a **separate approver call** (the `fast`/`router` role), not the acting model approving itself. It sees the proposed action, the workspace root and the user's request, never raw tool output or file contents (injection surface).
   - Deterministic rules run first and the approver cannot override them: deny list, path outside the resolved workspace root, destructive or irreversible actions, anything that leaves the device, credentials. These always go to the user.
   - Approver reply is `allow` / `ask` / `deny` plus a one-line reason; anything unparsable or failing is `ask`. Show the decision and reason in the step details so it can be audited.
4. **Tool loop for connected tools.** Let the model request a tool mid-turn (web search, MCP read tools, later file read) through the broker: request → gate → run → result back → continue, with a step cap and the same step UI. Web search first (read-only, no gate). *Codex tool router.*
5. **Structured local edits on desktop.** Over the existing AgentService: `read_file`, `search_replace` (exact, must match once, else error returned to the model) and `apply_patch` (envelope), always with a diff card and approve/reject, a per-prompt checkpoint (copy-on-write snapshot) and a "rewind" action; path checks resolved against the workspace root (the Codex "parent directory" bug is the cautionary tale: check the real resolved target of every path). Web/Android only show and approve; they do not execute.
6. **Subagents.** A subagent = a stage call with its own role model, tool allowlist, step cap and a fresh context (task + notes only); parent receives its final report as a step result. Read-only by default.
7. **Verification loop for Work.** The plan's last step may be a check with a command the device can run (tests/build) or a rubric for the judge; the answer says whether it passed.
   - **Judge output is a percentage (0-100)** (owner decision 2026-10-23). The core already reads `{"score": 87}`, `score: 87`, `87/100` and `0.87` (`parse_judgement` in `core-rs/src/cloud/orchestration.rs`), so a `jev` model can fill the judge slot without a format change. Keep the verdict thresholds (>= 80 pass, 50-79 revise, < 50 fail) and show the percentage in the card.
   - Research (web, 2026-10): "JEV" appears as a small decision-only judge (JEV-as-a-Judge, arXiv 2609.26550, [summary](https://www.opentrain.ai/papers/jev-as-a-judge-accept-when-confident-escalate-when-unsure--arxiv-2609.26550/)) and as a hosted calibrated-probability judge ([OpenRouter write-up](https://openrouter.ai/blog/tutorials/jev-vs-llm-as-a-judge/)). Both reports say the same: close to a large LLM judge on closed factual checks at a small fraction of the cost, clearly worse on reasoning-heavy or long open-ended rubrics. These are secondary write-ups; confirm which JEV we call and read the primary source before relying on the numbers.
   - So use a **cascade**: JEV percentage first; accept when it is far from the threshold (for example >= 90 or <= 30); otherwise escalate to the LLM judge role. Verbalized percentages are usually over-confident, so calibrate the cut-offs on our own labelled runs (ECE / Brier) before trusting them, and keep the percentage as a number the UI shows, not as a probability claim.

## Safety rules carried over

- The model never grants itself permission; tools and approvals are enforced by API/device policy.
- Tool output, files, search results and memory are data; they are never copied into system instructions.
- Writes are idempotent per step id; a resumed run never repeats a completed write.
- No unrestricted shell in the cloud. Local commands run only through the device's own AgentService with its policy.

## Decisions (owner, 2026-10-23)

- **Permission default for Chat and Work: `auto`**, decided by an approver model with deterministic hard rules ahead of it (slice 3).
- **Judge / `jev` output: percentage** (slice 7); cascade to the LLM judge when unsure.
- **Work works across devices.** Work tasks, the task list and the stored plan/steps/judge score live on the server (slice 1), so a task started on one device continues on another. Execution stays with the device that holds the workspace: other devices see progress and approve, but local edits and commands run only on the owning device through its AgentService (slice 5).

## Open questions for the owner

- Which JEV model exactly (provider/id) and does it return only the percentage or also a reason?
- Cross-device handoff: may a second device take over *execution* of a Work task (needs the workspace there too), or only continue the conversation and approvals?
- Approver model: which role (`fast` or `router`), and should `auto` ever auto-allow writes outside the open workspace (proposal: never)?
