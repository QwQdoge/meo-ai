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
- the user selected a unified product repository on 2026-10-18. Meo-owned Web
  source belongs under `meo/web/client`, alongside desktop, Android and Core.
  Preserve import provenance/license and keep the old Web repository for rollback;
  do not import its unrelated Express/Mongo backend or generated artifacts.

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


## Selected UI architecture (2026-10-18)

- Desktop applications on Linux, Windows and macOS use C++/Qt/QML + MeoUI.
  Keep desktop application/platform integration in C++; consume shared Core/API
  contracts instead of mandating a Rust UI binding migration.
- Web uses React/TypeScript; Android uses Kotlin/Compose. No shared rendering
  framework is required.
- `meo/ui-schema/` is the only editable product configuration for navigation
  placement/order, page hierarchy/states, feature entry points and token aliases.
  MeoUI owns the referenced shared token values and reusable controls.
- Render primary/secondary groups natively, including compact navigation. A
  placement change must preserve destination identity, state and permissions.
- Use a restrained Pixel/Material direction: function and information first,
  quiet surfaces, limited accents, subtle motion and system reduced motion.
- Schema data never executes code, grants capabilities or replaces server-side
  authorization. Page/feature declarations do not prove implementation parity.
