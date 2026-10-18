# Meo AI ownership and migration boundary

This repository is a migration repository: the Newelle-derived upstream tree and the first Python/C++ Meo-native stack remain present while the product moves to its final architecture. These layers are not equal product authorities.

## Final product architecture

The authoritative Meo AI product core is Rust under `meo/core-rs/`.

Rust owns:

- the cross-platform conversation/message/content-block protocol;
- provider clients and model routing;
- request lifecycle, cancellation, replay and streaming semantics;
- resources, attachments and artifact metadata contracts;
- tool/connector state and typed action IDs;
- conversation state, persistence/sync contracts and client transport;
- Account/session/broker and device protocol clients as they migrate;
- the local AgentService HTTP/SSE implementation and the reusable cloud service core.

Platform frontends own presentation only:

- Desktop (Linux, Windows and macOS): C++ + Qt/QML + MeoUI. C++ owns the application layer, platform integration and typed IPC/API adapters. The shared Core is accessed through a stable service boundary; replacing the desktop C++ layer with Rust bindings is not a migration objective. Conversation/provider/tool/sync/policy authority remains shared rather than duplicated in the client.
- Android: Kotlin + Jetpack Compose Material 3 Expressive, backed by the same Rust core through JNI/UniFFI-style bindings.
- Web: React/TypeScript presentation, consuming the same Rust-owned wire protocol and Rust service. Web UI code may adapt blocks to browser components but must not become a second AI engine.

The three frontends consume the same declarative UI configuration under `meo/ui-schema/` for navigation placement, ordering, page hierarchy/states, feature entry points and semantic token bindings. Platform renderers adapt layout to their native toolkit without inventing separate product configuration. A conversation, request, rich response block, tool decision and reconnect sequence must mean the same thing on every client. The initial schema/generator exists; renderer adoption is still required.

## Current Meo-owned areas

- `meo/core-rs/`: **authoritative product core and protocol**.
- `meo/android/`: native Android frontend. Product logic belongs in Rust, not Kotlin view models or duplicated network stacks.
- `meo/app/`: C++ desktop application and QML/MeoUI presentation; native integration remains C++.
- `meo/ui-schema/`: authoritative declarative product UI configuration and build-time generator; MeoUI retains ownership of reusable controls and token values.
- `meo/web/client/`: canonical React/TypeScript product UI and thin browser edge; imported with provenance from the old Web fork.
- `meo/web/`: browser integration contracts and shared transport adapter; business semantics remain in Core/API.
- `meo/cloud/`: deployment and compatibility contracts while cloud execution moves onto the Rust service core.
- `meo/device/`: compatibility implementation while authenticated device protocol/state moves to Rust.
- `meo/service/`, `meo/runtime/`, `meo/system/`, `meo/adapters/`: migration/compatibility code. Do not add new product architecture here when the behavior belongs in Rust.

## Migration rule for compatibility business logic

Python and C++ must not become independent copies of shared AI business logic. This does not restrict C++ desktop application/presentation/platform work, which remains the selected desktop technology.

Changes to duplicated legacy AI business behavior are limited to:

- preserving a working release while the equivalent Rust path is being enabled;
- compatibility adapters that translate an old contract into the Rust-owned contract;
- bug/security fixes that cannot safely wait for deletion;
- tests proving parity during migration.

Do not add a new provider, message type, tool state machine, sync feature, cache, router, resource format, reconnect rule or cross-device protocol only to Python/C++. Implement the Rust contract first and adapt the compatibility layer to it.

Deleting compatibility code is allowed only when packaging, desktop and integration tests no longer require it. The goal is deletion, not a permanently duplicated engine.

## Visual system ownership

MeoUI owns the desktop Material 3 / Material 3 Expressive design primitives, semantic tokens, adaptive geometry and motion. The selected product profile is restrained Pixel: information and function first, quiet surfaces, limited accents and subtle motion; avoid decorative card/pill proliferation. The Meo AI desktop must use those primitives rather than recreating Pixel-like values locally.

Android uses official Jetpack Compose Material 3 Expressive APIs and dynamic color where available. Web should map the same semantic surface/container/shape/type hierarchy into browser tokens rather than copying Android implementation details.

A visual feature is complete only when it has an equivalent semantic presentation across supported clients. Pixel/Material styling must never change the underlying Rust protocol shape.

## External authority boundaries

Moving product orchestration to Rust does not move unrelated security authorities into this repository.

- Meo Account remains authoritative for authentication/session identity and encrypted provider credentials.
- The Rust core may consume Account OAuth/provider-broker APIs but must not create a second credential authority or expose raw provider keys to frontends.
- The System AI Router and owning system/application components remain authoritative for privileged or desktop actions.
- Remote device infrastructure may relay exact AgentService/Router requests, but it must not bypass request, confirmation or verification semantics.

## Newelle-derived compatibility layer

The root Newelle-derived tree (`src/`, `modules/`, Meson/Flatpak metadata, `po/`, legacy data/assets and related build files) is retained only while migration still depends on its provider/runtime behavior.

It is compatibility infrastructure, not the target product architecture.

Do not:

- add new Meo-specific UI directly into GTK/Adwaita surfaces;
- add new cross-platform AI product logic to the Newelle tree;
- duplicate System AI Router executors or privileged OS logic here;
- delete the upstream layer before Rust replacements and packaging gates are complete;
- describe the Newelle root UI or Python compatibility AgentService as the final Meo AI architecture. The desktop application remains C++/Qt/QML; shared Core services remain a separate authority.

## Split/removal gates

The legacy layers can be moved out or deleted when all of the following are true:

1. Rust service/client protocol tests cover conversation, provider, resource, tool, cancellation and replay semantics;
2. the C++/QML desktop consumes the shared Core through a stable IPC/API contract and contains no duplicate AI business authority;
3. Android runs the same Rust protocol/core and native Compose renderer;
4. web/cloud consumes the Rust-owned protocol/service for supported Meo features;
5. packaging launches the Rust AgentService by default;
6. Meo Account, memory, provider, tool, skill/MCP/connector and device capabilities needed by the supported release have Rust implementations or explicit external authorities;
7. Newelle compatibility adapters are narrow enough to package separately or remove.

Preferred end state:

```text
meo-ai/
  meo/core-rs/       # authoritative core/service/client
  meo/app/qml/       # Linux native presentation
  meo/android/       # Android native presentation
  meo/web/           # web integration/presentation contract

meo-ai-newelle-legacy (optional archived compatibility repository)
```

## System AI Router boundary

`meo-ai` is a client of the OS-level System AI Router. The router/capability/policy/permission/verification authority belongs to `MeoArch-os-workspace` and owning system/app repositories. Rust may implement the typed client and state machine; it must not recreate privileged executors inside Meo AI.

## Change rule

For any new cross-platform capability, start from the Rust data/state contract, then render it in QML/MeoUI, Compose and web as applicable. A frontend-only implementation is not complete if it invents semantics that the Rust core does not own.