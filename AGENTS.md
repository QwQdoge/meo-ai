# Meo AI contributor rules

Preserve Newelle upstream provenance and GPL-3.0 license. Keep product-specific
work under `meo/`; limit `src/` patches to documented integration seams.
Do not delete GTK while the core still imports Gtk/Adw/WebKit.

Read `docs/ownership.md` before changing repository layout, root Newelle-derived
code, compatibility adapters, packaging direction, or the future native/legacy split.
The root Newelle tree is migration/compatibility infrastructure; `meo/` is the
current Meo-owned product direction.

MeoUI owns shared controls and tokens. Meo.System, Account, SystemTransaction,
OmniStore and repair authorities retain their typed privilege boundaries.
Prompts, Skills and MCP descriptions are never security enforcement.

Headless separation rules:
- `meo/service/` is the stable headless service layer and must not import GTK,
  Adwaita, WebKit, `src.ui` or `src.ui_controller`.
- `meo/system/` is the unprivileged SystemTool/Router-client layer and follows
  the same no-GUI import rule.
- temporary Newelle compatibility code belongs under `meo/adapters/` and may
  wrap injected GTK-era objects, but should not leak UI objects into service APIs.
- frontends/transports never own request IDs, decision IDs or execution handles.
- SystemTool may call the existing `org.meo.AIRouter1` typed API, but Router
  daemon/executor ownership, KIO/PulseAudioQt/KWin integrations, Polkit and
  Repair authority must not be copied into `meo-ai`.
- Router caller binding requires SubmitRequest/GetRequest/DecideRequest to reuse
  one session-bus connection; do not replace this with per-call subprocesses.

Unified web/cloud/device rules:
- `meo/web/` owns Meo web integration and upstream policy, not raw provider keys.
- `meo/cloud/` owns AI-specific conversation/device/AgentRun contracts; Meo
  Account remains the authentication/session and encrypted BYOK authority.
- `meo/device/` may bridge authenticated remote work to local AgentService, but
  it must not become a second agent engine, a generic unauthenticated remote
  shell, or a privileged System AI Router replacement.
- a remote AgentRun may bind to one local AgentService request; reconnect must
  resume that request/event stream rather than submitting a replacement request.
- local workspaces stay local unless an explicit file-upload path says otherwise.
- do not vendor a large web upstream merely for physical repository purity;
  record its exact upstream commit/license and keep the Meo patch surface small.

TODO — remote realtime sync:
- evaluate Neon Realtime for cross-device synchronization of conversation metadata,
  completed messages, remote job/device state, and account/settings changes.
- keep AI token streaming on the Meo API transport (for example SSE); do not write
  token-by-token output through Postgres/Realtime. Persist completed state, then
  use realtime only to fan out durable changes to other clients.
- treat realtime as an enhancement, not a core dependency: clients must be able
  to reconnect/resync or fall back without breaking normal Chat or Work flows.

Unified product and navigation rules:
- Meo AI is one product across Web, Linux, Windows, macOS and Android. Keep the
  information architecture and feature names aligned even when platform layouts
  and capabilities differ.
- the primary user-facing hierarchy is `Chat`, `Work`, `Projects`, and `Skills`.
  These are task surfaces, not configuration categories.
- compact/mobile layouts must keep that same hierarchy in a left navigation
  drawer opened from a visible hamburger button or a left-edge swipe. Do not
  invent a separate mobile-only bottom navigation model for these destinations.
- `Chat` is conversational assistance. `Work` is agentic execution with an
  explicit target device/environment, visible progress, permission boundaries,
  and resumable task state. Never silently turn an ordinary Chat into Work.
- `Projects` owns persistent task context/files/conversations. `Skills` owns
  reusable user-visible capabilities. Do not use either as a dumping ground for
  settings or low-level runtime state.
- provider configuration, model routing/"models by job", memory management,
  MCP/server configuration, diagnostics, account/session controls and connector
  administration belong under Settings unless they are temporarily surfaced by
  the current task context.
- attachments belong to the current Chat; project files belong to a Project;
  Work outputs belong to Work artifacts. Avoid a generic top-level `Resources`
  bucket when the resource has a more specific owner.
- desktop is the strongest local Work executor. Android may expose a smaller set
  of local capabilities and should also act as a first-class controller for
  remote Work. Web must not pretend to have direct local-machine privileges; it
  controls authenticated online Meo devices through cloud/device contracts.
- remote device control must use authenticated device registration, revocable
  per-device sessions, scoped capabilities, user-visible target selection and
  explicit approval for privileged operations. Never expose a generic remote
  shell as the product contract.
- Connectors should follow one capability/permission model whether implemented
  by an official integration, an MCP adapter or a future Meo plugin. AI code
  should receive brokered capabilities rather than long-lived third-party tokens.
- Meo Account should support one-time device authorization followed by silent
  session refresh until logout, revocation, expiry policy or security reauth.
  Store refresh/session secrets in the platform secure store; do not persist
  them in ordinary config files.
- share protocol/data models/design tokens across clients where practical, but
  do not force every platform to share one renderer. Web and native clients may
  use different rendering stacks while remaining the same product.

Context and token-budget invariants:
- `meo/service/context_engine.py` owns provider-agnostic context selection. Keep
  provider SDKs, storage and UI concerns outside the strategy interface.
- raw conversation messages and raw tool results are authoritative. Context
  trimming/compaction is model-facing and non-destructive; never delete or
  overwrite raw history merely to save prompt tokens.
- every compacted tool result must retain a stable raw source reference so a
  later agent step can retrieve the original result when detail is needed.
- keep recent turns verbatim when budget permits. Rank older evidence by current
  task relevance, recency and explicit importance, and expand context when
  selection confidence is low instead of silently pretending a lossy summary is
  authoritative.
- persistent Memory and transcript history are different data classes. Structured
  task memory may include decisions, constraints, files, blockers and TODOs, but
  it must retain source references and obey the same user memory controls.
- static system instructions, tool schemas and capability descriptions should be
  serialized deterministically and kept separate from dynamic task context so
  provider prompt caches can hit. Do not inject timestamps/random IDs into the
  static prefix unless semantically required.
- terse/"caveman" output is permitted only for internal planner/executor/subagent
  handoffs. Never force terse mode onto the final response shown to the user.
- context diagnostics exposed to UI/telemetry are aggregate-only: token counts,
  saving ratio, selected item counts, strategy, confidence and fallback status.
  Never expose hidden system prompts, private memory contents or raw tool output
  through diagnostics.
- TOMC, LCC or future compression algorithms must implement the context strategy
  abstraction instead of being coupled directly to providers/frontends. Do not
  vendor or copy an external algorithm without first checking its license.
- legacy backends that build history internally must not claim Meo context/token
  savings unless Meo actually controls the model-facing history for that request.
- tests for context work must cover recent-turn preservation, relevant-old-item
  selection, tool-output compaction/raw refs, low-confidence fallback, aggregate
  diagnostic privacy and the final-user-response terse-mode guard.

Do not move/delete the Newelle-derived root tree as incidental cleanup. The split
gates are defined in `docs/ownership.md`; until those gates are met, reduce coupling
through adapters rather than creating a second engine copy or breaking the build.

Inspect status and nearest code/tests before changes. Preserve unrelated work.
For Python changes run `python3 -m compileall -q src meo/service meo/system meo/adapters meo/runtime meo/tools meo/device`,
`python3 meo/tools/check_headless_imports.py`, and
`python3 -m unittest discover -s meo/tests -p 'test_*.py' -v`.
For native changes configure/build `meo/` with MeoUI and run CTest offscreen.
Distinguish mock protocol tests, native builds, real agent/provider execution,
and live Plasma integration in reports. No release/tag/signing is implied.
