"""Exercise pure upstream protocol methods without importing GTK on macOS."""
import ast
import importlib.util
import json
import queue
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("meo_profile", ROOT / "src/meo_profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def protocol_class():
    tree = ast.parse((ROOT / "src/handlers/interfaces/api_handler.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("_sse_chunk", "_render_tool_event", "_drain_queue_to_stream")]
    namespace = {"json": json, "queue": queue}
    pure_class = ast.ClassDef(name="Protocol", bases=[], keywords=[], body=methods, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[pure_class], type_ignores=[])), "upstream-protocol", "exec"), namespace)
    return namespace["Protocol"]


class ProtocolTests(unittest.TestCase):
    def test_non_stream_collector_stays_non_generator(self):
        tree = ast.parse((ROOT / "src/handlers/interfaces/api_handler.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        collector = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_collect_queue")
        self.assertFalse(any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(collector)))

    def test_prompt_order_and_boundary(self):
        layers = profile.prompt_layers()
        self.assertEqual(len(layers), 4)
        self.assertIn("Meo AI", layers[0])
        self.assertIn("never grant authority", layers[1])
        self.assertIn("not a containment sandbox", layers[2])

    def test_pause_preserves_queue_and_typed_choices(self):
        protocol = protocol_class()()
        protocol._pending_streams = {}
        protocol._is_logging_enabled = lambda: False
        protocol._chat_completion_log_print = lambda *a: None
        events = queue.Queue()
        event = {"type": "tool_interaction", "tool_name": "file", "interaction_id": "i1", "options": [{"index": 0, "title": "Deny"}]}
        events.put(("tool", event))
        stream = list(protocol._drain_queue_to_stream("meo:test", "id", 1, "model", events))
        structured = json.loads(stream[0][6:])
        self.assertEqual(structured["choices"][0]["delta"]["meo_event"], event)
        self.assertIs(protocol._pending_streams["meo:test"], events)
        self.assertEqual(stream[-1], "data: [DONE]\n\n")
        # Merely rendering a decision does not invoke a callback or drain work.
        self.assertTrue(events.empty())

    def test_legacy_text_remains_and_completion_finishes(self):
        protocol = protocol_class()()
        protocol._pending_streams = {}
        protocol._is_logging_enabled = lambda: False
        protocol._chat_completion_log_print = lambda *a: None
        events = queue.Queue()
        events.put(("text", "hello")); events.put(("done", None))
        stream = list(protocol._drain_queue_to_stream("regular", "id", 1, "model", events))
        self.assertEqual(json.loads(stream[0][6:])["choices"][0]["delta"]["content"], "hello")
        self.assertEqual(protocol._pending_streams, {})

if __name__ == "__main__":
    unittest.main()
