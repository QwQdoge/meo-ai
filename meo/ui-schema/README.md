# Meo UI Schema — native renderers, one navigation source

The canonical navigation configuration is [navigation.json](./navigation.json).
**Edit this JSON**, not the generated React, Qt Quick or Android lists.

The source intentionally describes only navigation metadata (stable IDs, order,
primary/secondary placement, title and each platform's icon identifier).
It does **not** attempt to serialize entire QML/Compose/React pages, tool
permissions or user account data. Those stay in native UI and secure APIs.

## Generate

Run from the **QwQdoge/meo-ai** checkout:

```sh
node meo/ui-schema/generate.mjs
node meo/ui-schema/generate.mjs --check
```

This regenerates:
- `meo/app/qml/GeneratedNavigation.js` used by the C++/Qt MeoUI sidebar.
- `meo/android/app/src/main/java/org/meo/ai/ui/GeneratedNavigation.kt`
  for the Android native navigation layer.

When the sibling `meo-ai-web` checkout is present, also regenerate its
vendored React artifact (adjust the relative path to your checkout layout):

```sh
node meo/ui-schema/generate.mjs --web-output ../meo-ai-web/client/src/components/Meo/uiNavigation.generated.ts
node meo/ui-schema/generate.mjs --check --web-output ../meo-ai-web/client/src/components/Meo/uiNavigation.generated.ts
```

The Web `Meo Pages` CI checks its artifact against the checked-out canonical
`meo-ai/main` schema; the native CI checks QML and Kotlin artifacts.
No cross-repository secret or write-capable CI token is required.
When this repository's schema changes, commit the three regenerated artifacts
to their respective main branches. CI **detects** drift but does not silently
push cross-repository commits. Automated synchronization requires a dedicated
minimal-scope bot credential or packaging the schema as a versioned dependency.

## Example: move Work to secondary navigation

Set the Work entry's `placement` from `primary` to `secondary`.
Run the generator above. Web and Qt sidebar layouts read the corresponding
generated lists; Android has generated metadata but currently exposes only
functional chat/account screens, not an unfinished Work destination.
Do not expose dead Android screens solely to claim UI parity.

The schema has a fixed ID vocabulary and validates duplicate IDs, placements,
labels, icon tokens and order. Add an actual route/component and its associated
tests before adding new navigation destinations.

## Rollout gates

1. All native and Web CI schema checks pass.
2. The current screen actually exists and works on the target platform.
3. Navigation and placement are manually checked at desktop and compact sizes.
4. The native React/Compose/QML screen is responsible for loading, errors,
   access control and functionality; never infer permission from visible nav.
5. Production API OAuth/Worker release is independent from navigation changes.
