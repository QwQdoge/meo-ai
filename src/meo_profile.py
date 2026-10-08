"""Meo prompt overlay. This is behavior guidance, never a permission boundary."""
from pathlib import Path

LAYERS = ("base", "system-control", "terminal", "repair")


def prompt_layers():
    # Source checkout first; Meson installs the same files beside the package.
    package = Path(__file__).resolve().parent
    root = package.parent / "meo" / "prompts"
    if not root.is_dir():
        root = package / "meo-prompts"
    return [(root / f"{name}.md").read_text(encoding="utf-8") for name in LAYERS]
