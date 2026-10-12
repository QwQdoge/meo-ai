# Meo AI product experience contract

This document defines the user-visible quality bar shared by the Meo AI desktop, web and account-connected experience. It is intentionally product-facing: security authority and implementation ownership remain in their existing repositories and contracts.

## First impression

A user should understand the product before reading architecture documentation.

- Repository and product entry points state what Meo AI is, who it is for and what is currently usable.
- Product surfaces use Meo naming and semantic visual roles consistently while preserving upstream attribution where applicable.
- Web deployments provide a Meo title, description, favicon/app icon, social preview metadata and a useful not-found experience.
- Installation/start instructions distinguish a development preview from a supported release.

## Shared visual language

MeoUI owns the reusable Meo control and token contract. Other surfaces map to the same semantic roles rather than copying literal QML values into feature code.

Required roles include:

- surfaces and elevation;
- primary/on-primary and secondary emphasis;
- text hierarchy and disabled state;
- spacing based on a small 4/8-derived scale;
- shared shape/radius intent;
- typography hierarchy and CJK fallback;
- motion intent, including reduced-motion behavior.

Applications should prefer shared primitives. A reusable visual need that cannot be expressed by the current system is a design-system gap, not permission to create a second local component language.

## Appearance and accessibility

- Follow the system appearance by default and support an explicit user override where the platform supports it.
- Maintain readable contrast, targeting WCAG AA for normal body text.
- All primary workflows must be keyboard operable.
- Keyboard focus must remain visible.
- Icon-only controls need accessible names.
- State must not be communicated by color alone.
- Respect reduced-motion preferences; nonessential transitions should remain short and unobtrusive.
- Responsive web layouts must be checked at phone, tablet and desktop widths.

## Conversation states

AI products are mostly state transitions, so empty/waiting/failure behavior is part of the primary experience.

### Empty

The first conversation surface should explain what can be done and provide a small number of useful example actions or prompts. Avoid a blank page that requires the user to already understand the product.

### Submitting and streaming

- Show that a request has been accepted without blocking the whole interface.
- Stream assistant output when the transport supports it.
- Expose Stop while work is active.
- Stop must map to real cancellation semantics when available rather than merely hiding output or closing a stream.
- Tool approval and long-running work should expose their current state without making the user inspect logs.

### Loading

Prefer layout-preserving skeletons/placeholders for content that has a predictable shape. Do not delay the entire shell while secondary data is loading; render navigation and stable chrome first when safe.

### Error and offline

User-visible failures must answer three questions:

1. What failed at a useful level?
2. Is user data/work still safe?
3. What can the user do next?

Use stable error categories and actionable retry/reconnect affordances. Raw exceptions, provider secrets, request payloads and internal stack traces are not user-facing error copy.

## Interaction cost

Common actions should normally be reachable within two interactions.

Web and desktop surfaces should converge on equivalent shortcuts where platform conventions allow it, including:

- send message;
- new conversation;
- conversation search;
- model/provider switch;
- command/action search (Ctrl/Cmd+K where appropriate).

Draft input should survive accidental navigation or reload where doing so does not create a privacy or multi-account leak.

Settings should separate common choices from advanced/provider/developer controls. A new user should not need to configure the product before the basic chat flow works.

## User control and trust

The product should make these boundaries understandable from the UI:

- which model/provider is active;
- whether a request may use the network;
- when a tool or system capability needs approval;
- which data is local, synced or uploaded;
- how to export or delete user-owned conversation data where supported.

Prefer reversible actions with a useful Undo path when practical. Irreversible or security-sensitive actions require an explicit confirmation appropriate to their impact.

Meo-specific product analytics must not silently become a prerequisite for core use. Any diagnostics/telemetry added by Meo should have a documented purpose, collection boundary and user-facing control appropriate to the data involved.

Provide a network/data explanation surface for production builds that documents major service categories and why the product contacts them.

## Account boundary

Meo Account owns authentication/session identity and encrypted BYOK credentials. Meo AI surfaces consume that authority; they do not create a second provider-key store.

Where local operation or user-supplied API credentials are supported, the product should not force account creation merely to access an otherwise local capability unless a concrete service dependency requires it.

## Reliability and performance

Critical user journeys should cover empty, loading, success, failure, cancellation, retry/reconnect and restored-session behavior.

Priorities:

- bounded request timeouts and retries appropriate to the operation;
- clear offline/reconnect behavior;
- lazy loading for heavy secondary features;
- virtualized or otherwise bounded rendering for very long conversations;
- visible shell/UI before slow secondary queries where authorization and data correctness permit it;
- end-to-end coverage for startup/auth, first conversation, streaming/cancel, history restore and destructive data actions.

Performance fixes must not weaken identity, authorization, permission or confirmation boundaries.

## Release maturity

A user-facing release should have:

- semantic version/release identifier;
- human-readable change notes;
- reproducible CI build/test gates;
- quick start documentation;
- a small FAQ/troubleshooting entry point;
- contribution instructions for public repositories;
- an in-product feedback/report-issue path that includes useful non-secret version/platform diagnostics.

## Implementation order

When several gaps exist at once, use this order unless a correctness/security issue is more urgent:

1. product entry point, naming and brand alignment;
2. shared tokens/primitives and obvious visual inconsistency;
3. empty/loading/error/offline/streaming states;
4. shortcuts, draft preservation and common-action cost;
5. export/delete/undo and visible data/network/model boundaries;
6. accessibility and privacy explanation surfaces;
7. performance and end-to-end acceptance;
8. observation of real user friction followed by targeted iteration.

This order is a product prioritization guide, not permission to bypass repository-specific contribution, security or validation rules.
