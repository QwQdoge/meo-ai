# Meo AI Web

The Meo-owned React/TypeScript application now lives at [`client/`](client/README.md)
in this product repository, alongside C++/QML desktop, Kotlin/Compose Android,
[`../core-rs/`](../core-rs/) and [`../ui-schema/`](../ui-schema/README.md).
There is no new project/repository to coordinate for the three UI implementations.
See [`../workspace.json`](../workspace.json) for the source map.

The import contains the existing Meo product components, English product
translations, OAuth/session Functions, thin Meo API proxy and their relevant
transport tests. `client/import-manifest.json` records source paths, hashes and
upstream revision; `client/LICENSE.librechat` retains the MIT attribution.
It does not import the LibreChat Express/Mongo backend, static rollback client,
node_modules, build output or credentials.

`QwQdoge/meo-ai-web` remains deployment/rollback history until an explicit cutover.
New Meo Web product development belongs here. Repository consolidation does not
claim that production has switched source, that the complete settings candidate
is promoted, or that every workspace has achieved parity.

Browser production traffic enters Meo API through the same-origin HttpOnly OAuth
edge. Account remains the authority for identity, encrypted BYOK and security.
The browser never talks to a local privileged AgentService or holds raw provider
keys. A loopback Rust service is used only by the isolated local settings preview;
it is not an authenticated cloud API or a production Web fallback.

Rust Core owns shared runtime/business semantics. Meo API remains in its own
repository and owns the production authentication/persistence boundary. Its
existing Worker is TypeScript; preserving it while moving new AI domain behavior
to Rust is deliberate. No Rust cloud rewrite, deployment or data migration is
implied by this import.
