"""Optional regression against the real GI/Newelle import graph, without mocks."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]

class RealHeadlessImportTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MEO_AI_RUN_NEWELLE_IMPORT_TEST") == "1", "opt-in real Newelle dependencies required")
    def test_controller_import_does_not_load_ui(self):
        code = "import gettext; gettext.install('newelle'); from meo.adapters.headless_newelle import _import_controller_class; from meo.runtime.headless_probe import require_headless; _import_controller_class(); require_headless()"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_controller_settings_keys_exist_in_packaged_schema(self):
        keys = {node.attrib["name"] for node in ET.parse(ROOT / "data/io.github.qwersyk.Newelle.gschema.xml").findall(".//key")}
        tree = ast.parse((ROOT / "src/controller.py").read_text())
        missing = set()
        methods = {"get_string", "get_boolean", "get_int", "get_double", "get_strv", "set_string", "set_boolean", "set_int", "set_double", "set_strv"}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in methods and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str) and node.args[0].value not in keys):
                missing.add(node.args[0].value)
        self.assertEqual(missing, set())

    @unittest.skipUnless(os.environ.get("MEO_AI_RUN_NEWELLE_IMPORT_TEST") == "1", "opt-in real Newelle dependencies required")
    def test_cancel_prevents_queued_tool_execution(self):
        code = '''
import gettext
gettext.install("newelle")
import threading
from types import SimpleNamespace
from meo.adapters.headless_newelle import _import_controller_class
Controller = _import_controller_class()
c = Controller.__new__(Controller)
c.workspace_local = threading.local()
c.workspace_lock = threading.Lock()
event = threading.Event()
context = {"cancelled": event, "handlers": SimpleNamespace(llm=None, secondary_llm=None)}
c.active_request_contexts = {7: [context]}
c.workspace_local.context = context
calls = []
c.tools = SimpleNamespace(get_tool=lambda name: SimpleNamespace(execute=lambda **args: calls.append(args)))
c.stop_workspace_request(7)
assert event.is_set()
c.execute_tool_on_main_thread("live", {})
assert calls == []
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.environ.get("MEO_AI_RUN_NEWELLE_IMPORT_TEST") == "1", "opt-in real Newelle dependencies required")
    def test_ollama_stop_closes_stream(self):
        code = '''
import gettext
gettext.install("newelle")
from meo.adapters.headless_newelle import _import_controller_class
_import_controller_class()
from src.handlers.llm.ollama_handler import OllamaHandler
from types import SimpleNamespace
handler = OllamaHandler.__new__(OllamaHandler)
handler.get_setting = lambda key, *args: {"thinking": False, "native_tool_calling": False, "model": "test"}.get(key)
handler.convert_history = lambda *args: []
handler.auto_serve = lambda client: None
closed = []
def stream():
    try:
        yield {"message": {"content": "first"}}
        yield {"message": {"content": "must not arrive"}}
    finally:
        closed.append(True)
handler.create_client = lambda: SimpleNamespace(chat=lambda **args: stream())
updates = []
def update(text):
    updates.append(text)
    handler.stop()
assert handler.generate_text_stream("test", history=[], on_update=update) == "first"
assert updates == ["first"] and closed == [True]
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.environ.get("MEO_AI_RUN_NEWELLE_IMPORT_TEST") == "1", "opt-in real Newelle dependencies required")
    def test_deferred_annotations_preserve_tool_schema(self):
        code = "from src.tools import Tool, Command; scope = {}; exec('from __future__ import annotations\ndef f(count: int, enabled: bool, ratio: float): pass', scope); expected = {'count': {'type': 'integer'}, 'enabled': {'type': 'boolean'}, 'ratio': {'type': 'number'}}; assert Tool('test', 'test', scope['f']).schema['properties'] == expected; assert Command('test', 'test', scope['f']).schema['properties'] == expected"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
