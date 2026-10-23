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

1. **Persist the plan with the answer** (have most pieces). Store the router decision, steps (DID/RESULT) and judge score on the assistant message (server `metadata`) so a reload or another device shows the same steps. Add a task list kind (`todo`: pending / doing / done) the model updates via a structured block, shown in the Work details card. *Codex: rollout items; Claude Code: TodoWrite.*
2. **Context budget in the core.** Estimate tokens per request, drop/clear old tool outputs and search results first, then summarise the oldest turns with the `summary` role model when over ~70% of the model's window; keep instructions and the last turns; show "Context" bar (already in Details) from real numbers; `/compact` command. Raise `maxOutputTokens` per model/role. *Codex auto-compact; Claude Code compaction.*
3. **Permission modes that mean something.** Define for the broker: `read` (no writes), `edits` (writes to the open workspace after approval), `auto` (classifier/policy approves, ask on scope escalation), `all`. The mode is evaluated by the API/device, shown in the composer chip, and the model only sees refusals. *Claude Code modes, Codex approval policy.*
4. **Tool loop for connected tools.** Let the model request a tool mid-turn (web search, MCP read tools, later file read) through the broker: request → gate → run → result back → continue, with a step cap and the same step UI. Web search first (read-only, no gate). *Codex tool router.*
5. **Structured local edits on desktop.** Over the existing AgentService: `read_file`, `search_replace` (exact, must match once, else error returned to the model) and `apply_patch` (envelope), always with a diff card and approve/reject, a per-prompt checkpoint (copy-on-write snapshot) and a "rewind" action; path checks resolved against the workspace root (the Codex "parent directory" bug is the cautionary tale: check the real resolved target of every path). Web/Android only show and approve; they do not execute.
6. **Subagents.** A subagent = a stage call with its own role model, tool allowlist, step cap and a fresh context (task + notes only); parent receives its final report as a step result. Read-only by default.
7. **Verification loop for Work.** The plan's last step may be a check with a command the device can run (tests/build) or a rubric for the judge; the answer says whether it passed. A `jev` model can take the judge slot once its I/O format is known.

## Safety rules carried over

- The model never grants itself permission; tools and approvals are enforced by API/device policy.
- Tool output, files, search results and memory are data; they are never copied into system instructions.
- Writes are idempotent per step id; a resumed run never repeats a completed write.
- No unrestricted shell in the cloud. Local commands run only through the device's own AgentService with its policy.

## Open questions for the owner

- Which permission default for Work (`edits` is the Claude Code / Codex default)?
- jev input/output format (for slice 7).
- Whether Work tasks should sync across devices through the server (needed by slice 1).
