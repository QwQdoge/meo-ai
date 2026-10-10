# Meo AI conversation content blocks

Status: first service-side contract for moving the native product away from plain-string chat. The current QML frontend still renders the existing string stream; this document and `meo/service/content_blocks.py` define the safe typed representation that later transcript, attachment, artifact and tool-activity work will consume.

## Why this exists

A complete Meo AI conversation must persist and restore more than plain text. Files, images, code, citations, tool activity, confirmations, native presentation cards, generated artifacts and recoverable errors all need stable identities and ordering.

The frontend must not infer these from markdown conventions or model-written prose. The model may propose presentation data, but AgentService normalizes it into a bounded known block type before QML sees it.

## Block vocabulary

The first vocabulary is:

- `text`: user-authored/plain text that must not be reinterpreted as markdown.
- `markdown`: assistant-formatted prose.
- `code`: code text with optional language and filename metadata.
- `image`: an image resource referenced by stable resource ID.
- `attachment`: a user/context file referenced by stable resource ID.
- `citation`: a source label/URI/detail presentation block.
- `tool_activity`: one observable tool/execution step.
- `confirmation`: a presentation block tied to a service-owned `decision_id`.
- `presentation`: compact native contextual UI such as status/metric/file/system cards.
- `artifact`: an agent-generated durable output resource.
- `error`: a visible product error with recoverability metadata.

This vocabulary can grow only by adding a typed schema and native renderer. There is intentionally no generic `custom`, `html`, `qml`, `javascript`, `command` or arbitrary action payload.

## Stable identity

Every block carries a `block_id`. Resource-backed blocks additionally carry `resource_id`; activity and confirmation blocks carry the IDs owned by their respective service contracts.

IDs are presentation/reconciliation identity, not authorization. A `decision_id` is only useful through the existing AgentService decision endpoint, which still checks request ownership and lifecycle. A presentation block never grants an OS capability.

## Resource references

Image, attachment and artifact blocks intentionally expose `resource_id` plus non-secret metadata such as name, MIME type and size. They do not expose an arbitrary local filesystem path.

A later resource store/attachment service owns the mapping:

```text
resource_id
  -> scoped resource record
  -> owning conversation/workspace
  -> approved read/write operation
  -> local backing object
```

This makes it possible to support one-shot attachments, conversation files, workspace files and generated artifacts without injecting `/home/...` paths directly into prompts or frontend history.

## Legacy compatibility

Inherited Newelle history currently yields only user/assistant text. The compatibility projection is:

- user text -> `text`
- assistant text -> `markdown`

This lets the new transcript model be introduced without pretending the old history already contains structured attachments or tool activity.

The compatibility projection does not parse markdown into executable blocks. Code fences can later be rendered as code by the native markdown renderer, while real generated files still require an artifact/file tool.

## Streaming

The current transport still emits `message.delta` string events. Migration should preserve that event until the native client accepts block-aware streaming.

The intended evolution is:

```text
request.started
message.block.started
message.block.delta
message.block.completed
tool.activity...
presentation.block...
request.completed
```

A migration must preserve sequence/reconnect semantics. It must not create a second event stream that can reorder tool effects relative to visible transcript blocks.

## Large paste and attachments

Long paste is a product-layer use of the same resource model:

1. Small clipboard text stays in the composer.
2. Large clipboard text is offered as a text attachment.
3. The attachment receives a `resource_id` and visible metadata.
4. Submission references that resource instead of placing an unbounded string in the request body.
5. The resource is persisted according to conversation/workspace policy.

File and image attachments use the same resource identity model. Image blocks additionally carry validated positive width/height metadata when known.

## Artifacts

Generated files are `artifact` blocks only after a typed artifact/file tool reports success. Model prose cannot create an artifact record by claiming a path or filename exists.

An artifact renderer may offer Open, Save As, Reveal, Preview or version/diff actions, but those actions are native UI commands bound to an existing resource record. They are not model-supplied action payloads.

## Tool activity

`tool_activity.state` has a closed vocabulary:

- `queued`
- `running`
- `awaiting_confirmation`
- `completed`
- `failed`
- `cancelled`

This is the basis for the compact execution timeline in the product UI. Tool activity detail remains presentation data; real authority and lifecycle stay in AgentService/Router/owner APIs.

## Security invariants

- No arbitrary QML/HTML/JavaScript execution from conversation blocks.
- No generic shell command/action field in the block contract.
- No local path exposure for attachment/artifact identity.
- Unknown block types are rejected.
- Text and metadata fields are length bounded.
- Arrays are count bounded.
- Tool/confirmation/resource identity does not replace owning-service authorization.
- Skills and MCP can contribute tools/results but cannot add new executable block semantics by description alone.

## Implementation order

1. Land and test the normalization contract.
2. Add block-aware presentation-safe conversation history while preserving legacy `text` compatibility.
3. Add native block model/renderers for text/markdown/code/error.
4. Add scoped resource service and attachment lifecycle.
5. Add file/image composer UX and model capability validation.
6. Persist presentation/tool/artifact blocks with conversations.
7. Add artifact pane and richer file types.
8. Surface MCP/Skill/tool provenance in tool activity without granting new authority.
