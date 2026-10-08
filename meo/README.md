# Meo AI preview

Native C++/QML MeoUI client for the Newelle-derived agent engine. GPL-3.0;
upstream Newelle attribution and license remain in the repository root.

See [architecture](docs/architecture.md), [AgentService contract](docs/agent-service-contract.md),
[SystemTool contract](docs/system-tool-contract.md) and [upstream policy](docs/upstream-policy.md).

## Build

On Arch Linux, install Qt 6.8+ base/declarative/shadertools/tools, CMake and a C++
compiler. Clone MeoUI alongside this repository.

```sh
cmake -S meo -B build/meo -DMEO_UI_ROOT="$PWD/../MeoUI" -DBUILD_TESTING=ON
cmake --build build/meo --parallel 2
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software ctest --test-dir build/meo --output-on-failure
python3 meo/tools/check_headless_imports.py
python3 -m meo.runtime.main --self-check
python3 -m unittest discover -s meo/tests -p 'test_*.py' -v
```

MeoUI is built as a dependency, not vendored. Installing this preview also
installs the built MeoUI module through its existing CMake install rules.

## Phase B AgentService

Phase B now has a maintained loopback transport over `AgentServiceCore`. HTTP/SSE
is an implementation detail; the stable semantics are conversation IDs,
service-generated request IDs, service-generated decision IDs, ordered events,
explicit cancellation and request-stream reconnect.

The transitional `meo.adapters.headless_newelle:create_backend` factory mirrors
Newelle's existing headless controller initialization without importing
`src.main` or constructing a window. It temporarily shims the controller's two
known UI-only imports and then re-runs the dynamic headless probe. If any real
Gtk/Adw/WebKit or `src.ui*` module is pulled in later, construction fails instead
of silently claiming to be headless.

On a machine with the full Newelle runtime dependencies and GSettings schema,
first validate the extraction:

```sh
python3 -m meo.runtime.main --self-check \
  --backend-factory meo.adapters.headless_newelle:create_backend
```

Then start the service from the checkout:

```sh
python3 -m meo.runtime.main \
  --backend-factory meo.adapters.headless_newelle:create_backend \
  --host 127.0.0.1 \
  --port 8765
```

The service refuses non-loopback binds. The native QML application now uses
AgentService at `http://127.0.0.1:8765` by default when neither transport endpoint
is configured. Override the service origin when needed:

```sh
MEO_AI_SERVICE_ENDPOINT=http://127.0.0.1:8765 ./build/meo/meo-ai
```

An explicitly configured `MEO_AI_ENDPOINT` selects the Phase A compatibility
transport only when `MEO_AI_SERVICE_ENDPOINT` is absent. The app never retries a
submitted AgentService request through the legacy transport because replaying a
message could duplicate tool or system side effects.

In AgentService mode the native client:

- creates and persists a Meo conversation ID;
- restores persisted user/assistant message history on startup while filtering
  Newelle-internal console, command, file and folder records from the UI contract;
- clears a stale persisted conversation ID when the service reports that it no
  longer exists;
- streams ordered events carrying request-local `seq` values;
- uses `request_id` and `decision_id` for tool choices;
- can submit a tool decision while the model/tool SSE request remains open;
- exposes a real Stop action that calls `CancelRequest` rather than merely
  disconnecting the stream;
- queues an early Stop until the request ID is known;
- treats an SSE disconnect as transport loss, not cancellation;
- automatically reconnects a live request with
  `/v1/requests/{requestId}/events?after={lastSeq}` and ignores duplicate
  sequence numbers;
- limits automatic reconnect attempts and does not loop on an expired journal;
- rejects non-loopback service endpoints.

The service keeps reconnect history in a bounded in-memory event journal. This
supports frontend/network reconnect while the same AgentService process is
alive; it is not durable execution across service restart. A stale reconnect
cursor is rejected explicitly rather than silently skipping missing events.

### Installed service

The Meson install now also installs:

- `meo-agent-service` in the install `bindir`;
- the Phase B `meo/runtime`, `meo/service` and `meo/adapters` Python modules
  beside the installed Newelle Python package;
- the Phase C `meo/system` Router client/contract modules;
- `meo-agent-service.service` as a systemd user unit.

The unit is installed but **not enabled automatically** by this repository. For
development/live acceptance after installing the package:

```sh
systemctl --user daemon-reload
systemctl --user start meo-agent-service.service
systemctl --user status meo-agent-service.service
```

Only after live session validation should distro packaging decide whether to
enable it by default. The service runs unprivileged with `NoNewPrivileges=yes`;
future OS authority still belongs behind the typed System AI Router/capability
policy rather than this process.

A successful headless self-check means the backend could be constructed without
loading the forbidden UI modules. It does **not** yet prove real provider
inference, cooperative interruption of every tool, session/systemd activation or
Plasma integration; those remain on the live acceptance track.

## Phase C SystemTool preview

System control is present as an **explicit opt-in preview** and remains disabled
by default. `meo-ai` does not embed desktop executors: it talks to the existing
`org.meo.AIRouter1` service over one persistent user-session D-Bus connection so
Router caller binding remains stable across submit/query/decision calls.

The Router is the authoritative source of the currently executable capability
list and each capability's `argumentSchema`. The Newelle compatibility adapter
turns each listed capability into one fixed tool using that Router-owned schema;
the model is not given a generic free-form capability ID field.

To exercise this path locally, the session needs the updated Meo Router that
publishes `argumentSchema`, and the Python runtime needs the `dbus-next` module.
Then start AgentService with the opt-in flag:

```sh
MEO_AI_ENABLE_SYSTEM_TOOL=1 \
python3 -m meo.runtime.main \
  --backend-factory meo.adapters.headless_newelle:create_backend \
  --host 127.0.0.1 \
  --port 8765
```

When enabled:

- `SubmitRequest(capabilityId, arguments)` is used; AI never delegates an action
  back through Router `SubmitText()`;
- capability IDs and parameter schemas come from `ListCapabilities()`;
- reversible requests wait for the owning component to report a terminal result;
- `awaiting_confirmation` becomes explicit Deny/Approve choices through the
  existing AgentService tool-decision path;
- confirmation UI receives bounded Router-backed title/target/impact context;
- approval uses the Router-issued request ID and fingerprint, and no model/Skill
  output can auto-approve it;
- Router rejections are surfaced as results rather than retried with guessed
  arguments.

For live Router acceptance without starting a model, the helper is read-only by
default:

```sh
python3 meo/tools/live_system_tool_check.py
python3 meo/tools/live_system_tool_check.py --read-volume
```

A state-changing volume check is only performed when explicitly requested:

```sh
python3 meo/tools/live_system_tool_check.py --set-volume 30
```

The installed systemd unit intentionally does **not** set
`MEO_AI_ENABLE_SYSTEM_TOOL=1` yet. Distro enablement waits for live D-Bus,
provider, Plasma and cancellation acceptance. Missing Router/`dbus-next` while
the preview is explicitly enabled fails closed instead of falling back to shell
commands or a second natural-language parser.

## Phase A compatibility preview

Phase A is now an explicit compatibility fallback rather than the default native
path. To select it, set `MEO_AI_ENDPOINT` and leave `MEO_AI_SERVICE_ENDPOINT`
unset. Build/install **this fork's** Newelle engine, enable its API interface on
`127.0.0.1:8080`, configure a nonempty API key and start:

```sh
MEO_AI_API_KEY=... \
MEO_AI_ENDPOINT=http://127.0.0.1:8080 \
./build/meo/meo-ai
```

The legacy path still understands inherited `/models`, `/model`, `/tools`,
`/skill`, `/list_chats`, `/resume` and `/option` commands. It remains only a
compatibility path while Phase B reaches real-provider parity. A failed or
interrupted AgentService request is never automatically replayed through this
legacy endpoint.

Do not put credentials in Git or prompt files. Upstream shell/MCP/extensions are
not an OS sandbox. Use a dedicated test workspace with reviewed tools. Router,
Repair, package/ISO and privileged integration remain separate migration tracks.

## Real-provider acceptance client

Build the opt-in `meo-ai-live-client` target to drive the production QML client
against an explicitly supplied `MEO_AI_SERVICE_ENDPOINT` on the current display.
Use a dedicated `XDG_CONFIG_HOME`; `--prompt TEXT`, `--cancel-after-delta`,
`--history`, and `--screenshot PATH` cover streaming, cancellation, history and
window captures. `--require-tool` requires a real tool event: model text that
claims an action or invents a result does not satisfy that check.

The compatibility backend initializes the selected provider without installing
optional providers or starting inherited interface servers. Its model list only
includes the selected provider; configure a different provider in the inherited
profile before selecting its models. GLib tool dispatch has its own UI-free loop.
GTK-only inherited tools still require a separately reviewed compatibility path;
use a dedicated workspace with only the tools under acceptance enabled.
