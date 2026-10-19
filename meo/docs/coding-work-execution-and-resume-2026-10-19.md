# Coding Work and durable remote execution — 2026-10-19

Meo AI can use the existing AgentService, Account plugin/MCP configuration, and the authenticated AgentRun bridge to assist with coding on a connected workspace. **It cannot yet claim full GitHub edit → tests → PR → CI → merge automation on its own.** In particular, the Web UI is an AgentRun controller, not a cloud shell or coding executor. GitHub operations must come from approved tool capabilities of the selected local Agent/Account connector, not LLM text alone.

## What shipped in this change

Web Work now stores a **minimal, account-scoped reference** to the last AgentRun in browser persistent storage. It stores only run UUID, project/workspace UUID, conversation UUID, a schema version and a 30-day timestamp, not prompts, files, model output, credentials or arbitrary URLs. The UI restores the run and replays server-owned events after the browser closes and reopens. It also migrates earlier tab-session task pointers without copying old prompt text. Clearing from UI clears only the pointer and **does not cancel running work**. Cancellation is a separate authenticated server API request.

This is not a promise of process-level durability. If the cloud server or device daemon stops, their separate persistence and resume mechanisms still need testing. A persistent browser pointer does not mean the agent is running.

## Target execution lifecycle

1. Chat/Work chooses a **connected**, user-owned device and an existing approved workspace. No invented device path or automatic uploading of local files.
2. Meo AI plans the coding changes and proposes typed tool calls. GitHub connector / MCP or local capability adapters must report actual availability, access scopes and risk classes.
3. The server or owning local capability checks account/session, repo/write scope, consent and tool policy before execution. The model cannot self-grant permanent permissions. Sensitive repo changes, publishing and merging require separately authorized write actions; approved read-only operations may use a revocable standing grant if the server supports it.
4. Create one durable AgentRun. One run dispatches at most one local AgentService request. Each tool step needs stable IDs, results, errors and audit references; resumptions must never repeat a completed write.
5. The existing installed development environment (not the browser) checks out / edits / builds / tests the repo. GitHub APIs create branch/commit/PR, read CI and perform an approved merge. Do not claim edits/tests/merge until the tool reports completion.
6. Persist the run and event stream server-side. Android and Web read the same user-owned task list and IDs once the cloud exposes **list/get AgentRun** endpoints. The current cloud has single-run SSE replay and Web remembers the last pointer *per browser*, not account-wide task discovery.
7. On app close, disconnect only the event subscriber. Cloud/device task keeps running if the executor and transport remain alive. When a client returns, query run status and stream events from a known cursor, no duplicate dispatch.

## Gaps to implement before declaring ChatGPT-like coding Work

- **GitHub coding tool broker:** account-owned GitHub OAuth or carefully scoped connector, read and write capabilities, explicit repository policy, branch protections, permission receipts, CI polling, PR merge policy. No unrestricted remote shell or direct GitHub personal access token sync.
- **Cross-device run discovery:** authenticated `GET /v1/agent-runs` and `GET /v1/agent-runs/:id`, ownership checks and paginated metadata. The current API only creates, cancels, decides and subscribes via SSE; Web/Android cannot enumerate every in-flight run on a new device.
- **Durable coordinator:** persistent plan/step checkpoint, idempotency and retry mapping across cloud restarts and device reconnect. Current per-run event streaming does not prove an arbitrary agent can continue after host power loss.
- **Capability parity:** Desktop invokes AgentService locally; Web and Android control the same remote AgentRun and approvals; Account plugin metadata and tool authorization must not be confused with installed executors.
- **Acceptance:** two-account isolation, controlled test repo, one real test change/CI/PR, declined write permission, revoked grant, background browser exit/reopen, Android resume, device disconnect/reconnect, cancellation vs committed side effects, terminal status on all three clients.

## Safety boundary

The Meo AI UI never gains authority because a model says it is safe. A model can propose or assess tool risk, but only the Account/API/device policy owner can authorize execution. Standing approvals are revocable and scoped; repo writes and PR merges must comply with the owner’s policy. These are engineering capability checks, not new popups for every read-only operation.
