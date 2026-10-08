import ast
import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


class HeadlessNewelleAdapterTests(unittest.TestCase):
    def test_module_import_is_lazy_and_does_not_load_newelle_ui(self):
        before = set(sys.modules)
        module = importlib.import_module("meo.adapters.headless_newelle")
        after = set(sys.modules) - before
        self.assertTrue(hasattr(module, "create_backend"))
        self.assertNotIn("src.main", sys.modules)
        self.assertNotIn("src.ui_controller", sys.modules)
        self.assertNotIn("gi.repository.Gtk", sys.modules)
        self.assertNotIn("gi.repository.Adw", sys.modules)
        self.assertFalse(any(name.startswith("src.ui.") for name in after))

    def test_adapter_source_never_imports_src_main(self):
        source = (ROOT / "meo/adapters/headless_newelle.py").read_text()
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertNotIn("src.main", imported)
        self.assertNotIn("src.ui_controller", imported)

    def test_headless_ui_controller_is_widget_free(self):
        source = (ROOT / "meo/adapters/headless_newelle.py").read_text()
        self.assertNotIn("Gtk.", source)
        self.assertNotIn("Adw.", source)
        self.assertNotIn("WebKit", source)

    def test_system_tools_are_explicit_opt_in(self):
        module = importlib.import_module("meo.adapters.headless_newelle")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(module._system_tools_enabled())
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value), mock.patch.dict(
                os.environ, {"MEO_AI_ENABLE_SYSTEM_TOOL": value}, clear=True
            ):
                self.assertTrue(module._system_tools_enabled())
        with mock.patch.dict(
            os.environ, {"MEO_AI_ENABLE_SYSTEM_TOOL": "0"}, clear=True
        ):
            self.assertFalse(module._system_tools_enabled())


if __name__ == "__main__":
    unittest.main()
