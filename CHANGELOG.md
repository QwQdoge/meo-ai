# Changelog

All notable Meo AI product changes are recorded here.

The project is still in active development. Until the first tagged Meo AI release, current work stays under **Unreleased** rather than pretending development snapshots are stable releases.

## Unreleased

### Added

- Native MeoUI chat surface with responsive navigation, conversation details, presentation cards, model-role controls, memory and resource management.
- Local AgentService transport with streaming responses, tool decisions, cancellation, reconnect and stale-conversation recovery.
- Structured request-failure state with an actionable MeoUI error banner and safe retry for text-only requests.
- Account-backed provider connection UI that keeps provider credential authority in Meo Account/KWallet.
- Usage and activity surfaces for model and token visibility.
- Product experience contract in `docs/product-experience.md`.

### Changed

- Root project documentation now presents Meo AI first while preserving Newelle provenance and GPL-3.0 licensing.
- Native settings make active runtime capabilities and compatibility limits explicit instead of presenting preference-only controls as complete features.

### Safety and reliability

- Privileged system actions remain outside Meo AI and go through the System AI Router policy/permission boundary.
- Native service endpoints are restricted to loopback HTTP origins.
- Requests carrying conversation-scoped resources are not silently retried as text-only requests.
- Request failure, ordinary status text, and metadata refresh state are separate UI contracts.

## Release process

When a Meo AI version is tagged, move the relevant entries out of **Unreleased** into a dated version section and link the corresponding GitHub release. Use semantic versioning for product releases.