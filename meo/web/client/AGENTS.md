# Consolidated Meo Web

The `meo-ai` root guidance applies. This is the Meo product React client, not the
LibreChat server. New product changes belong here; old `meo-ai-web` is retained
for deployment rollback and provenance.

Read the shared `../../ui-schema/` contract and the corresponding native surface
before changing product navigation or settings. Render Core/API state; never
copy provider orchestration, memory selection, approval policy or agent loops
into React or the Pages edge.

Keep settings field definitions in UI Schema. Keep visible product copy in the
localization system. Preserve keyboard/IME, focus, reduced motion, theme and
compact navigation. New visual candidates follow the workspace preview rule.

Run `npm run typecheck`, focused `npm test`, and the output-root-directed build.
OAuth/browser session tests are offline fixtures; do not report them as real
login, model generation, cloud sync or desktop/Android acceptance. Keep tokens,
provider keys and user content out of logs, source and screenshots.
