# Shared settings and memory contract

The Rust implementation is `core-rs/src/settings.rs` and `core-rs/src/memory.rs`.
The UI section/field catalog is `ui-schema/settings.json`. It is presentation
metadata, not permission policy. A test ensures every preference binding matches
the actual serialized Rust model.

## Ownership and current scope

The implemented transport is the **loopback Core service**, scoped to the local
user/device process. It is not a multi-tenant cloud endpoint. The public Meo API
remains a separate authenticated service; it must adopt actor-scoped storage and
this domain contract before account-wide sync can be offered. Production Web
uses only Meo API/Account and must not fall back to the loopback service.

C++/QML desktop, React and Kotlin/Compose remain native presentation adapters.
The user approved the eight settings groups and restrained Pixel candidate on
2026-10-18. The maintained client source now adopts that structure. The deployed
web service and installed packages have not been switched by this integration.

## Routes

| Method | Core route | Behavior |
| --- | --- | --- |
| GET | `/v1/ai/settings/catalog` | Shared declarative section/field catalog |
| GET | `/v1/ai/settings` | `{scope: "device", settings: SettingsDocument}` |
| PATCH | `/v1/ai/settings` | Revision-checked partial preferences update |
| GET | `/v1/ai/memory` | Separate memory document, including recoverable archives |
| POST | `/v1/ai/memory` | Add a user-supplied memory |
| PUT | `/v1/ai/memory/:id` | Edit, archive or restore an existing memory |
| GET | `/v1/models` | IDs actually registered in this runtime |

Settings updates contain `expected_revision` and `patch`. Omitted fields remain
unchanged; unknown fields, null/mistyped values, unsupported enum values and
empty patches fail. A stale revision returns 409 rather than overwriting another
save. Success returns the committed document and incremented revision.

Current preferences: Enter-to-send, theme, reduced motion, personal instructions,
response language, and whether to use explicitly saved memories. Enter/theme/
motion are renderer behaviors; Core stores the values, and each renderer must
consume them before claiming that setting works on that platform.

Personal instructions and response language enter new Rust model requests.
When memory use is enabled, active user memories are ranked/budgeted by the
existing Context Engine. Only selected memories enter model context, with stable
`memory:<id>` references. Archived memories never enter context. Diagnostics
contain aggregate context statistics, not instructions or memory text.

Memory writes require a revision, text (1–4000 Unicode characters), `pinned` and
`archived`. New entries receive Core-owned UUIDs. The current device store allows
up to 1000 entries including archives. There is no destructive purge endpoint or
automatic memory extraction. Archiving preserves the entry for restoration;
disabling memory recall preserves all saved content.

## Persistence

By default, embedded service instances use in-memory stores. Set
`MEO_AI_SETTINGS_FILE` and `MEO_AI_MEMORY_FILE` to explicit per-user storage paths
for persistence. This avoids an implicit write to production/user configuration
when starting tests or a candidate preview. Neither request bodies nor UI Schema
choose filesystem paths or actor IDs.

Writes use a newly created sibling temporary file, flush it and rename it before
updating memory. On Unix, created files use mode 0600. Corrupt/unsupported files
fail rather than silently resetting user preferences. The current file stores
are single-process device stores; multi-process/cloud synchronization requires
a transactional actor-scoped persistence adapter, not shared JSON files.

Account security, OAuth, passwords, provider keys, billing, authorization grants
and tool approvals are not writable preferences. Those remain with Account/API
and the owning capability authorities. UI metadata never overrides them.

## Client adoption

| Surface | Implemented behavior | Remaining boundary |
| --- | --- | --- |
| React Web | Eight groups from schema; browser-persistent theme/motion/Enter behavior; settings API adapter with optimistic revision; existing Account connection metadata and security/data links | Public actor-scoped preferences/memory service is not implemented by the loopback Core; unavailable responses stay visible |
| C++/QML | Generated shared catalog/navigation; device-persistent theme/motion/Enter behavior; existing provider/model-role/runtime/MCP/memory/activity operations retained within groups | Existing compatibility runtime and Rust memory stores are not merged; shared personal instructions need runtime adoption |
| Kotlin/Compose | Generated catalog/navigation; device preferences bound to theme/keyboard/scroll/motion; existing provider metadata and Account actions | Android SDK/Gradle absent on the local host; assembly/device checks and account preferences/memory adapter remain outstanding |

Browser device preferences contain only interaction/appearance fields. They do
not contain personal instructions, memories, credentials or grants. The public
Web API adapter accepts `scope: account` for shared preferences/memory and never
silently uses a `scope: device` response. The thin Pages edge forwards only the
specified GET/PATCH/POST/PUT routes to Meo API with existing authentication and
preserves unavailable/conflict errors. It owns no settings or memory store.

Switching from Web Chat to Settings keeps Chat mounted, preserving its draft and
in-flight stream state. This is presentation continuity, not durable background
AgentRun execution. Android drafts use saved Compose state while changing pages;
real process death, stream reconnect and cross-device continuation require their
separate acceptance tests.
