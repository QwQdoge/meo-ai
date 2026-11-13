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


def live_recovery_requested():
    """True with --live-recovery, or inside the MeoArch Live environment.

    The packaged Meo AI desktop app and AgentService are not started through
    the GTK launcher, so the Live ISO itself (/run/archiso) also counts.
    """
    import os
    return os.environ.get("MEO_AI_LIVE_RECOVERY") == "1" or os.path.isdir("/run/archiso")


def live_recovery_layer():
    """Extra behaviour guidance for the Live ISO recovery conversation."""
    if not live_recovery_requested():
        return []
    package = Path(__file__).resolve().parent
    root = package.parent / "meo" / "prompts"
    if not root.is_dir():
        root = package / "meo-prompts"
    try:
        return [(root / "live-recovery.md").read_text(encoding="utf-8")]
    except OSError:
        return []


def bundled_skills_dir():
    """Skills shipped with MeoArch. Read-only data; lowest priority."""
    package = Path(__file__).resolve().parent
    for candidate in (package.parent / "meo" / "skills", package / "meo-skills"):
        if candidate.is_dir():
            return str(candidate)
    return None
