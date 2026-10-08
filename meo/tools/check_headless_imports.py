#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "meo" / "service"
BANNED_ROOTS = {"gi", "Gtk", "Adw", "WebKit", "WebKit2"}
BANNED_PROJECT_PREFIXES = {"src.ui", "src.ui_controller"}


def imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.append(module)
    return found


def main() -> int:
    failures: list[str] = []
    for path in sorted(SERVICE.rglob("*.py")):
        for name in imported_names(path):
            root = name.split(".", 1)[0]
            if root in BANNED_ROOTS or any(name == p or name.startswith(p + ".") for p in BANNED_PROJECT_PREFIXES):
                failures.append(f"{path.relative_to(ROOT)} imports forbidden headless dependency: {name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"headless import gate passed for {len(list(SERVICE.rglob('*.py')))} service modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
