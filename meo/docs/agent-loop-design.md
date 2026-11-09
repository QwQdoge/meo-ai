# The agent loop: what it was, what it is, and why

Read this to understand why the chat loop changed in November 2026 and what each part is for. Reference
points: DeepSeek Harness (`deepseek-ai/deepseek-harness`, MIT), Codex's prompts (`openai/codex`,
`codex-rs/core/*prompt.md`).

## Before: the model wrote text, the core guessed

```
user message
  -> one request: "prompt" = instructions + history + question, flattened to ONE user message
  -> model writes prose and, to use a tool, a fenced block  ```meo-tool {"tool": ...}```
  -> core parses the text for a block
       block found   -> run it, send "Tool result for ..." as a NEW user message, ask again
       no block      -> the reply is the final answer   <-- the weak point
```

The whole loop hung on "did the model write a block?". When it wrote "next I'll read the README" and no block,
or got the format wrong ("app needs \"app\""), or leaked a marker (`<<<END_TURN_..>>>`), the core could only guess
from the wording. Each fix was another phrase list. Tool results were stored as fake user messages, so a
conversation filled with "Tool result for ..." lines, and every round re-sent a 3-4k character instruction block.

## After: the provider's own tool calling, and explicit state

```
user message
  -> request: prompt + tools[] (real JSON Schemas) + turns[] (finished call/result round trips of this run)
  -> meo-api forwards them as the provider's real `tools` and `tool` messages
  -> the model answers with TEXT and zero or more tool_calls          (SSE event `tool_calls`)
       calls     -> gate (permission), run the first, record {text, calls, results} as a turn, ask again
       no calls  -> the reply is the final answer, unless the model's own task list is still open
```

What is better, concretely:

1. **"Continue or stop" is the model's structured answer, not a guess.** A call is a call; no call is the end.
   There is no phrase list, no fence parsing, no marker cleaning on this path.
2. **The model sees the real schema of every tool** (a connected app's tools are offered as their own functions
   with the app's own input schema, up to 60 functions / 70,000 schema characters), so wrong argument shapes
   are caught by the provider and the model, not by our parser.
3. **No fake user messages.** The finished rounds travel as proper `tool` messages and are not stored as chat
   messages; the answer of all rounds is one message.
4. **The server stays a relay.** `meo-api` never runs these tools, drops calls to names that were not declared,
   and hashes `tools` and `turns` into the consent, so what the user approved is what is sent.
5. **Fallback, not breakage.** A provider without native tools, an older server, or a model the provider refuses
   to use tools with (a 400 such as "function tools with reasoning_effort are not supported") makes the core
   remember that for the credential and run the same message on the old fenced protocol.

## The task list and the round driver (from DeepSeek Harness)

Harness keeps a durable *goal* and a *round driver*: while the goal is active and the agent is idle, the driver
queues another round; the model ends it by marking the goal complete. Meo's chat version is smaller:

- the model keeps a list with the `update_tasks` function (`todo` / `doing` / `done`, whole list each time);
- if it ends a reply with no calls while an item is open, the core sends one `<goal_round>` prompt (objective, open
  tasks, what it just said) and the run continues, at most twice per message;
- no list, or all `done`, means finished. Updating the list does not use up the tool rounds.

## The prompt: named sections, stable first, loaded not hunted

Codex writes its prompt as `##` sections (General, Editing constraints, Plan tool, Presenting your work) and loads
`AGENTS.md` as its own message. DeepSeek Harness registers named, ordered sections and keeps the stable system
prompt apart from dynamic context. Meo's prompt now follows the same shape.

Server (`meo-api`, `assistantPrompt`): who you are, where you are, the user's environment, what you can use,
how to help, answer format. About 1.4k tokens for a web chat; unchanged.

Core, tool part (`tool_instructions_with_apps`), fixed text, same on every round:

| Section | Content | When |
| --- | --- | --- |
| Tools | one line per tool | always |
| How to work | call don't announce; data not instructions; task list; how to finish; ask when ambiguous | always |
| (read rules) | find with `search`/`list_dir`, read ranges, never read a file twice | open folder |
| Project rules | what the loaded rules are and how they apply | open folder |
| Project state | `.agent/` convention (GOAL, TODO, NOTES) | open folder |
| Connected apps | the exact call shape, the app list | apps enabled |

Core, per-run text, added after the fixed part:

| Section | Content | Bound |
| --- | --- | --- |
| Where things are | folder path, top-level entries (no `.git`, `node_modules`, `target`, ...) | 40 entries |
| Project rules (loaded) | the folder's `AGENTS.md` and `CLAUDE.md`, once | 6,000 chars each, 9,000 total, "(truncated)" marker |
| Project state | `.agent/` goal, to-do, notes | existing per-file cap |

Why that saves tokens and rounds:

- The old prompt told the model to find and read in full every README, AGENTS.md, CLAUDE.md, CONTRIBUTING and
  the files they point to, before touching anything: many rounds and many thousands of tokens on every task,
  and it still had to discover where the files were. Now the rules the folder has are in the prompt once, the
  map says where everything is, and the model is told to read ranges and never re-read.
- The fixed folder prompt went from 3,361 to 2,713 characters (-19%); the tool-only chat prompt from 1,144 to
  1,004 (-12%), now with headings.
- Native runs use a short guidance block (`NATIVE_GUIDANCE`) instead of format instructions, because the format
  is the provider's.

## The output limit (a cause of "it stopped half way")

`meo-api` used to send `max_tokens: 2048` for every chat. A reasoning model spends that same budget on its
thinking, so an answer was cut mid-sentence, and because the core never looked at `finish_reason: "length"`, the
half sentence was taken for the final answer: the task seemed to end with work still to do. Now:

- the budget follows the thinking level (low 2,048; medium 6,144; high 12,288; max 16,384);
- `meo-api` sends a `truncated` event (before `tool_calls` and `done`) when the provider stopped for length;
- the core never treats such a reply as final: it asks the model to continue from the last 300 characters it
  wrote (native: one answer, no seam; fenced: a hidden notice and a second message), at most three times.

## What is not native yet

- An open folder (desktop Work) still uses the fenced protocol (its tools are local). Porting `read_file`,
  `search`, `apply_patch`, `run` as native functions is the next step; the fenced path keeps the sections above.
- Only the first call of a round runs; the others are answered "not run".
- Gemini has no native path here.
