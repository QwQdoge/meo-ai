from __future__ import annotations

import threading
import unittest

from meo.adapters.routed_backend import DeterministicModelRouter, RoutedBackend
from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo
from meo.service.model_roles import ModelRoleRegistry


class FakeBackend:
    def __init__(self) -> None:
        self.current = "main:strong"
        self.calls: list[tuple[str, str]] = []

    def list_models(self):
        return [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selected=self.current == "cheap:tiny"),
            ModelInfo("main:strong", "Strong", "Main", selected=self.current == "main:strong"),
        ]

    def set_model(self, _conversation_id: str, model_id: str) -> None:
        self.current = model_id
        self.calls.append(("set", model_id))

    def send_message(self, _conversation_id: str, _text: str, callbacks: BackendCallbacks):
        self.calls.append(("send", self.current))
        callbacks.on_tool_event({"type": "response_meta", "activity": {}})
        callbacks.on_done()
        return object()


class DeferredBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.callbacks: BackendCallbacks | None = None
        self.started = threading.Event()

    def send_message(self, _conversation_id: str, _text: str, callbacks: BackendCallbacks):
        self.calls.append(("send", self.current))
        self.callbacks = callbacks
        self.started.set()
        return object()


class DeterministicModelRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selected=False),
            ModelInfo("main:strong", "Strong", "Main", selected=True),
        ]
        self.roles = ModelRoleRegistry()
        self.router = DeterministicModelRouter()

    def test_simple_chat_stays_on_chat_role(self) -> None:
        decision = self.router.decide("你好", (), self.models, self.roles)
        self.assertEqual(decision.role_id, "chat")
        self.assertFalse(decision.needs_tools)
        self.assertEqual(decision.complexity, "low")

    def test_coding_action_uses_execution_role(self) -> None:
        self.roles.set_role("execution", "cheap:tiny", self.models)
        decision = self.router.decide("Fix this C++ build bug", (), self.models, self.roles)
        self.assertEqual(decision.role_id, "execution")
        self.assertEqual(decision.intent, "coding")
        self.assertEqual(decision.model_id, "cheap:tiny")
        self.assertTrue(decision.needs_tools)

    def test_image_resource_uses_vision_role(self) -> None:
        image = InputResource("resource:image", "image", "shot.png", "image/png", b"png")
        decision = self.router.decide("What is wrong here?", (image,), self.models, self.roles)
        self.assertEqual(decision.role_id, "vision")
        self.assertTrue(decision.needs_vision)


class RoutedBackendTests(unittest.TestCase):
    def test_request_switches_to_assigned_model_then_restores_profile(self) -> None:
        backend = FakeBackend()
        roles = ModelRoleRegistry()
        roles.set_role("execution", "cheap:tiny", backend.list_models())
        routed = RoutedBackend(backend, roles)
        events: list[object] = []
        callbacks = BackendCallbacks(
            on_text_delta=lambda _delta: None,
            on_tool_event=events.append,
            on_done=lambda: events.append("done"),
            on_error=lambda error: events.append(error),
        )

        routed.send_message("meo:1", "Fix this C++ build bug", callbacks)

        self.assertIn(("send", "cheap:tiny"), backend.calls)
        self.assertEqual(backend.current, "main:strong")
        self.assertEqual(events[0]["routing"]["role_id"], "execution")
        self.assertEqual(events[0]["routing"]["model_id"], "cheap:tiny")
        self.assertEqual(events[-1], "done")

    def test_catalog_is_exposed_as_request_scoped(self) -> None:
        routed = RoutedBackend(FakeBackend(), ModelRoleRegistry())
        self.assertTrue(all(item.selection_scope == "request" for item in routed.list_models()))

    def test_profile_switch_is_held_until_request_finishes(self) -> None:
        backend = DeferredBackend()
        roles = ModelRoleRegistry()
        roles.set_role("execution", "cheap:tiny", backend.list_models())
        routed = RoutedBackend(backend, roles)
        callbacks = BackendCallbacks(
            on_text_delta=lambda _delta: None,
            on_tool_event=lambda _event: None,
            on_done=lambda: None,
            on_error=lambda _error: None,
        )

        routed.send_message("meo:1", "Fix this code", callbacks)
        self.assertEqual(backend.current, "cheap:tiny")
        self.assertIsNotNone(backend.callbacks)
        backend.callbacks.on_done()
        self.assertEqual(backend.current, "main:strong")


if __name__ == "__main__":
    unittest.main()
