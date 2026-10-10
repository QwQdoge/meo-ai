# Meo AI product specification

Status: product source of truth for the native Meo AI application. This document describes the complete user-facing product, not only the current engineering preview. Every section distinguishes the target experience from the implementation state where that matters.

## Product statement

Meo AI is the local-first AI workspace for MeoArch. It should feel as simple as a high-quality chat product when the user only wants to ask a question, while progressively exposing files, images, tools, system capabilities, MCP, Skills, artifacts and long-running agent work when the task needs them.

The product is not a dashboard around an LLM. The conversation is the primary canvas. Complexity appears in context, and disappears again when it is not needed.

Security authority never comes from model output, prompts, Skills, MCP descriptions or presentation blocks. Privileged actions remain behind typed capabilities, Router policy, owning services, explicit confirmation where required and verification.

## Core product loop

A first-time user must be able to complete this flow without reading repository documentation:

1. Install Meo AI from the normal MeoArch software path.
2. Open `Meo AI` from the application launcher.
3. Connect a model through Meo Account, a supported cloud provider, a local model, or an OpenAI-compatible endpoint.
4. Start a chat immediately.
5. Paste text, attach files/images, or select a workspace/repository when needed.
6. Receive rich text, code, files, cards, citations and artifacts in the conversation.
7. Allow or deny actions when a tool needs permission.
8. Observe what the agent is doing and stop it at any time.
9. Close the app and later reopen the same conversation with its visible outputs restored.
10. Find previous chats and continue work without rebuilding context manually.

If any of these steps requires knowledge of Newelle internals, environment variables, a development service endpoint or repository layout, the product loop is incomplete.

## Information architecture

### Main application

The main window has four conceptual areas, but only the relevant ones are visible:

- **Conversation navigation**: new chat, search, recent conversations and workspaces/projects.
- **Conversation canvas**: user messages, assistant content blocks, tool activity, confirmations and inline artifacts.
- **Composer**: text input, attachments/context, current model, stop/send and optional quick controls.
- **Artifact/task pane**: appears only when a file, document, code artifact, generated output or long-running task benefits from a dedicated surface.

The default state should remain visually quiet. Settings, MCP, Skills, model routing and permissions are not permanent dashboard chrome.

### Settings

Settings should expose at least:

- Account and provider connections
- Default model and per-conversation model
- Advanced model routing (Title / Judge / Reasoning / Execution)
- Local models
- Skills
- MCP servers
- Tool permissions and approval defaults
- Files/workspace access
- Memory and history
- Privacy and data handling
- Usage/cost information where the provider can supply it
- Appearance/accessibility
- Diagnostics

## Conversation content model

A conversation is not a sequence of plain strings. A visible turn is an ordered set of typed blocks.

```text
Conversation
  -> Turn
       -> TextBlock
       -> MarkdownBlock
       -> CodeBlock
       -> ImageBlock
       -> AttachmentBlock
       -> CitationBlock
       -> ToolActivityBlock
       -> ConfirmationBlock
       -> PresentationBlock
       -> ArtifactBlock
       -> ErrorBlock
```

The service owns stable block identity and ordering for persistent blocks. The frontend owns rendering. Unknown executable payloads are rejected; the model never supplies arbitrary QML/HTML/JavaScript for native execution.

### Required text rendering

P0:

- CommonMark-style Markdown basics
- headings, lists, emphasis, quotes
- fenced code blocks
- inline code
- copy message
- copy code block
- selectable text
- links with explicit external-open behavior
- very long response virtualization / bounded rendering cost

P1:

- tables
- citations/source chips
- LaTeX/math where supported
- expandable long tool output
- message retry/edit/branch

## Input and context

### Text and clipboard

The composer must handle both short prompts and very long pasted text.

For large paste operations the product should:

- never freeze the UI while inserting text;
- detect large clipboard input and offer `Attach as text` rather than forcing thousands of lines into the visible composer;
- preserve UTF-8, CJK, emoji and line endings safely;
- show size/token estimate when available;
- allow removing the pasted context before send;
- avoid silently truncating user input;
- store large pasted content as a conversation attachment/context object when that is more stable than embedding it in the message body.

A practical policy is to keep ordinary paste inline, and convert sufficiently large input into a named text attachment with a short visible chip.

### Files

P0 file input:

- file picker
- drag and drop
- paste file where the desktop clipboard exposes a file URL
- multiple attachments
- remove before send
- visible file name, type and size
- clear unsupported/too-large error states
- explicit workspace permission when the agent needs repeated access beyond one attached file

Files should be represented by stable attachment IDs and metadata, not by injecting local paths directly into prompts.

The product should distinguish:

- **one-shot attachment**: readable for this request/conversation according to policy;
- **conversation file**: retained as part of this chat;
- **workspace file**: belongs to a selected project/repository and may be read or edited through workspace tools;
- **generated artifact**: created by the agent and offered back to the user.

P1 file handling:

- folder/repository selection
- file preview
- diff view before/after edits
- open in owning application
- reveal in file manager
- download/save-as for generated files
- version/revision history for agent-generated or edited artifacts where practical

### Images

P0 image input:

- image picker
- drag and drop
- clipboard image paste
- thumbnail preview
- remove/replace before send
- dimensions/type/size metadata
- model capability check before submission

The router should choose or require a vision-capable model when image understanding is needed. If the selected model cannot process images, the UI must say so and offer a compatible model rather than dropping the image silently.

P1:

- multiple-image comparison
- image annotations/crops as explicit derived attachments
- screenshots from MeoArch with user-visible capture confirmation
- generated-image output as an artifact, not an opaque markdown URL

## Output formats and generated files

Meo AI must support outputs that are useful outside the chat.

### Inline outputs

P0:

- formatted text
- Markdown
- code
- structured key/value or table presentation
- native cards for compact status/context

### File outputs

The agent may create a file only through a typed file/artifact tool. The model should not claim a file exists until the owning tool reports success.

P0 generated file types should be format-agnostic at the protocol level and support at least:

- `.txt`
- `.md`
- source/code files
- `.json`
- `.csv`

The UI should show generated files as artifact blocks with:

- name
- type
- size
- creation/update status
- open
- reveal/save/export action as appropriate

P1 can add richer first-class renderers/workflows for:

- PDF
- DOCX
- PPTX
- XLSX
- images
- archives

These formats must be produced by dedicated tooling/libraries, not by asking the model to emit binary/base64 into the conversation.

### Artifact pane

When an output benefits from a larger dedicated surface, open it beside the conversation rather than expanding the chat indefinitely.

Examples:

- document/report preview
- code/file editor or diff
- spreadsheet/table
- generated image
- diagram
- long research result
- task execution summary

Artifacts remain associated with the originating conversation and can be reopened later.

## Tool activity and agent execution

A finished AI product must make agent work observable.

The UI should normalize tool execution into an activity timeline such as:

```text
Working
  ✓ Read 14 files
  ✓ Searched workspace
  ✓ Updated Main.qml
  ● Running native tests…
```

Each activity has stable identity, state and optional details:

- queued
- running
- awaiting_confirmation
- completed
- failed
- cancelled

Normal successful steps stay compact. Failures, destructive actions, diffs and confirmation-required operations can expand.

`Stop` cancels further agent work but never falsely claims rollback of an operation already committed by another subsystem.

## Tool model

Meo AI should treat tools as typed capabilities with provenance, schema and authority information.

A tool record should eventually expose non-secret metadata such as:

- stable tool/capability ID
- display name
- provider/source (`builtin`, `system`, `skill`, `mcp`, `extension`)
- input schema
- output schema or result family
- read-only vs state-changing
- confirmation policy
- workspace/file scope
- network requirement
- current availability/health

The model receives only the capabilities enabled for the active request/workspace/policy.

## Tool chain / execution graph

A user request may require multiple steps. The runtime should represent this as a request-local execution graph rather than as unstructured hidden model behavior.

Conceptually:

```text
User request
   -> Reasoning / routing
   -> plan
   -> tool/model step
   -> result
   -> judge/verification if needed
   -> next step
   -> final response/artifact
```

Requirements:

- request-local IDs for every tool step;
- cancellation propagation;
- bounded retries;
- no duplicate side effects after transport reconnect;
- explicit dependencies between steps when available;
- tool results are data, not authority;
- a model may propose the next action but deterministic policy decides whether the action is permitted;
- long-running external operations are queried from their owning service instead of inferred from chat text.

P1 should expose enough of this graph to power a compact task/activity view. P2 may support user-editable plans or step retry where safe.

## Skills

A Skill is reusable behavior/instruction/tool composition, not a permission grant.

Product requirements:

P0/P1 boundary:

- list installed Skills
- search/filter
- enable/disable
- show source/author where known
- show what tools/integrations the Skill expects
- show whether a Mode/runtime override changes the configured state
- inspect the Skill text/manifest before enabling where practical
- clear warning for untrusted third-party Skills

A Skill must never silently gain file, network or system authority merely because it is enabled. Effective capabilities remain constrained by tool/workspace/policy layers.

Skill management belongs in Settings/Integrations, with contextual shortcuts from a conversation when a missing Skill is relevant.

## MCP

MCP is an integration transport, not a trusted security boundary.

P1 native MCP product surface should support:

- server list
- add/configure supported server types
- connect/disconnect
- health/status
- tool/resource/prompt inventory
- per-server enable/disable
- workspace/profile scope
- clear display of network/local process provenance
- secrets stored outside QML/chat history
- remove server
- diagnostics/log summary without exposing credentials

Before enabling a server, the UI should make high-risk properties visible where known, for example:

- can access local files
- launches a local process
- can reach the network
- exposes write/state-changing tools

MCP tool descriptions remain untrusted input. They may describe tools but do not determine OS permission.

## Built-in system tools

MeoArch-native actions should use typed System AI Router capabilities rather than generic shell execution when a first-party owner API exists.

Examples:

- audio/media
- Bluetooth/Wi-Fi
- display/power
- settings navigation
- app launching
- package/software workflows
- file search
- diagnostics/repair

The UI should show the actual target and verified result for state-changing actions when the owner can provide read-back.

## Shell and coding tools

Coding is an important Meo AI workflow, but arbitrary shell access is high-risk.

Product requirements before broad release:

- explicit workspace root
- path containment where applicable
- clear read/write/execute distinction
- command preview for risky actions
- timeout/resource limits
- output truncation with expandable full logs
- environment/secrets filtering where possible
- network policy or at least visible network use for tools that need it
- diff-first UX for file edits
- Git status awareness
- no silent privilege escalation

A powerful execution model does not change these permissions.

## Models and provider routing

### Normal model selection

P0 must provide a real current-model picker for the conversation. This takes precedence over advanced role routing in the main UI.

The product should expose model capability hints such as:

- tools
- vision
- structured output
- context class
- local/cloud
- latency/cost class where known

### Advanced model roles

Title / Judge / Reasoning / Execution belong under advanced routing until request-local multi-model execution is real.

- `title`: cheap naming and tiny summaries
- `judge`: structured classification/ranking/routing, never security approval
- `reasoning`: primary planning/composition
- `execution`: tool-oriented implementation

The UI must never label a preference `Active` unless the runtime really executes that role independently.

## Conversation history and persistence

P0:

- real conversation list
- generated/edited title
- timestamps
- resume
- rename
- delete with confirmation/recovery policy
- search by title/text

Persistent conversation content must include all user-visible durable blocks required to reconstruct the session, not only plain user/assistant text. Ephemeral live telemetry may be omitted, but durable artifacts, file references, important tool outcomes and native presentation blocks should not disappear after restart.

P1:

- folders/projects/workspaces
- pinned chats
- chat branching
- export conversation

## Workspaces / projects

A workspace is a durable context boundary for substantial work.

It may contain:

- root folder/repository
- project instructions
- allowed files/paths
- conversation set
- project attachments/knowledge
- enabled Skills/MCP integrations
- tool policy overrides that never exceed system policy
- generated artifacts

Workspace selection should be explicit and visible in the composer/header when active.

## Memory

Memory is separate from chat history and project files.

Before native memory is enabled as a product feature, the frontend contract must support:

- what is stored
- source/provenance
- scope
- search/review
- disable
- delete/forget controls supported by the underlying memory system

Do not expose a vague `Memory on` toggle before the underlying semantics are trustworthy.

## Errors, offline and recovery

The default UI is quiet when healthy and explicit when unhealthy.

Required states include:

- AgentService unavailable
- provider unavailable
- model unavailable
- authentication/account problem
- attachment unsupported/too large
- workspace permission denied
- tool failed
- MCP disconnected
- request interrupted by service restart
- conversation restore failure

Each recoverable error should offer the next useful action: retry, reconnect, choose another model, open settings, remove attachment, or inspect details.

## Notifications and background work

P1:

- long-running tasks can continue when the main window is not focused after runtime durability is safe;
- desktop notification on completion/confirmation/error;
- task center showing active/recent work;
- reopening a task returns to its conversation and activity state.

Do not claim background durability until AgentService request persistence and restart semantics support it.

## Product release gates

### P0 — usable daily chat/agent product

A release candidate must have:

1. Meo AI application identity, icon, desktop entry and one normal installation/launch path.
2. Reliable AgentService activation or an equally reliable final local transport.
3. Provider/model onboarding with a real current-model picker.
4. Real conversation history/navigation.
5. Markdown/code/select/copy/retry-quality transcript rendering.
6. Long-paste handling.
7. File and image attachments with model capability validation.
8. Observable tool activity, confirmation and cancellation.
9. Persistent visible conversation blocks sufficient to reconstruct completed work.
10. Basic generated file/artifact handling.
11. Clear error/reconnect states.
12. Live MeoArch acceptance for provider streaming, cancellation and the supported system-tool subset.

### P1 — integrated workspace product

- project/workspace context
- richer files and diffs
- MCP management UI
- Skills management UI
- citations/research surfaces
- richer artifact pane and common document formats
- background task center
- notification integration
- provider usage/cost surfaces where available
- memory UI only after a stable memory contract exists

### P2 — advanced agent platform

- true multi-model role routing
- durable execution across restart where safe
- rich artifact editors
- scheduled tasks
- voice/live workflows
- image generation/editing workflows
- advanced plan/step controls
- extension ecosystem hardening and sandboxing

## Current implementation reality

The Newelle-derived engine already contains many capabilities that are useful raw material, including multiple providers/local models, terminal execution, extensions, Skills, MCP, long-term memory, document chat, image generation, web search, file permissions, scheduled tasks, file management, rich formatting and multi-chat features. Those upstream capabilities do not count as finished Meo AI product features until they cross the native AgentService/frontend boundary with Meo-owned UX, persistence, security semantics and live acceptance.

The current native Meo client already proves several important foundations: conversation transport, streaming, Stop/cancellation, reconnect semantics, presentation cards, tool confirmation and model-role preferences. It is still an engineering preview because the complete product loop above is not yet closed.

## Design rule

When choosing between adding another visible feature and completing an incomplete user loop, complete the loop.

A simple surface with real history, real files, real tools and reliable recovery is preferable to a visually impressive surface full of placeholders.