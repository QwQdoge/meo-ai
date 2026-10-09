# Meo AI ownership and migration boundary

This repository is a migration repository: the Newelle-derived upstream tree remains present while the Meo-native frontend/service stack is developed under `meo/`. These two layers are not equal product authorities.

## Current Meo direction

- `meo/`: current Meo-owned implementation area.
- `meo/service/`: stable headless assistant/service layer.
- `meo/system/`: unprivileged System AI Router client/tool layer.
- `meo/adapters/`: temporary compatibility adapters around Newelle-era objects.
- native C++/QML frontend under `meo/`: current desktop UI direction.

New Meo product behavior should land under these boundaries unless it must patch a documented upstream integration seam.

## Newelle-derived compatibility layer

The root Newelle-derived tree (`src/`, `modules/`, Meson/Flatpak metadata, `po/`, legacy data/assets and related build files) is retained because the current Meo migration still depends on upstream engine/runtime functionality.

It is **compatibility/migration infrastructure**, not the long-term Meo frontend architecture.

Do not:

- add new Meo-specific UI directly into GTK/Adwaita surfaces when an equivalent Meo-native surface exists;
- duplicate System AI Router executors or privileged OS logic here;
- delete the upstream layer while Meo service/runtime still imports or depends on it;
- describe Newelle root UI as the target Meo desktop frontend.

## Split gate

Do not move the Newelle tree into a separate legacy repository yet. A split becomes appropriate only when all of the following are true:

1. the Meo-native frontend is the default runnable product;
2. headless Meo service/provider execution no longer requires GTK/Adwaita/WebKit UI objects;
3. compatibility adapters are narrow and can be packaged independently or removed;
4. packaging/CI can build Meo without treating the Newelle root as the primary application;
5. provider, memory, tool, skill/MCP and conversation capabilities needed by the supported Meo release contract have migrated or have explicit replacements.

At that point the preferred end state is:

```text
meo-ai            # Meo-native assistant/service/frontend
meo-ai-newelle-legacy (or archived upstream fork)  # provenance/migration only
```

## System AI Router boundary

`meo-ai` is a client of the OS-level System AI Router. The router/capability/policy/permission/verification authority belongs to `MeoArch-os-workspace` (with native executors in their owning system/app repositories). Meo AI may request typed capabilities; it must not recreate the privileged router inside this repository.

## Change rule

When touching root Newelle-derived code, document why a Meo-side adapter cannot own the change instead. Prefer migration seams over deeper coupling so the future split becomes easier rather than harder.
