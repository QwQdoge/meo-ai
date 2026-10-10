# Meo AI runtime observability, controls and sync

Status: product/runtime contract for exposing useful AI execution data without turning the main chat surface into a dashboard.

## Principle

Meo AI should preserve useful information returned by the model/provider/runtime instead of discarding it. The default conversation stays quiet; detailed telemetry is progressively disclosed through a response details surface, activity timeline, settings and diagnostics.

The system must distinguish:

- answer content;
- provider/runtime metadata;
- observable tool activity;
- user-configurable model controls;
- memory/search/retrieval activity;
- durable conversation/resources;
- cloud synchronization state.

Unknown future provider fields should remain inspectable through a bounded, secret-filtered raw metadata view. Credential-bearing headers, cookies, API keys and tokens are never shown or synchronized as response metadata.

## Response details

When available, each completed assistant response should be able to show:

### Identity

- provider
- model
- provider response/request ID
- finish reason
- service tier
- system fingerprint/version when the API returns one

### Token usage

- input/prompt tokens
- output/completion tokens
- total tokens
- reasoning tokens
- cache read tokens
- cache write/creation tokens
- audio/image/specialized token counters when returned
- the raw provider usage object for future counters not yet normalized

### Context

- model context-window size when known
- context used
- context remaining
- maximum output tokens
- context percentage used
- number/tokens of trimmed messages
- context-management strategy/status

Context numbers must be labelled as provider/runtime values or estimates. Meo AI must not present an invented exact context count when the provider cannot supply one.

### Timing

- total request runtime
- time to first token
- time to first visible token
- queue time when supplied
- network/provider time when measurable
- tool time and reasoning time when the runtime can measure them separately
- request start/completion timestamps when available

### Cost and limits

When returned or reliably calculated from an account-owned pricing table:

- input/output/total cost
- currency
- rate-limit remaining/reset information
- provider quota/credit information

If the provider does not supply a value and Meo AI cannot calculate it reliably, the field stays absent rather than guessed.

### Activity

A response may report structured activity including:

- memory used / memory item count
- web/search queries and result count
- retrieval/RAG activity
- tools used
- MCP servers/tools used
- files/resources used
- vision/image input
- code/terminal activity
- sync activity relevant to the response

The compact message footer can summarize this (for example `1.4 s · 2.1k tokens · Search · 34% context`). Full details open on demand.

### Citations and sources

Citations are durable response blocks, not only markdown links. Where a provider/search tool returns source metadata, Meo AI keeps source title, URI/provider identity and relevant safe metadata so the user can inspect how the answer was grounded.

## Provider-returned reasoning

Meo AI may display a reasoning field or reasoning summary only when the external provider/runtime explicitly returns that material to the client.

It must not reconstruct, infer or fabricate hidden chain-of-thought from normal answer text. A UI label should make the distinction clear, for example `Provider reasoning` or `Reasoning summary`.

Encrypted/opaque reasoning payloads may be retained in the safe raw metadata view if useful for round-tripping, but are not presented as readable reasoning.

## Model controls

The product should support a typed control surface rather than provider-specific free-form JSON in the normal UI.

Potential controls include, where the selected provider/model actually supports them:

- current model
- temperature
- top-p
- maximum output tokens
- reasoning effort/budget
- verbosity/detail
- tool use: auto / ask / off
- web search: auto / on / off
- memory: auto / on / off
- citation/search grounding mode
- response format / structured output
- context strategy
- prompt caching preference where the provider exposes it
- parallel tool calls
- image/vision quality or detail
- seed / deterministic mode where supported

Each control must expose `supported`, `effective value`, `scope` and provenance. Unsupported controls disappear or are disabled; Meo AI must not pretend a saved preference was applied to a provider that ignored it.

Advanced provider-specific controls can live under `Provider options` and should remain bounded JSON-safe values.

## Memory

Memory is a first-class data product, separate from chat history and workspace files.

The native product should eventually support:

- list/search memory items
- source/provenance
- created/updated time
- global/account/workspace/conversation scope
- enable/disable automatic recall
- pin/protect important memory
- edit when the memory backend supports editing
- delete/forget
- temporary chat that does not write long-term memory
- per-request indication that memory was consulted
- sync status for each memory item if cloud sync is enabled

The model never becomes the authority for memory deletion. Deletion must go through the owning memory store and return a verified result.

## Search and research

Search should expose more than final prose.

Useful observable data includes:

- query/query rewrites
- provider/engine
- source list
- citation mapping
- retrieval time
- filters/time range/language when used
- result count when available
- whether the answer used web search, local search, workspace retrieval or MCP search

Search activity belongs in the execution timeline and sources/citations belong in the completed response.

## Tool, MCP and Skill controls

The user should be able to inspect and control the complete effective tool chain:

- built-in Meo tools
- typed System AI Router capabilities
- Skills
- MCP servers/tools/resources/prompts
- extensions
- workspace tools

For each capability, show provenance, health, read/write/state-changing classification, network/file scope and confirmation policy where known.

Useful controls include:

- enable/disable
- ask every time / allow while workspace active / deny
- network on/off where enforceable
- workspace root/path scope
- timeout/resource limits
- output/log detail
- MCP connect/disconnect
- Skill configured state vs runtime override

Enabling a Skill or MCP server never grants OS authority by itself.

## Cloud sync

Meo AI remains local-first, but a signed-in Meo Account may synchronize durable product state across the user's devices.

For a personal/self-hosted setup, `Sync everything` can be an easy default, but the architecture still keeps data categories explicit so secrets are excluded and future multi-user use remains safe.

Synchronizable categories may include:

- conversations and titles
- durable typed conversation blocks
- attachments and generated artifacts, subject to size policy
- workspaces/project metadata and project instructions
- model/provider preferences (never raw provider secrets through the conversation sync path)
- advanced model-role preferences
- memory items
- Skills enabled state and user-created Skills
- MCP configuration metadata; credentials remain in the credential broker/secret store
- tool permission preferences that are safe to roam
- UI/settings preferences
- usage history/telemetry if the user enables it

### Sync requirements

- account/device identity
- encrypted transport
- encryption at rest on the sync service
- explicit object version/revision
- conflict handling rather than blind last-writer overwrite for user-authored content
- deletion/tombstone propagation
- per-object/category sync status
- offline queue and retry
- no credential/API-key export in normal sync payloads
- ability to disable cloud sync and continue entirely locally
- diagnostics for pending/failed sync

Large artifacts can use content-addressed/deduplicated storage later. The first sync contract should prioritize correctness and recoverability over bandwidth optimization.

## Common AI-product capabilities to account for

The product specification should leave room for the common workflows users now expect from mature AI applications:

- edit/retry/regenerate a turn
- branch from a message
- copy message / copy code
- conversation search
- projects/workspaces
- files/images and long paste
- citations/research
- artifacts/preview panes
- memory
- voice/live input where supported
- image generation/editing
- scheduled/background tasks
- notifications
- temporary/private chat
- export/share where appropriate
- model/provider switching
- usage/cost/context inspection
- tool/MCP/Skill management
- task/activity timeline
- stop/cancel/retry failed steps
- provider diagnostics and raw safe metadata

These do not all belong in permanent chrome. The conversation remains the default surface and advanced capability appears when relevant.

## Branding indirection

AI branding must not be hard-coded throughout the QML layout.

`app/qml/AiLogo.qml` is the stable `meo.aiLogo` presentation boundary. Current branding can continue to render the existing Meo AI mark, while a later logo, animated mark, account-selected asset or rebrand can replace that one component without editing the chat/sidebar layout.

Older `MeoAiMark` call sites are routed through a compatibility shim so the implementation can migrate gradually.

## Current implementation status

Already present on the current feature branch:

- safe `response.meta` normalization;
- normalized token usage with common provider aliases;
- bounded secret-filtered raw provider metadata retention;
- timing/context/activity/citation fields;
- provider-returned reasoning-only rule;
- response cost/rate-limit/control slots;
- legacy Newelle adapter emits response metadata when stored provider data is available;
- AgentService event journal preserves response metadata ordering with the answer/tool stream;
- typed conversation content blocks;
- scoped conversation resource store for text/file/image inputs;
- stable AI-logo component boundary.

Still required before this is a finished native product surface:

- attach response metadata to the correct durable assistant turn;
- native response-details UI;
- provider/model capability and control discovery;
- native memory/search management surfaces;
- account-backed cloud sync implementation;
- durable persistence of tool activity/citations/telemetry where product policy says they should survive restart.
