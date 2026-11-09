> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

# Chat, Work and Code product model

Status: product/design contract. This document describes the intended behavior; a listed behavior is not automatically implemented on every client or device. See the implementation notes at the end.

## Product shape

Meo AI has two primary interaction modes:

- **Chat** is a conversation-first assistant. It answers questions and can use lightweight tools such as web search, connected-app lookups, memory and user-attached files. A Chat conversation has no bound local workspace and does not receive general filesystem, shell, Git or project-folder access.
- **Work** is a task-first agent. A Work task must have an explicit execution target device and a workspace before it can perform workspace operations. It can read and change files, run approved commands and keep task progress visible and resumable.

**Code is a Work profile, not a third top-level mode.** Work offers at least two profiles:

| Work profile | Intended tasks | Typical capabilities |
| --- | --- | --- |
| General | Research, document creation, file organization, data tasks and other non-coding work | Workspace files, document tools, web and connected apps; shell only when needed and permitted |
| Code | Software development and repository maintenance | Everything appropriate to General, plus repository-aware context, Git, terminal, build, test and debugging tools |

The profile selects task instructions, Skills, suggested tools and defaults. It does not create a separate account, conversation system or Agent Runtime. The same Work task can change profile only through an explicit user action; the UI must make any resulting tool/permission changes visible.

## Chat boundaries

Chat is deliberately useful without becoming a hidden Work session.

- Chat may use lightweight, explicitly available tools: search/fetch, connected-app lookups, memory and attached-file reading.
- Chat does not silently bind to a device folder, scan a project directory, run shell commands or modify local files.
- Being inside a Project may add that Project's instructions, memories and linked context to the conversation. It does **not** grant access to a device's project folder.
- A user can explicitly choose **Open in Work / Move to Work** when a task needs a workspace, changes files, runs commands or needs a multi-step execution environment.
- The conversion carries the selected conversation context and user-selected attachments, then asks for a target device and workspace if they are not already defined. It must not silently grant new permissions or start side effects.
- Moving a task back to Chat is also explicit. It stops workspace execution and preserves the conversation history; it does not imply that local files are uploaded.

## Work task setup and lifecycle

A Work task is bound to **one primary target device** and **one active workspace** at a time.

1. The user starts Work from the Work entry point or from a Project's **Start Work** action.
2. The user selects an online, authorized device that advertises the capabilities needed for the task.
3. The user selects an existing local folder, creates a new workspace, or chooses an explicitly offered remote source to materialize on that device.
4. The user selects General or Code. The selected profile determines the task guide, relevant Skills and available tool set.
5. The task starts with its permission mode visible. The UI streams the plan when one is needed, assistant output, tool calls, approvals, results, changed files and final verification.
6. The task can be stopped, resumed after transport interruption, and inspected later. Reconnect resumes the same run/request; it must not submit a replacement that could repeat side effects.

### Workspace materialization

- A folder already on the target device is used in place; Meo does not make an unnecessary second copy.
- A remote Git repository can be cloned into a user-selected empty folder on the target device. Refuse a non-empty destination rather than overwriting it.
- Other remote files or generated starter material may be downloaded/copied only after the user chooses the source and destination. Show what will be copied and where.
- Local workspace contents remain on the target device by default. Account sign-in, Project sync or Work history sync must never silently upload the folder.
- Work artifacts may be stored locally and selectively exported or uploaded through an explicit action. A cloud conversation/task record is not the same thing as cloud storage for the workspace.
- If the target device disconnects, the task pauses and offers reconnect or an explicit re-target/migration flow. Never silently run the task on another device.

### Project relationship

A Project is the durable home for shared instructions, memories, conversations and repository identity. Each device may link that Project to its own local folder/environment because filesystem paths differ by device. Starting Work in a Project uses the selected device's linked folder. Project metadata can follow the account; local folders and their contents do not.

A task not attached to a Project may use a general Work folder on the chosen device. Attachments in Chat, Project files and Work outputs remain distinct data classes.

## Tool execution and safety

Work uses an agentic tool loop:

`model response → typed tool request → policy/approval gate → target-device execution → tool result → model response`

- Tool definitions describe names, schemas, effects and risk classes. The model requests a tool; it never executes it directly.
- The Rust Core owns the shared request/event/state contract. The target device's local executor performs filesystem and process operations.
- Permission modes are explicit and visible: Ask, Workspace, Auto and Full. Workspace is the normal Work default; Full is explicit per-project/per-device opt-in and is never silently inherited by a remote task.
- Destructive operations, actions outside the workspace, credential access, privilege escalation, package installation and network sends require the configured approval or hard-stop behavior.
- Tool results, file contents, Skills, MCP output and web content are untrusted data, not instructions. Prompt text and plugin descriptions never grant capabilities.
- Privileged OS actions remain behind the typed System AI Router and its confirmation/Polkit policy; Work does not implement a second privileged executor.
- A task's target device and workspace are visible throughout execution. Approval shows the exact command, diff or action and its target.

Chat and Work may share provider adapters, message/content-block formats, tool schemas and an activity presentation contract. They retain distinct execution scopes: Chat's lightweight tool access must not inherit Work's workspace authority.

## Cross-device and cross-client behavior

- Desktop is the strongest local Work executor.
- Android is a first-class controller and may direct Work to an authorized desktop device; it must not imply that Android can execute desktop-only operations locally.
- Web is a controller for authorized devices and cloud capabilities; it must not pretend to have access to the browser host's filesystem.
- A remote Work request is authenticated, bound to one registered device and scoped to that device's approved capabilities. Device sessions are revocable.
- All clients render the same Core-owned task state and events. They may adapt presentation to their platform, but must not invent different execution semantics.
- Work task history and durable metadata may sync through Meo API. Local workspace files remain local unless the user explicitly exports or uploads them.

## Ownership boundaries

| Component | Authority |
| --- | --- |
| Rust Core (`meo/core-rs/`) | Conversation/task state, tool protocol, run lifecycle, events, replay/reconnect and cross-client contracts |
| Meo API | Account-owned conversations, Projects, memory, Skills/plugins, AgentRun coordination and model broker |
| Meo Account | Identity, sessions and encrypted provider credentials |
| Device Agent / device bridge | Authenticated relay to the selected device's local executor; no second Agent engine and no unrestricted remote shell |
| Local workspace executor | Filesystem, process, Git and project-local operations within policy |
| System AI Router | Privileged system capabilities, confirmation, verification and Polkit |
| Desktop / Android / Web clients | Presentation and platform-specific device interaction only |

## Implementation status and source map

The repository already contains parts of this model, but not the complete target:

- `AGENTS.md` defines Chat, Work, Projects and Skills as the primary product hierarchy and requires an explicit Work target device.
- `meo/core-rs/src/cloud/agent.rs` defines Work tool requests and permission gating; `workspace.rs` owns the current workspace execution path.
- `meo/core-rs/src/cloud/app.rs` owns the shared product view/actions, Work task creation/conversion and project actions.
- `meo/docs/projects-and-environments.md` documents per-device Project folders and `.agent/` state.
- `meo/docs/ui-redesign.md` documents the shared Chat | Work shell and current client presentation.
- `docs/harness-alignment.md` documents the Agent Loop, DSH concepts, tool pipeline, permission modes and prompt safety.

Known gaps recorded in the current design include the full Rust device protocol/local executor migration, robust remote task resume, cross-device Work task identity/state, Android workspace execution, richer Code-specific tools and per-tool permission rules. Do not describe these as completed merely because a navigation item or compatibility implementation exists.

Implementation work must follow `docs/ownership.md`: define cross-platform behavior in the Rust/API contract first, then render it in QML, Compose and React. Do not add new product Agent logic to the paused Python/device compatibility layers.
