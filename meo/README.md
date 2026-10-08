# Meo AI preview

Native C++/QML MeoUI client for the Newelle-derived agent engine. GPL-3.0;
upstream Newelle attribution and license remain in the repository root.

See [architecture](docs/architecture.md), [AgentService contract](docs/agent-service-contract.md)
and [upstream policy](docs/upstream-policy.md).

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

The service refuses non-loopback binds. To make the native QML client use the
new contract instead of the legacy Newelle API:

```sh
MEO_AI_SERVICE_ENDPOINT=http://127.0.0.1:8765 ./build/meo/meo-ai
```

In AgentService mode the native client:

- creates and persists a Meo conversation ID;
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

## Phase A compatibility preview

If `MEO_AI_SERVICE_ENDPOINT` is unset, the native client keeps the Phase A path
for now. Build/install **this fork's** Newelle engine, enable its API interface
on `127.0.0.1:8080`, configure a nonempty API key and start:

```sh
MEO_AI_API_KEY=... \
MEO_AI_ENDPOINT=http://127.0.0.1:8080 \
./build/meo/meo-ai
```

The legacy path still understands inherited `/models`, `/model`, `/tools`,
`/skill`, `/list_chats`, `/resume` and `/option` commands. It remains only a
compatibility path while Phase B reaches real-provider parity.

Do not put credentials in Git or prompt files. Upstream shell/MCP/extensions are
not an OS sandbox. Use a dedicated test workspace with reviewed tools. Router,
Repair, package/ISO and privileged integration remain separate migration tracks.
