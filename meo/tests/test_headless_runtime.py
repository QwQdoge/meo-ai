import sys
import types
import unittest
from unittest import mock

from meo.runtime.headless_probe import inspect_loaded_modules
from meo.runtime.main import build_service, load_backend_factory, main
from meo.service.backend_adapter import BackendCallbacks


class FakeBackend:
    def list_conversations(self): return []
    def create_conversation(self): return "conversation:test"
    def conversation_exists(self, conversation_id): return conversation_id == "conversation:test"
    def send_message(self, conversation_id, text, callbacks: BackendCallbacks):
        callbacks.on_done(); return object()
    def choose_tool_option(self, execution_handle, legacy_option_index): pass
    def cancel(self, execution_handle): pass
    def list_models(self): return []
    def set_model(self, conversation_id, model_id): pass
    def list_skills(self): return []
    def set_skill_enabled(self, skill_id, enabled): pass
    def list_mcp_servers(self): return []


def fake_factory():
    return FakeBackend()


def this_module_factory_spec():
    return f"{__name__}:fake_factory"


class FakeServer:
    server_address = ("127.0.0.1", 8765)

    def __init__(self):
        self.served = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def server_close(self):
        self.closed = True


class HeadlessRuntimeTests(unittest.TestCase):
    def test_static_probe_detects_forbidden_prefixes(self):
        result = inspect_loaded_modules([
            "json",
            "gi.repository.Gtk",
            "src.ui_controller",
            "src.handlers.llm",
        ])
        self.assertFalse(result.clean)
        self.assertEqual(
            result.forbidden_modules,
            ("gi.repository.Gtk", "src.ui_controller"),
        )

    def test_self_check_without_backend(self):
        self.assertEqual(main(["--self-check"]), 0)

    def test_factory_builds_service(self):
        service = build_service(this_module_factory_spec())
        self.assertIsInstance(service.backend, FakeBackend)

    def test_factory_module_that_loads_ui_is_rejected(self):
        module_name = "meo.tests.fake_dirty_backend"
        module = types.ModuleType(module_name)
        module.factory = fake_factory
        with mock.patch.dict(sys.modules, {module_name: module, "src.ui_controller": types.ModuleType("src.ui_controller")}, clear=False):
            with self.assertRaises(RuntimeError):
                load_backend_factory(f"{module_name}:factory")

    def test_normal_start_runs_loopback_transport(self):
        fake_server = FakeServer()
        with mock.patch("meo.runtime.main.create_http_server", return_value=fake_server) as create:
            self.assertEqual(main(["--backend-factory", this_module_factory_spec()]), 0)
        create.assert_called_once()
        self.assertTrue(fake_server.served)
        self.assertTrue(fake_server.closed)


if __name__ == "__main__":
    unittest.main()
