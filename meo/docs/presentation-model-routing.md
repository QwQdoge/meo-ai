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

The current Newelle compatibility backend still selects one model at profile scope. Therefore every role reports `runtime_supported=false` and `routing_status=preference_only`. The UI deliberately says the preference is saved but not yet active as independent runtime routing.

True model-role execution should be activated only after AgentCore exposes a UI-free per-call model invocation seam (or equivalent provider broker contract) that can select a model without mutating the global Newelle profile model for concurrent work.

## Account/provider ownership

Long-term credentials and provider connections belong behind the Account provider broker, not inside QML or prompts. The frontend should receive only non-secret records such as provider label, model id, model capabilities, availability, pricing hints, and current role assignment.

The desired ownership split is:

```text
Meo Account / provider broker
  -> credentials and provider connections

AgentService
  -> model catalog, role preferences, routing policy, request lifecycle

AgentCore
  -> actual per-call inference and tool loop

Native QML
  -> model-role selection and presentation only
```

This keeps API keys out of the UI and lets the same role configuration survive provider changes without weakening tool/security boundaries.

## Next gates

1. Keep presentation cards data-only and add typed card schemas as real use cases appear.
2. Add provider/model capability metadata needed for routing, such as tools, vision, context, structured output, cost class, and local/cloud status.
3. Extract a per-call model invocation seam from the compatibility backend.
4. Activate `title` and `judge` first because they are isolated auxiliary calls and easiest to test for cost savings.
5. Activate `reasoning` and `execution` only with request-local model state, cancellation, accounting, and concurrency tests.
6. Integrate the Account broker so adding/removing provider credentials updates the catalog without exposing secrets to QML.
7. Keep Router policy and human confirmation independent of all model-role choices.
