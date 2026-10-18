# Meo Design & UI Schema v1

This directory is the single editable Meo AI **product UI configuration** for
React/TypeScript, desktop C++/Qt/QML + MeoUI, and Kotlin/Compose. It describes
navigation, page hierarchy/states, feature entry points and semantic token
bindings. It does not contain a renderer, agent engine or permission authority.

## Ownership

- `navigation.json`: stable destination IDs, translation keys, semantic icons,
  page references, placement and ordering.
- `pages.json`: known native renderer IDs, ordered section IDs and visible states.
- `features.json`: stable presentation capability requirements. A capability is
  discovered from the runtime/API; its presence here never grants permission or
  asserts that a feature is implemented.
- `tokens.json`: a restrained Pixel/Material semantic profile. MeoUI remains the
  authority for shared token values and controls; these are references, not a
  second set of hard-coded geometry or colors. Platform adapters map them to
  React theme roles and Compose equivalents, including system dynamic color.
- `settings.json`: ordered settings sections, field bindings, labels and control kinds. Field bindings are checked against the Rust preference contract in Core tests; declarations do not assert backend availability.
- `generate.mjs`: dependency-free build-time validation and generation.

ContentBlock is a separate **content protocol**, currently owned by
`../core-rs/src/blocks.rs`. Do not hand-maintain another ContentBlock union here.
A future `content-blocks.schema.json` must be exported from that authoritative
wire model with versioned compatibility fixtures before clients consume it.

## Build interface

```sh
node meo/ui-schema/generate.mjs --output /absolute/build/output/ui-schema
```

Use the workspace output root locally, or a runner temporary directory in CI.
The generator writes only its named files, does not clean the output directory,
and refuses to write into this source directory. Generated results include:

- TypeScript configuration with inferred navigation types;
- a C++17 header containing the same JSON for `QJsonDocument` consumption;
- a QML JavaScript library containing the same configuration;
- a Kotlin object containing the same JSON for native adapter consumption;
- a JSON bundle and SHA-256 manifest.

All outputs derive from the same validated data, ordered by `order` and then
stable ASCII ID. Pin a schema revision/hash when copying build artifacts between
repositories; never implicitly depend on a mutable branch head at runtime.
CI generates an artifact; publishing that artifact and adopting it in client
builds are separate integration steps.

## Native adapter contract

`primary` and `secondary` are logical regions. Desktop/Web render secondary
items near the bottom of the navigation area. Android uses the same two groups
in its navigation drawer, rather than inventing a mobile bottom tab bar. Moving
Work means changing only its `placement`; the adapter must retain its ID, page,
feature requirement and runtime state. Ordering is scoped to each group.

Labels use `labelKey` with the existing platform translation system. `label` is
an English fallback. Icons are semantic IDs resolved through each platform's
existing icon system; no downloadable SVG, code or arbitrary path is accepted.
Unknown schema versions, renderer IDs and placements fail the build. Missing
runtime capabilities show a truthful unavailable state with a reason; schema
configuration cannot bypass API permissions, approvals or account scopes.

Page sections/states define the shared intended contract, not completed pages.
New renderer/section types and transitions need native implementation on each
platform before being offered as available. Adapters do not infer execution
status from UI configuration.

Native CMake and Android Gradle schema generation require Node.js at build time
(no Node.js runtime is shipped with the native applications).

The maintained React source reads the navigation/settings JSON directly. CMake
validates and generates the QML library into its external build tree; native
sidebar and compact drawer adapters use its primary/secondary groups. Gradle
runs the same generator and compiles the Kotlin configuration for Compose.
The eight settings groups are shared; existing desktop runtime operations stay
inside those groups. Unsupported service functions are explicitly unavailable.

These are source integrations, not proof that all three deployed clients are in
parity. Web and desktop have local build validation; Android assembly/device
validation and cross-account settings synchronization remain outstanding. There
is no remote configuration loader in v1.

## Restrained Pixel direction

Prioritize readable information, clear grouping, predictable controls and useful
empty/error states. Use quiet semantic surfaces, one restrained accent, shared
spacing and shape tokens, concise motion and system reduced-motion preferences.
Avoid decorative cards, large empty hero sections, excessive pills, gradients
and competing accent colors. Preserve Meo branding. Platform typography and
dynamic color may differ while hierarchy, meaning and interaction stay aligned.

## Checked navigation adapters

The generator also maintains the existing public `GeneratedNavigation.js` and
`GeneratedNavigation.kt` bindings from the same schema. `--check` detects drift;
`--web-output <path>` writes/checks the retained Web navigation adapter. Shared
configuration and external build artifacts continue to use `--output <dir>`.
