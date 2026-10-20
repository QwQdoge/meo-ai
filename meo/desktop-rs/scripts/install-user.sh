#!/usr/bin/env bash
# Builds Meo AI (release) and registers a per-user launcher. Development install:
# it uses the local MeoUI build until a MeoUI package with the new components ships.
#   MEO_OUTPUT_ROOT  generated-output root (default ~/Projects/outputs)
#   MEO_UI_INSTALL   MeoUI install prefix (default $MEO_OUTPUT_ROOT/meo-ui/install/meoui-main)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${MEO_OUTPUT_ROOT:-$HOME/Projects/outputs}"
ui="${MEO_UI_INSTALL:-$out/meo-ui/install/meoui-main}"
target="$out/meo-ai/build/cargo-target"
[ -d "$ui/lib/qt6/qml" ] || { echo "MeoUI install not found at $ui (set MEO_UI_INSTALL)" >&2; exit 1; }

CARGO_TARGET_DIR="$target" cargo build --release -j "${CARGO_BUILD_JOBS:-2}" --manifest-path "$here/Cargo.toml"

apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$apps"
cat > "$apps/org.meo.MeoAI.Cloud.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Meo AI
Comment=Cloud-first Meo AI assistant
Exec=env MEO_UI_IMPORT_PATH=$ui/lib/qt6/qml LD_LIBRARY_PATH=$ui/lib MEO_AI_QML_DIR=$here/qml $target/release/meo-ai-desktop %u
Icon=$ui/share/icons/hicolor/scalable/apps/meo-ai.svg
Terminal=false
Categories=Utility;
MimeType=x-scheme-handler/meoai;
StartupWMClass=meo-ai-desktop
DESKTOP
xdg-mime default org.meo.MeoAI.Cloud.desktop x-scheme-handler/meoai 2>/dev/null || true
echo "Installed: $apps/org.meo.MeoAI.Cloud.desktop"
