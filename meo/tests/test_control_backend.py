from __future__ import annotations

import unittest

from meo.adapters.control_backend import ControlledLegacyBackend
from meo.service.backend_adapter import BackendCallbacks


class _Settings:
    def __init__(self):
        self.ints = {
            "context-max": 128000,
            "context-suggested": 30000,
            "max-tool-calls": 70,
            "max-run-times": 5,
        }
        self.bools = {
            "memory-on": True,
            "websearch-on": True,
            "rag-on-documents": True,
            "rag-on": False,
            "auto-run": False,
            "parallel-tool-execution": True,
            "context-summarization": True,
            "usage-tracking": True,
        }

    def get_int(self, key):
        return self.ints[key]

    def get_boolean(self, key):
        return self.bools[key]

    def get_string(self, key):
        raise KeyError(key)


class _SearchIntegration:
    id = "websearch"

    def __init__(self):
        self.calls = []

    def consume_meo_search_traces(self, chat_id, since_monotonic):
        self.calls.append((chat_id, since_monotonic))
        return [{
            "trace_id": "search:one",
            "kind": "web",
            "query": "meo ai latest",
            "provider": "duckduckgo",
            "duration_ms": 345.5,
            "result_count": 2,
            "sources": [
                {"title": "Meo docs", "uri": "https://example.test/docs"},
                {"title": "Meo repo", "uri": "https://example.test/repo"},
            ],
            "filters": {"max_results": "5"},
            "completed": True,
        }]


class _Controller:
    def __init__(self, with_search=False):
        self.settings = _Settings()
        self.handlers = type("Handlers", (), {"llm": None, "memory": object()})()
        if with_search:
            self.search = _SearchIntegration()
            self.integrationsloader = type(
                "IntegrationLoader",
                (),
                {"extensionsmap": {"websearch": self.search}, "extensions": [self.search]},
            )()


class _Backend:
    def list_conversations(self):
        return [{"id": "c1", "legacy_chat_id": 7}]

    def send_message(self, conversation_id, text, callbacks):
        callbacks.on_tool_event({
            "type": "response_meta",
            "usage": {"prompt_tokens": 42000, "completion_tokens": 1200},
            "provider_metadata": {"id": "response_1"},
            "activity": {"search": {"used": True}, "tools": ["search"]},
        })
        callbacks.on_done()
        return object()

    def send_message_with_resources(self, conversation_id, text, resources, callbacks):
        return self.send_message(conversation_id, text, callbacks)


class ControlledLegacyBackendTests(unittest.TestCase):
    def _callbacks(self, events):
        return BackendCallbacks(
            on_text_delta=lambda _delta: None,
            on_tool_event=events.append,
            on_done=lambda: None,
            on_error=lambda error: self.fail(error),
        )

    def test_response_meta_gets_context_budget_and_effective_controls(self):
        events = []
        wrapped = ControlledLegacyBackend(_Backend(), _Controller())
        wrapped.send_message("c1", "hello", self._callbacks(events))

        self.assertEqual(len(events), 1)
        meta = events[0]
        self.assertEqual(meta["context"]["window_tokens"], 128000)
        self.assertEqual(meta["context"]["target_tokens"], 30000)
        self.assertEqual(meta["context"]["used_tokens"], 42000)
        self.assertEqual(meta["context"]["remaining_tokens"], 86000)
        self.assertEqual(meta["context"]["status"], "runtime_budget")
        self.assertTrue(meta["controls"]["memory.enabled"])
        self.assertTrue(meta["controls"]["search.web_enabled"])
        self.assertEqual(meta["controls"]["tools.max_calls"], 70)

    def test_exact_search_trace_becomes_activity_and_citations(self):
        events = []
        controller = _Controller(with_search=True)
        wrapped = ControlledLegacyBackend(_Backend(), controller)
        wrapped.send_message("c1", "search", self._callbacks(events))

        meta = events[0]
        search = meta["activity"]["search"]
        self.assertTrue(search["used"])
        self.assertEqual(search["queries"], ["meo ai latest"])
        self.assertEqual(search["result_count"], 2)
        self.assertEqual(search["traces"][0]["provider"], "duckduckgo")
        self.assertEqual(search["traces"][0]["duration_ms"], 345.5)
        self.assertEqual(search["traces"][0]["sources"][0]["title"], "Meo docs")
        self.assertEqual(meta["citations"][1]["uri"], "https://example.test/repo")
        self.assertEqual(controller.search.calls[0][0], 7)
        self.assertGreater(controller.search.calls[0][1], 0)

    def test_resource_path_uses_same_enrichment(self):
        events = []
        wrapped = ControlledLegacyBackend(_Backend(), _Controller())
        wrapped.send_message_with_resources("c1", "hello", tuple(), self._callbacks(events))
        self.assertEqual(events[0]["context"]["target_tokens"], 30000)

    def test_non_response_events_are_untouched(self):
        wrapped = ControlledLegacyBackend(_Backend(), _Controller())
        event = {"type": "presentation_card", "title": "Status"}
        self.assertIs(wrapped._enrich_response_event(event), event)


if __name__ == "__main__":
    unittest.main()
