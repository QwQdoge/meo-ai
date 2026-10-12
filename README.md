# Meo AI

**Meo AI is the MeoArch assistant for everyday chat, local/remote agent work, and safe system actions — with one Meo experience across desktop and web.**

> Development preview. The native MeoUI frontend is the product direction; the Newelle-derived engine remains as migration/compatibility infrastructure while capabilities move behind the headless Meo service layer.

## Start here

### Native desktop preview

Meo AI's desktop client is built with C++/QML and the shared **MeoUI** design system.

```sh
cmake -S meo -B build/meo -DMEO_UI_ROOT="$PWD/../MeoUI" -DBUILD_TESTING=ON
cmake --build build/meo --parallel 2
```

Run the maintained service self-check and tests:

```sh
python3 meo/tools/check_headless_imports.py
python3 -m meo.runtime.main --self-check
python3 -m unittest discover -s meo/tests -p 'test_*.py' -v
```

For the full build, service, provider and live-acceptance workflow, see **[meo/README.md](meo/README.md)**.

### Web

The browser experience is maintained separately in **[QwQdoge/meo-ai-web](https://github.com/QwQdoge/meo-ai-web)**. `meo-ai` remains the product source of truth for the service contract, web integration boundary, cloud/device protocol and Meo-specific web policy.

## What Meo AI owns

| Area | Responsibility |
| --- | --- |
| `meo/` | Meo-owned native assistant implementation |
| `meo/service/` | Stable headless AgentService layer |
| `meo/system/` | Unprivileged System AI Router client/tool layer |
| `meo/adapters/` | Temporary compatibility adapters around the inherited engine |
| `meo/web/` | Browser integration contract and Meo web policy |
| `meo/cloud/` | Conversation, device and AgentRun contracts |
| `meo/device/` | Authenticated bridge from remote work to local AgentService |

Shared visual controls and design tokens belong to **MeoUI**. Account/session identity and encrypted BYOK credentials belong to **Meo Account**. Privileged desktop execution remains behind the typed **System AI Router** rather than inside the assistant.

## Product principles

- **One assistant, multiple surfaces.** Desktop and web should expose the same mental model instead of becoming separate products.
- **Useful before configurable.** Good defaults, clear empty/loading/error states and progressive disclosure come before more settings.
- **Streaming is a real state.** Stop, cancellation, reconnect and restored-session behavior are part of the product contract.
- **User control is visible.** The UI should make model/provider, network use, tool approval and data boundaries understandable.
- **System actions stay typed and reviewable.** Prompts, Skills and MCP descriptions never replace permission or policy enforcement.
- **MeoUI is the visual source of truth.** Applications consume shared tokens and controls instead of inventing local copies.

## Current architecture

```text
Desktop (C++/QML + MeoUI) ─┐
                           ├─> AgentService ─> providers / tools / memory
Web (meo-ai-web) ──────────┘        │
                                    ├─> Meo Account (identity + encrypted BYOK)
                                    └─> System AI Router (typed system capabilities)
```

The maintained architecture and migration details are in:

- [Ownership and migration boundary](docs/ownership.md)
- [Native architecture](meo/docs/architecture.md)
- [AgentService contract](meo/docs/agent-service-contract.md)
- [SystemTool contract](meo/docs/system-tool-contract.md)
- [Web upstream policy](meo/docs/upstream-policy.md)

## Status

Meo AI is not presented as a finished release yet. The native frontend, AgentService transport, cancellation/reconnect semantics and System AI Router client are actively being migrated and validated. A successful mock, build or headless self-check is not the same as real-provider or live Plasma acceptance.

## Upstream and license

This repository is derived from **[qwersyk/Newelle](https://github.com/qwersyk/Newelle)** and preserves its provenance and GPL-3.0 licensing. The inherited root Newelle tree is intentionally retained while the Meo-native service/frontend reaches the documented split gates.

Do not remove the compatibility layer merely to make the repository look cleaner; new Meo product work belongs under the boundaries documented in [`AGENTS.md`](AGENTS.md) and [`docs/ownership.md`](docs/ownership.md).
