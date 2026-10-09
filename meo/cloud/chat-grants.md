# Meo AI chat grants

The existing Meo Account provider broker intentionally uses payload-bound one-time consent for isolated inference and image-generation actions. That is too interruptive for an ordinary chat product, where a conversation may invoke the same approved provider dozens of times.

Meo AI therefore needs a reusable, revocable authorization layer for first-party chat clients. This is an authorization contract, not a credential store: provider API keys remain exclusively in Meo Account.

## Modes

- `ask_every_time`: retain the current prepare/approve/invoke flow. No reusable grant is created.
- `session`: approve one credential and a bounded set of data categories until a fixed expiry or logout.
- `persistent`: approve one credential and data-category set until explicitly revoked.

The default product choice should be `session`. Persistent access must be an explicit user choice.

## Grant binding

A reusable grant is bound to:

- the authenticated Meo user;
- the exact OAuth client ID (`meo-ai-web`, native Meo AI, etc.);
- one Account-owned credential ID;
- a declared set of data categories;
- issuance and optional expiry;
- revocation state.

A grant never contains or returns a provider API key.

The Account broker remains responsible for verifying the OAuth session/client identity, looking up the credential, decrypting the key only inside the broker, validating the requested model/provider destination and performing the outbound provider call.

## Data categories

Initial categories owned by the Meo AI contract:

- `chat_text`
- `system_instructions`
- `conversation_context`
- `attachment_text`
- `image_input`

A request whose categories are not a subset of the grant must fail closed. New categories require an explicit contract revision; free-form category names from a model are not authority.

## Revocation

Grant validity must be checked at each broker invocation. Sign-out, account/session revocation, credential deletion/disablement and explicit grant revocation all stop future inference. Already-sent provider requests are not rolled back.

## Migration path

1. Keep the deployed one-time consent flow unchanged.
2. Add Account-side storage/API for first-party chat grants in the Account repository and preview database.
3. Add broker support for invoking with a valid grant ID instead of a one-time consent envelope.
4. Integrate Meo AI Web and native Meo AI against the grant path.
5. Preserve `ask_every_time` as a user-selectable privacy mode.

`meo/cloud/contracts.py` defines the Meo-side contract and validation invariants. It is not a substitute for server-side Account authorization.
