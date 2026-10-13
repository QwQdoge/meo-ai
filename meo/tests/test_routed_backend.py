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
            ModelInfo(
                "main:strong",
                "Strong",
                "Main",
                selected=self.current == "main:strong",
                supports_vision=True,
            ),
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


class DeferredVerifyingBackend(FakeBackend):
    def __init__(self, judge_outputs: list[str]) -> None:
        super().__init__()
        self.callbacks: BackendCallbacks | None = None
        self.judge_outputs = list(judge_outputs)
        self.auxiliary_calls: list[tuple[str, str]] = []

    def send_message(self, _conversation_id: str, _text: str, callbacks: BackendCallbacks):
        self.calls.append(("send", self.current))
        self.callbacks = callbacks
        callbacks.on_text_delta("unverified candidate")
        callbacks.on_tool_event({"type": "response_meta", "activity": {"tools": ["shell"]}})
        return object()

    def generate_auxiliary(self, model_id: str, prompt: str, _system_prompt=None) -> str:
        self.auxiliary_calls.append((model_id, prompt))
        return self.judge_outputs.pop(0)


class DeterministicModelRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selected=False),
            ModelInfo("main:strong", "Strong", "Main", selected=True, supports_vision=True),
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

    def test_image_resource_uses_vision_role_and_capable_model(self) -> None:
        image = InputResource("resource:image", "image", "shot.png", "image/png", b"png")
        decision = self.router.decide("What is wrong here?", (image,), self.models, self.roles)
        self.assertEqual(decision.role_id, "vision")
        self.assertTrue(decision.needs_vision)
        self.assertEqual(decision.model_id, "main:strong")

    def test_stale_vision_preference_to_text_only_model_falls_back(self) -> None:
        self.roles._assignments["vision"] = "cheap:tiny"
        image = InputResource("resource:image", "image", "shot.png", "image/png", b"png")
        decision = self.router.decide("Read this image", (image,), self.models, self.roles)
        self.assertEqual(decision.model_id, "main:strong")
        self.assertTrue(decision.fallback_used)

    def test_image_request_fails_when_no_vision_model_exists(self) -> None:
        models = [ModelInfo("text:only", "Text only", "Text", selected=True)]
        image = InputResource("resource:image", "image", "shot.png", "image/png", b"png")
        with self.assertRaisesRegex(ValueError, "no vision-capable model"):
            self.router.decide("Read this image", (image,), models, self.roles)


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

    def test_execution_candidate_is_hidden_until_judge_accepts(self) -> None:
        backend = DeferredVerifyingBackend([
            '{"verdict":"ACCEPT","issues":[],"confidence":0.95}',
        ])
        roles = ModelRoleRegistry()
        roles.set_role("judge", "cheap:tiny", backend.list_models())
        routed = RoutedBackend(backend, roles)
        text_events: list[str] = []
        tool_events: list[dict] = []
        done_events: list[str] = []
        callbacks = BackendCallbacks(
            on_text_delta=text_events.append,
            on_tool_event=tool_events.append,
            on_done=lambda: done_events.append("done"),
            on_error=lambda error: done_events.append(error),
        )

        routed.send_message("meo:1", "Fix this code", callbacks)
        self.assertEqual(text_events, [])
        self.assertEqual(tool_events, [])
        self.assertIsNotNone(backend.callbacks)

        backend.callbacks.on_done()

        self.assertEqual(text_events, ["unverified candidate"])
        self.assertEqual(done_events, ["done"])
        self.assertEqual(backend.auxiliary_calls[0][0], "cheap:tiny")
        self.assertEqual(tool_events[0]["verification"]["status"], "accepted")
        self.assertEqual(tool_events[0]["activity"]["verification"]["used"], True)
        self.assertEqual(tool_events[0]["activity"]["tools"], ["shell"])

    def test_catalog_is_exposed_as_request_scoped_and_preserves_capabilities(self) -> None:
        routed = RoutedBackend(FakeBackend(), ModelRoleRegistry())
        catalog = routed.list_models()
        self.assertTrue(all(item.selection_scope == "request" for item in catalog))
        self.assertTrue(next(item for item in catalog if item.model_id == "main:strong").supports_vision)

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

    def test_router_error_does_not_leave_request_lock_held(self) -> None:
        backend = FakeBackend()
        backend.list_models = lambda: [ModelInfo("text:only", "Text", selected=True)]
        routed = RoutedBackend(backend, ModelRoleRegistry())
        callbacks = BackendCallbacks(
            on_text_delta=lambda _delta: None,
            on_tool_event=lambda _event: None,
            on_done=lambda: None,
            on_error=lambda _error: None,
        )
        image = InputResource("resource:image", "image", "shot.png", "image/png", b"png")
        with self.assertRaisesRegex(ValueError, "no vision-capable model"):
            routed.send_message_with_resources("meo:1", "read", (image,), callbacks)
        routed.send_message("meo:1", "hello", callbacks)
        self.assertIn(("send", "main:strong"), backend.calls)


if __name__ == "__main__":
    unittest.main()
