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
