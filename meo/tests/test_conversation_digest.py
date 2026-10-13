from __future__ import annotations

import unittest

from meo.adapters.routed_backend import RoutedBackend
from meo.service.backend_adapter import BackendCallbacks, ModelInfo
from meo.service.conversation_digest import ConversationDigestGenerator, newelle_automatic_chat_title
from meo.service.model_roles import ModelRoleRegistry


class DigestBackend:
    def __init__(self, *, output: str = '{"title":"Linux Build Fix","summary":"The user asked to fix a Linux build and the assistant explained the solution."}') -> None:
        self.output = output
        self.calls: list[tuple] = []
        self.saved: list[dict] = []
        self.needs_digest = True

    def generate_auxiliary(self, model_id: str, prompt: str, system_prompt=None) -> str:
        self.calls.append(("aux", model_id, prompt, tuple(system_prompt or [])))
        if isinstance(self.output, Exception):
            raise self.output
        return self.output

    def conversation_needs_digest(self, conversation_id: str) -> bool:
        self.calls.append(("needs", conversation_id))
        return self.needs_digest

    def apply_conversation_digest(self, conversation_id: str, *, title: str, summary: str = "") -> None:
        self.saved.append({"conversation_id": conversation_id, "title": title, "summary": summary})
        self.needs_digest = False


class RoutedDigestBackend(DigestBackend):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current = "main:strong"
        self.sent: list[tuple[str, str]] = []

    def list_models(self):
        return [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selected=self.current == "cheap:tiny"),
            ModelInfo("main:strong", "Strong", "Main", selected=self.current == "main:strong"),
        ]

    def set_model(self, _conversation_id: str, model_id: str) -> None:
        self.current = model_id

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        self.sent.append((conversation_id, self.current))
        callbacks.on_text_delta("Useful answer")
        callbacks.on_tool_event({"type": "response_meta", "activity": {}})
        callbacks.on_done()
        return object()


class ConversationDigestGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap"),
            ModelInfo("main:strong", "Strong", "Main", selected=True),
        ]
        self.roles = ModelRoleRegistry()
        self.roles.set_role("title", "cheap:tiny", self.models)

    def test_headless_auto_title_mirrors_newelle_markdown_and_truncation_rules(self) -> None:
        self.assertEqual(newelle_automatic_chat_title("**Fix** [Linux](https://example.invalid) build"), "Fix Linux build")
        self.assertEqual(newelle_automatic_chat_title("prefix\n```image\nsecret payload\n```\nsuffix"), "prefix suffix")
        self.assertEqual(
            newelle_automatic_chat_title("Please investigate this Linux graphics driver regression and explain every relevant failure"),
            "Please investigate this Linux…",
        )

    def test_uses_title_role_and_persists_bounded_metadata(self) -> None:
        backend = DigestBackend(
            output='```json\n{"title":"  Linux   Build Fix  ","summary":"Short useful summary."}\n```'
        )
        outcome = ConversationDigestGenerator(backend, self.roles).maybe_generate(
            "meo:1", "Fix my Linux build", "Useful answer", self.models
        )

        self.assertEqual(outcome.metadata["status"], "completed")
        self.assertEqual(outcome.metadata["model_id"], "cheap:tiny")
        self.assertEqual(backend.calls[1][1], "cheap:tiny")
        self.assertEqual(backend.saved[0]["title"], "Linux Build Fix")
        self.assertEqual(backend.saved[0]["summary"], "Short useful summary.")

    def test_named_conversation_skips_auxiliary_call(self) -> None:
        backend = DigestBackend()
        backend.needs_digest = False
        outcome = ConversationDigestGenerator(backend, self.roles).maybe_generate(
            "meo:1", "Hello", "Hi", self.models
        )
        self.assertEqual(outcome.metadata["status"], "skipped")
        self.assertEqual([call for call in backend.calls if call[0] == "aux"], [])

    def test_provider_or_parser_failure_is_fail_open_metadata(self) -> None:
        backend = DigestBackend(output=RuntimeError("provider unavailable"))
        outcome = ConversationDigestGenerator(backend, self.roles).maybe_generate(
            "meo:1", "Hello", "Hi", self.models
        )
        self.assertEqual(outcome.metadata["status"], "failed")
        self.assertIn("provider unavailable", outcome.metadata["reason"])
        self.assertEqual(backend.saved, [])


class RoutedConversationDigestTests(unittest.TestCase):
    @staticmethod
    def callbacks(events: list, text: list[str]) -> BackendCallbacks:
        return BackendCallbacks(
            on_text_delta=text.append,
            on_tool_event=events.append,
            on_done=lambda: events.append("done"),
            on_error=lambda error: events.append(error),
        )

    def test_successful_first_reply_uses_cheap_title_model(self) -> None:
        backend = RoutedDigestBackend()
        roles = ModelRoleRegistry()
        roles.set_role("title", "cheap:tiny", backend.list_models())
        routed = RoutedBackend(backend, roles)
        events: list = []
        text: list[str] = []

        routed.send_message("meo:1", "Hello there", self.callbacks(events, text))

        self.assertEqual(text, ["Useful answer"])
        self.assertEqual(events[-1], "done")
        self.assertEqual(backend.saved[0]["title"], "Linux Build Fix")
        aux = [call for call in backend.calls if call[0] == "aux"]
        self.assertEqual(aux[0][1], "cheap:tiny")

    def test_digest_failure_does_not_fail_chat_or_hold_route_lock(self) -> None:
        backend = RoutedDigestBackend(output=RuntimeError("title provider failed"))
        roles = ModelRoleRegistry()
        roles.set_role("title", "cheap:tiny", backend.list_models())
        routed = RoutedBackend(backend, roles)

        first_events: list = []
        routed.send_message("meo:1", "Hello", self.callbacks(first_events, []))
        second_events: list = []
        routed.send_message("meo:1", "Hello again", self.callbacks(second_events, []))

        self.assertEqual(first_events[-1], "done")
        self.assertEqual(second_events[-1], "done")
        self.assertEqual(backend.saved, [])
        self.assertEqual(len(backend.sent), 2)


if __name__ == "__main__":
    unittest.main()
