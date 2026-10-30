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

### Added (since 2026-10-15; summarised from the commit history)

- **Work mode:** tool loop with folder tools, a permission gate with approver, checkpoints saved on disk with a diff on the approval card, rewind, task lists planned and judged by level, sub-agents, context compaction and an enforced check; "Files changed" per-file diffs in the Details panel; a headless `meo-runner` for Work on your own computers; remote control between a user's devices.
- **Chat and Work share one conversation:** the server mode follows the conversation on every device, Work is suggested for big tasks, and an answer's steps and check score are stored with it so reloads and other devices show them.
- **Plugin store (Web, desktop QML, Android Compose):** MCP registry search and third-party import, Skills bundles (including 17 more open-source skills), an Essentials bundle, hosted MCP plugins the model can call in Chat and Work, and OAuth connectors (GitHub, Google and more) with a Connect button and connection status.
- **Models:** model profiles by requirement (main model, ranking, parallel probe, per-role editor, AI generation), retry once on another model when a provider route is saturated, and Settings > Usage from the account usage dashboard.
- **Files and attachments (Web):** paste, drag-and-drop and multi-select attachments; reading PDF, Word, Excel, PowerPoint and RTF; downloading model-written files (docx, xlsx, text) and images; browser file tools through the File System Access API.
- **Rich messages:** callouts, draft cards, tables, icons, nested step details and collapsible inspector sections on Web, desktop and Android.
- **Clients:** redesigned Web shell (drawer, app bar, tune sheet composer, device chip), dynamic color and capsule composers on desktop and Android, masked password input on every client.

### Fixed (since 2026-10-15)

- Token refresh race on startup; sign-in browser and notifications on macOS and Windows; packaging of the context engine, sub-agent scheduler and tool output modules.

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