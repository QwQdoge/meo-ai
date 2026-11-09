# Chat reply states: events, components, recovery (audit, 2026-11-09)

Scope: Meo AI Chat on Web (`meo/web/client/src/core/CoreApp.tsx`, `shell.css`, `core.css`) rendering the view built by
`meo/core-rs/src/cloud/app.rs`. Desktop (QML) and Android were not audited here; they must follow the same table.

## Display rule: the UI reports only what has happened

1. A status line names a real event. With no event but "request sent", say that ("Waiting for the model"), not "Thinking" or "Searching".
2. "Thinking" may be shown only when the provider sent reasoning, or a router/plan step is `running`.
3. Expandable process content exists only when text was actually received and is allowed to be shown. No invented "thinking record".
4. A step label names an action only when a step for that action exists (running or finished). Never from the prompt or a guess.
5. Every reply ends in a terminal state: done, stopped, or failed. No message stays "generating".

## Real events the core receives (`cloud/api.rs` SSE `next_frame`)

`delta` (answer text), `tool_calls`, `truncated`, `done`, `error`. **There is no reasoning/thinking event.**
Steps (`app.rs` `step()` / `note_step()`) are created by the core itself: router stage, plan, web search, each tool call, check, answer.
Step status values in use: `running`, `done`, `error`. No `pending`, `skipped` or `stopped`.

## State → trigger → component → survives refresh

| State | Real trigger | Component (Web) | Refresh / reopen |
| --- | --- | --- | --- |
| Request sent, nothing back | `generating`/`streaming` set, message empty | `MessageView`: `LiveStatus "Thinking"` **and** `.core-typing` dots together (`CoreApp.tsx:1034-1036`) | Live state is in memory only; not verified for Web refresh mid-stream |
| Router / plan / search / tool step running | `step(id, …, "running")` | `.core-steps` summary shows `LiveStatus` from `stepKind()` (regex on step id/title) | Lost mid-run; finished steps are stored on the message |
| Answer streaming | `delta` | `Blocks` + trailing `▍` caret (`withCaret`) | Text stored when finished |
| Reasoning text | **no event exists** | none | n/a |
| Step finished | `step(..., "done")` | `step-done` list row, check icon, `detail` and `items` in a `<details>` | Stored (`visible_steps`, `steps_stored_with_answers_show_after_a_reload` test) |
| Step failed | `step(..., "error")` | `step-error` row, close icon | Stored |
| Stop (user) | `Action::Stop` → `cancel` flag | Composer button / Esc; running steps set to `error` (`answer` → `done`) | Steps keep that status |
| Provider/connection failure | stream `error`, timeout, HTTP 5xx/429 | Transient: one automatic retry; then a message with reason and a `Retry` button (`failed_round`, `retry_round`) | `failed_round` is state in memory, not stored: not verified to survive a refresh |
| Truncated reply | `truncated` | Core asks the model to continue, up to 3 times | n/a |
| Waiting for approval | consent / `Waiting for your approval` step | `page.consent` banner (`role=alertdialog`), buttons from core | Not verified |
| Reply finished | `done` | `stepsLabel` summary, answer blocks, message actions (copy, core actions) | Stored |
| Scrolled up while streaming | scroll position | `stick` ref stops following; `.core-jump` button (`aria-label`) returns to end | n/a |
| Copy | click | `CopyButton` per code block and per answer (`m.text`) | n/a |
| Charts / math / diagrams | fenced language in `VISUAL_LANGUAGES` | `VisualBlock` with plain-code fallback | n/a |

## Gaps against the rule (to fix in order)

1. **Invented "Thinking".** With no step and no text the UI shows "Thinking" (twice: `LiveStatus` plus dots) although no thinking event exists. Replace by a neutral "Waiting for the model" until a real step or delta arrives; keep one indicator, not two. Copy belongs in the core strings (`app.rs` ~7217), not hard-coded in React.
2. **Labels guessed from text.** `stepKind()` maps free-text step ids/titles by regex ("web", "run", "read"…) to "Searching the web", "Running a command". A title that merely contains such a word is mislabelled. The core should send a `kind` field on each step; React uses it.
3. **Stopped is shown as failed.** `Stop` sets running steps to `error`. Needs a distinct `stopped` status with its own icon and wording; add `pending`/`skipped` for planned but unreached steps.
4. **Long waits.** `LiveStatus` only adds an elapsed counter after 5 s. After a threshold (suggest 20 s) the text should say plainly what is happening ("Still waiting for the model · 24 s") instead of a repeating animation. The counter sits inside `role="status"`, so a screen reader may announce every second; move the timer out of the live region.
5. **Failed rounds do not persist.** `failed_round` is memory-only. After refresh the Retry card is gone; decide whether to store the failed marker with the conversation.
6. **Copy feedback.** `CopyButton` has success feedback but silently does nothing when `navigator.clipboard` is missing or rejects. Add a failure label and a selection fallback. Whole-answer copy uses `m.text`; confirm it matches the rendered markdown (no tool-call fences).
7. **No process content.** Because no reasoning event exists, the "expandable process" requirement is currently satisfied only by step `detail`/`items`. A reasoning view needs a core event first (`reasoning.delta`) and a display permission flag; do not add it in React alone.
8. **Reduced motion** is handled globally (`shell.css:441-447`, system setting and in-app toggle). Keep it; new animations need no extra work.

## Not verified

Desktop and Android rendering, page refresh during a live stream on Web, behaviour on a real provider (all findings are from reading code and the existing Rust tests; nothing was run).
