# Meo AI presentation blocks and model roles

Status: first repo-side contract. The native UI and AgentService expose these concepts, while true multi-model execution remains gated on the UI-free AgentCore/provider-broker work.

## Native presentation blocks

Meo AI may return normal assistant text plus zero or more small native cards. The model does not generate QML, HTML, JavaScript, commands, URLs, or arbitrary action payloads. It emits bounded structured data and the installed native client chooses a registered MeoUI component.

Current backend compatibility event:

```json
{
  "type": "presentation_card",
  "card": {
    "card_id": "build:preview",
    "kind": "status",
    "title": "Meo AI build",
    "subtitle": "Native preview",
    "value": "Passing",
    "detail": "Protocol and native checks completed."
  }
}
```

AgentService normalizes that to a `presentation.card` request event. The accepted card kinds are currently `info`, `status`, `metric`, `file`, and `system`. Text fields are length bounded. Unknown executable fields are discarded rather than forwarded to QML.

The native client keeps a small bounded set of cards and renders them with MeoUI next to the conversation. More card types can be registered later, but each type must have a typed schema and a native implementation.

The Newelle compatibility backend also registers `meo_present_card`, a data-only tool that lets the model request one or several of these native cards. The tool returns only a small acknowledgement to the model. Its private compatibility encoding is consumed before AgentService, revalidated at the service boundary, and is not a frontend protocol.

Presentation is never authority. A card saying that Bluetooth is enabled does not grant permission to change Bluetooth, and a card saying that an operation is safe does not approve it. Real actions continue through typed tools, Router policy, owner APIs, confirmation, and verification.

## Model roles

A Meo AI account/profile can connect several provider models, then assign models to workloads rather than forcing one model to do everything.

The first role vocabulary is:

| Role | Intended work | Typical model shape |
|---|---|---|
| `title` | chat titles, short labels, tiny background summaries | cheapest small model |
| `judge` | yes/no classification, ranking, routing, structured selection | cheap reliable structured-output model |
| `reasoning` | planning, difficult reasoning, answer composition | strongest main reasoning model |
| `execution` | bounded agent steps, code edits, tool-oriented implementation | tool-capable model with good cost/latency |

A future runtime may use a flow such as:

```text
User request
   |
   v
Reasoning model -----> answer planning
   |
   +---- Judge model -----> classify / rank / choose route
   |
   +---- Execution model -> typed tools / implementation loop

Background:
Title model -> conversation title / labels
```

The Judge role is not a security judge. It may answer questions such as "is this request code-related?" or select between candidate plans. It must never authorize privileged operations, bypass confirmation, grant a capability, or replace deterministic policy.

Likewise, assigning a powerful Execution model does not grant that model more OS authority. Tool authority remains outside the model and behind the typed System AI Router / owning subsystem APIs.

## Current implementation boundary

AgentService now owns a non-secret `ModelRoleRegistry` and exposes:

- `GET /v1/model-roles`
- `POST /v1/model-roles/{roleId}` with `{"model_id":"provider:model"}` or `null`

Preferences persist in the user's config directory. The registry validates a selected model against the backend's structured model catalog. Provider credentials are not stored in this file and never cross the native frontend contract.

The native MeoUI client has a Model roles surface that lets the user choose a model for Title, Judge, Reasoning, and Execution. It explicitly marks the current selections as saved preferences rather than pretending role-specific execution is already active.

The current Newelle compatibility backend still selects one model at profile scope. Therefore every role reports `runtime_supported=false` and `routing_status=preference_only`. True model-role execution should be activated only after AgentCore exposes a UI-free per-call model invocation seam (or equivalent provider broker contract) that can select a model without mutating the global Newelle profile model for concurrent work.

## Account/provider ownership

Long-term credentials and provider connections belong behind the Account provider broker, not inside QML or prompts. The frontend should receive only non-secret records such as provider label, model id, model capabilities, availability, pricing hints, and current role assignment.

Meo Account already has the right primitives, so Meo AI should integrate them rather than create a second API-key database:

- the account service can store multiple provider credentials and exposes only non-secret credential metadata to its account UI;
- the desktop `meo-accountd` broker stores device AI credentials in KWallet and never returns saved keys to clients;
- approved clients can use `ListAvailableLocalAiConnections(clientId)` to receive enabled, non-secret connection metadata;
- approved clients can request model discovery/inference through `StartLocalAiOperation(clientId, action, arguments)` while the Account broker remains the credential-bearing network caller;
- Account's client-manifest capability boundary is kept separate from AI model roles and from OS tool permissions.

That means the intended integration path is not `QML -> API key`. It is:

```text
Meo Account / meo-accountd
  -> credentials, provider connections, device model catalog authority

AgentService
  -> non-secret model catalog, role preferences, routing policy, request lifecycle

AgentCore / provider broker adapter
  -> actual per-call inference using an approved provider connection

Native QML
  -> model-role selection and presentation only
```

The Meo Account broker already distinguishes ordinary provider metadata from privileged credential access. Meo AI must preserve that split when it gains the `local_ai` client capability. Installing/authorizing that manifest and enabling automatic inference is a packaging/security decision; it must not be silently synthesized by Meo AI itself.

For cloud-backed account connections, the account-side AI provider broker also already supports OpenAI, Gemini, DeepSeek, OpenRouter, and OpenAI-compatible profiles. Meo AI should consume a deliberately exposed non-secret catalog/inference seam from Account rather than fetch or duplicate those encrypted credentials.

This keeps API keys out of the UI and lets the same role configuration survive provider changes without weakening tool/security boundaries.

## Next gates

1. Keep presentation cards data-only and add typed card schemas as real use cases appear.
2. Add provider/model capability metadata needed for routing, such as tools, vision, context, structured output, cost class, and local/cloud status.
3. Add a Meo Account catalog adapter that consumes only approved non-secret connection/model metadata; do not add an independent key store to Meo AI.
4. Extract a per-call model invocation seam from the compatibility backend.
5. Activate `title` and `judge` first because they are isolated auxiliary calls and easiest to test for cost savings.
6. Activate `reasoning` and `execution` only with request-local model state, cancellation, accounting, and concurrency tests.
7. Sync role preferences to Account only after a stable account-owned preference schema exists; local role configuration remains the safe fallback until then.
8. Keep Router policy and human confirmation independent of all model-role choices.
