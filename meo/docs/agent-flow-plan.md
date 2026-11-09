# Agent flow plan: one request from send to answer

What happens to a message, step by step, and what is done versus still to build. Written after a
run that lost the user's request mid-task (2026-11-09). Companion to `agent-loop-design.md`.

## The failure this answers

The user asked Meo AI to open a PR improving the chat output. The provider refused native tools, the
run fell back to the fenced protocol, read two large files, and then asked "What specific change would
you like me to carry out?" in English. Causes, all found in code:

| Symptom | Cause | Fix |
|---|---|---|
| Request forgotten | The Meo API keeps the newest 40k prompt characters and trims the oldest first. Each fenced round sent ~38k characters of connected-app tool text plus the tool result twice (saved message and prompt), so the user's first message fell out. | Every later round ends with `<task>` holding the request (core). The server no longer repeats the saved message when the prompt wraps it (meo-api `chat.ts`). |
| English answer | Same cause: the request, and with it the user's language, was gone. | The `<task>` block says to reply in the request's language. |
| "cannot use tools the new way" popup | A notice about plumbing. | Removed; the run just continues. |
| Work done twice after the fallback | The fallback restarted the run from zero. | Finished native rounds are passed as `<done_so_far>`, and the router's reading is reused. |
| Many reply bubbles, each with Copy/Edit | Each fenced round was stored and drawn as its own message. | The view merges the rounds of one run into one answer (`merge_rounds`); a round that only called a tool is a step, not text. |
| Task list written again as text every round | Each round's `meo-tasks` block was drawn. | Only the newest list is kept; a native run's list is drawn live at the top of the answer. |
| Flash and jump when the answer finishes | The web keyed messages by server id, so the streamed message remounted (and replayed its entrance) when it got its id. | Messages are keyed by position in the chat. |
| Details showed route/model/answer as "tools", context at 98% "connected apps" | Plumbing steps counted as tools; CJK text counted as 4 characters a token. | Only real tool steps listed; CJK counted as one token a character; Model and Context moved to the end, closed. |
| Asked again "what do you want me to change?" on later messages | Across messages the request is an older user message; old tool results (whole files) pushed it out of the 40k window. | The server shrinks old tool results to one line, oldest first, before anything is cut, so user messages stay. |
| "好的" and "can you see the context" sent to web search | The fenced path searched the web with the message itself as the query. | No search on the model's behalf when it has `web_search`, or when the message is not a lookup. |
| "The file was cut before the part I need", then giving up | Results are capped at 14,000 characters with no way on. | The whole result is kept on the device; the cut note gives an id and `read_more {id, from}` reads the next part. |
| Claimed the GitHub tools cannot do something, plan restated every round | No rule against either. | Prompt: never ask to repeat the request, check the tools before saying something cannot be done, one sentence between calls, report outcome / checked / not done. |
| Avatar and settings overlap | Collapsed sidebar put avatar, gear and sync dot in one row. | Gear on the right (icon only); collapsed they stack; the sync state is a dot on the avatar. |

## The flow

1. **Send.** `send` → `agent_begin` (the request is kept for the whole run) → `turn`.
2. **Thinking level decides the extra steps** (table in `agent-loop-design.md`): low adds nothing;
   medium adds the router's reading; high/max add the server planner (or the reading), the task list
   seeded from the reading, and a grounding check; max adds the judge.
3. **Route.** `router::route_for` picks the model slot (fast / default / thinking / image) from the
   composer mode, the message and the level. The server planner may override it at high/max.
4. **Understand.** The router's reading (`understand`) writes what is wanted, the subject, the
   deliverable, what must be examined and what is not wanted. It is not a rule for one kind of task.
5. **Tools.** Native function calling when the credential supports it; otherwise the fenced protocol
   (remembered per credential). Both run the same loop: one call per round, results go back as data.
6. **Rounds.** Each round carries the request (`<task>`), the brief and the task list. The goal-round
   driver keeps going while tasks are open; a reply cut at the output limit is continued; a reply that
   announces a step without calling it is sent back (at most twice).
7. **Answer.** One answer on screen per user message, with the steps folded above it and the task list
   at its top. Formatting rules (headings only for long answers, bold sparingly, anything to copy in its
   own fenced block) are in the server's `markdownGuide`.

## Files and repositories

- Attached files are read by the server and passed as data; a Work folder gives `read_file`,
  `list_dir`, `search` and edits, with the project rules loaded up front.
- A GitHub repository is reached through the GitHub connector. Scope comes from what the user named:
  `get_me`, then search `user:<login> <name> fork:true`; never list every repository.
- Changing a repository (commit, branch, PR) is a write: the user's permission setting decides whether
  each call runs, and the answer names the branch and the PR link.

## Still to build

| Item | Why it is not done yet |
|---|---|
| Sub-agents for independent parts (read several files in parallel, each with a fresh context) | Exists for Work folders (`subagents` pref); not yet for connector reads in chat. |
| Several tool calls per round | Native calls after the first get "not run"; running them in parallel needs per-call consent. |
| Rich interactive answer cards (generated UI beyond charts, diagrams, graphs, drafts, files) | Needs a block type all three renderers draw; to be specified in the view contract first. |
| Android renderer parity for the merged answer and the sidebar foot | The Android client is not compiled in this environment. |
