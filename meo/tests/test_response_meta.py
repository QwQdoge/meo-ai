from __future__ import annotations

import unittest

from meo.service.response_meta import json_safe, normalize_response_meta, normalize_usage


class ResponseMetaTests(unittest.TestCase):
    def test_usage_keeps_known_counts_and_provider_extras(self):
        usage = normalize_usage({
            "input_tokens": 120,
            "output_tokens": 30,
            "reasoning_tokens": 9,
            "cache_read_tokens": 80,
            "provider_unit": "tokens",
        })
        self.assertEqual(usage["total_tokens"], 150)
        self.assertEqual(usage["reasoning_tokens"], 9)
        self.assertEqual(usage["cache_read_tokens"], 80)
        self.assertEqual(usage["extra"]["provider_unit"], "tokens")

    def test_provider_metadata_is_preserved_but_secrets_are_redacted(self):
        normalized = normalize_response_meta({
            "type": "response_meta",
            "provider": "OpenAI-compatible",
            "model": "example-model",
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "provider_metadata": {
                "id": "resp_123",
                "finish_reason": "stop",
                "headers": {
                    "x-request-id": "req_1",
                    "Authorization": "Bearer secret",
                    "set-cookie": "private",
                },
                "new_future_field": {"a": 1},
            },
        })
        self.assertEqual(normalized["provider_metadata"]["id"], "resp_123")
        self.assertEqual(normalized["provider_metadata"]["new_future_field"], {"a": 1})
        self.assertEqual(normalized["provider_metadata"]["headers"]["Authorization"], "<redacted>")
        self.assertEqual(normalized["provider_metadata"]["headers"]["set-cookie"], "<redacted>")

    def test_reasoning_is_only_exposed_when_provider_returned_it(self):
        hidden = normalize_response_meta({"provider_metadata": {"message": "ordinary answer"}})
        self.assertFalse(hidden["reasoning"]["available"])

        visible = normalize_response_meta({
            "provider_metadata": {"reasoning_content": "provider-visible reasoning summary"}
        })
        self.assertTrue(visible["reasoning"]["available"])
        self.assertEqual(visible["reasoning"]["text"], "provider-visible reasoning summary")

    def test_timing_context_activity_and_citations_are_structured(self):
        normalized = normalize_response_meta({
            "timing": {
                "total_ms": 1234.5,
                "first_token_ms": 145,
                "first_visible_token_ms": 190,
            },
            "context": {
                "window_tokens": 128000,
                "used_tokens": 42000,
                "remaining_tokens": 86000,
                "trimmed_messages": 3,
                "strategy": "summarize-oldest",
            },
            "activity": {
                "memory": True,
                "search": {"queries": ["Meo AI"]},
                "tools": ["web.search", "filesystem.read"],
            },
            "citations": [{"title": "Example", "url": "https://example.invalid"}],
        })
        self.assertEqual(normalized["timing"]["total_ms"], 1234.5)
        self.assertEqual(normalized["context"]["remaining_tokens"], 86000)
        self.assertTrue(normalized["activity"]["memory"])
        self.assertEqual(normalized["activity"]["tools"][0], "web.search")
        self.assertEqual(normalized["citations"][0]["title"], "Example")

    def test_json_safe_bounds_binary_values(self):
        self.assertEqual(json_safe(b"abc"), "<bytes:3>")


if __name__ == "__main__":
    unittest.main()
