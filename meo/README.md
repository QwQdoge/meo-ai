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
python3 -m unittest discover -s meo/tests -p 'test_*.py' -v
```

MeoUI is built as a dependency, not vendored. Installing this preview also
installs the built MeoUI module through its existing CMake install rules.

## Current runtime

Phase A still uses this fork's Newelle loopback v2 API and requires the GTK-era
engine process. The QML client is not yet wired to the Phase B `AgentServiceCore`.
Phase B now defines a UI-free backend adapter, request/decision identity,
cancellation semantics, a compatibility bridge for legacy tool events and a CI
import gate for `meo/service`. These pieces are foundations, not a claim that the
full Newelle runtime is headless yet.

## Run the Phase A preview

1. Build/install **this fork's** Newelle engine using the upstream Meson/Flatpak
   instructions and dependencies. Stock Newelle lacks the Meo overlay/events.
2. In Newelle Interfaces enable the API interface on `127.0.0.1:8080`, configure
   a nonempty API key, and select your existing local model/provider. Leave
   the API `use_bang_for_commands` setting off. Keep GTK running for this phase.
3. Import `meo/skills/system-diagnostics/SKILL.md` in Newelle Skills if desired;
   this example is not enabled automatically.
4. Start the native client with the same API key in `MEO_AI_API_KEY` and optional
   `MEO_AI_ENDPOINT=http://127.0.0.1:8080`, then run `./build/meo/meo-ai`.

Do not put credentials in Git or prompt files. Runtime connection keys belong
in a local launch environment; the native client does not persist them.
`/models`, `/model`, `/tools`, `/skill`, `/list_chats` and `/resume` are inherited
commands. Restarting keeps the same API session; New chat uses the upstream
`/new` command.

This phase is not headless and the Phase A client still has no real request-local
cancel endpoint. Disconnecting the UI does not stop work. Upstream shell/MCP/
extensions are not an OS sandbox. Use a dedicated test workspace with reviewed
tools. Actual provider, desktop and Repair integration require their own
acceptance evidence.
