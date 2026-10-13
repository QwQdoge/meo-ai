from __future__ import annotations

import unittest

from meo.adapters.newelle_multimodal import NewelleMultimodalBridge
from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo


class FakeBackend:
    def __init__(self, *, vision_selected: bool = True) -> None:
        self.vision_selected = vision_selected
        self.calls: list[tuple] = []

    def list_models(self):
        return [
            ModelInfo("text:model", "Text", selected=not self.vision_selected),
            ModelInfo("vision:model", "Vision", selected=self.vision_selected),
        ]

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        self.calls.append(("send", conversation_id, text))
        callbacks.on_done()
        return object()

    def send_message_with_resources(self, conversation_id: str, text: str, resources, callbacks: BackendCallbacks):
        self.calls.append(("resources", conversation_id, text, tuple(resources)))
        callbacks.on_done()
        return object()


class MixedBackend(FakeBackend):
    def list_models(self):
        return [
            ModelInfo("mixed:text-only", "Mixed Text", selected=False),
            ModelInfo("mixed:camera", "Mixed Vision", selected=True),
        ]


class FakeController:
    settings = object()

    class Handlers:
        directory = "/tmp"

    handlers = Handlers()


class TestBridge(NewelleMultimodalBridge):
    def _provider_supports_vision(self, provider_name: str) -> bool:
        return provider_name == "vision"


class PerModelBridge(NewelleMultimodalBridge):
    def _provider_model_supports_vision(self, provider_name: str, raw_model_id: str) -> bool:
        return provider_name == "mixed" and raw_model_id == "camera"


class NewelleMultimodalBridgeTests(unittest.TestCase):
    def callbacks(self, events: list[str]) -> BackendCallbacks:
        return BackendCallbacks(
            on_text_delta=lambda _delta: None,
            on_tool_event=lambda _event: None,
            on_done=lambda: events.append("done"),
            on_error=lambda error: events.append(error),
        )

    def test_catalog_uses_provider_vision_capability(self) -> None:
        bridge = TestBridge(FakeBackend(), FakeController())
        catalog = bridge.list_models()
        self.assertFalse(next(item for item in catalog if item.model_id == "text:model").supports_vision)
        self.assertTrue(next(item for item in catalog if item.model_id == "vision:model").supports_vision)
        self.assertTrue(next(item for item in catalog if item.model_id == "vision:model").selected)

    def test_catalog_can_scope_vision_to_one_model_inside_provider(self) -> None:
        bridge = PerModelBridge(MixedBackend(), FakeController())
        catalog = bridge.list_models()
        self.assertFalse(
            next(item for item in catalog if item.model_id == "mixed:text-only").supports_vision
        )
        self.assertTrue(
            next(item for item in catalog if item.model_id == "mixed:camera").supports_vision
        )

    def test_image_bytes_become_existing_newelle_image_block(self) -> None:
        backend = FakeBackend()
        bridge = TestBridge(backend, FakeController())
        events: list[str] = []
        image = InputResource("resource:1", "image", "shot.png", "image/png", b"png")

        bridge.send_message_with_resources("meo:1", "Describe it", (image,), self.callbacks(events))

        self.assertEqual(events, ["done"])
        self.assertEqual(backend.calls[0][0], "send")
        prompt = backend.calls[0][2]
        self.assertIn("Attached image: shot.png", prompt)
        self.assertIn("```image\ndata:image/png;base64,cG5n\n```", prompt)
        self.assertTrue(prompt.endswith("Describe it"))

    def test_image_and_text_resource_keep_text_resource_on_legacy_path(self) -> None:
        backend = FakeBackend()
        bridge = TestBridge(backend, FakeController())
        image = InputResource("resource:1", "image", "shot.png", "image/png", b"png")
        note = InputResource("resource:2", "long_text", "note.txt", "text/plain", b"hello")

        bridge.send_message_with_resources("meo:1", "Compare", (image, note), self.callbacks([]))

        kind, _conversation, prompt, remaining = backend.calls[0]
        self.assertEqual(kind, "resources")
        self.assertIn("data:image/png;base64,cG5n", prompt)
        self.assertEqual(remaining, (note,))

    def test_text_only_selected_model_rejects_images(self) -> None:
        backend = FakeBackend(vision_selected=False)
        bridge = TestBridge(backend, FakeController())
        image = InputResource("resource:1", "image", "shot.png", "image/png", b"png")
        with self.assertRaisesRegex(ValueError, "does not support vision"):
            bridge.send_message_with_resources("meo:1", "Read", (image,), self.callbacks([]))
        self.assertEqual(backend.calls, [])

    def test_image_kind_requires_image_mime(self) -> None:
        backend = FakeBackend()
        bridge = TestBridge(backend, FakeController())
        invalid = InputResource("resource:1", "image", "bad.bin", "application/octet-stream", b"data")
        with self.assertRaisesRegex(ValueError, "invalid MIME"):
            bridge.send_message_with_resources("meo:1", "Read", (invalid,), self.callbacks([]))


if __name__ == "__main__":
    unittest.main()
