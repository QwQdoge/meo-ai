from __future__ import annotations

import unittest

from meo.service.response_meta import (
    configured_context_from_usage,
    json_safe,
    normalize_response_meta,
    normalize_usage,
)


class ResponseMetaTests(unittest.TestCase):
    def test_usage_normalizes_common_aliases_and_keeps_raw_provider_object(self):
        usage = normalize_usage({
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 9},
            "prompt_tokens_details": {"cached_tokens": 80},
            "provider_unit": "tokens",
        })
        self.assertEqual(usage["input_tokens"], 120)
        self.assertEqual(usage["output_tokens"], 30)
        self.assertEqual(usage["total_tokens"], 150)
        self.assertEqual(usage["reasoning_tokens"], 9)
        self.assertEqual(usage["cache_read_tokens"], 80)
        self.assertEqual(usage["raw"]["provider_unit"], "tokens")

    def test_configured_context_uses_real_input_usage_and_labels_budget(self):
        context = configured_context_from_usage(
            {"prompt_tokens": 42000, "completion_tokens": 1000},
            configured_budget=128000,
            reserved_output_tokens=8192,
        )
        self.assertEqual(context["window_tokens"], 128000)
        self.assertEqual(context["used_tokens"], 42000)
        self.assertEqual(context["remaining_tokens"], 86000)
        self.assertEqual(context["max_output_tokens"], 8192)
        self.assertEqual(context["status"], "runtime_budget")
        self.assertEqual(context["strategy"], "configured_context_budget")

    def test_configured_context_does_not_invent_usage_when_provider_has_none(self):
        context = configured_context_from_usage({}, configured_budget=32000, reserved_output_tokens=None)
        self.assertEqual(context["window_tokens"], 32000)
        self.assertNotIn("used_tokens", context)
        self.assertNotIn("remaining_tokens", context)

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
        self.assertEqual(normalized["response_id"], "resp_123")
        self.assertEqual(normalized["finish_reason"], "stop")
        self.assertEqual(normalized["request_id_provider"], "req_1")
        self.assertEqual(normalized["provider_metadata"]["id"], "resp_123")
        self.assertEqual(normalized["provider_metadata"]["new_future_field"], {"a": 1})
        self.assertEqual(normalized["provider_metadata"]["headers"]["Authorization"], "<redacted>")
        self.assertEqual(normalized["provider_metadata"]["headers"]["set-cookie"], "<redacted>")

    def test_provider_field_aliases_support_nested_choices(self):
        normalized = normalize_response_meta({
            "provider_metadata": {
                "choices": [{"finish_reason": "length"}],
                "service_tier": "priority",
                "system_fingerprint": "fp_1",
            }
        })
        self.assertEqual(normalized["finish_reason"], "length")
        self.assertEqual(normalized["service_tier"], "priority")
        self.assertEqual(normalized["system_fingerprint"], "fp_1")

    def test_reasoning_is_only_exposed_when_provider_returned_it(self):
        hidden = normalize_response_meta({"provider_metadata": {"message": "ordinary answer"}})
        self.assertFalse(hidden["reasoning"]["available"])
        self.assertFalse(hidden["reasoning"]["provider_returned"])

        visible = normalize_response_meta({
            "provider_metadata": {"reasoning_summary": "provider-visible reasoning summary"}
        })
        self.assertTrue(visible["reasoning"]["available"])
        self.assertTrue(visible["reasoning"]["provider_returned"])
        self.assertEqual(visible["reasoning"]["text"], "provider-visible reasoning summary")

    def test_timing_context_activity_controls_and_citations_are_structured(self):
        normalized = normalize_response_meta({
            "timing": {
                "total_ms": 1234.5,
                "first_token_ms": 145,
                "first_visible_token_ms": 190,
                "queue_ms": 20,
            },
            "context": {
                "window_tokens": 128000,
                "used_tokens": 42000,
                "remaining_tokens": 86000,
                "trimmed_messages": 3,
                "strategy": "summarize-oldest",
            },
            "activity": {
                "memory": {"used": True, "items": 2},
                "search": {"queries": ["Meo AI"]},
                "tools": ["web.search", "filesystem.read"],
                "mcp": ["github"],
                "files": 3,
            },
            "controls": {
                "reasoning_effort": "high",
                "temperature": 0.2,
            },
            "cost": {"total": 0.013, "currency": "USD"},
            "rate_limits": {"remaining_requests": 42},
            "citations": [{"title": "Example", "url": "https://example.invalid"}],
        })
        self.assertEqual(normalized["timing"]["total_ms"], 1234.5)
        self.assertEqual(normalized["context"]["remaining_tokens"], 86000)
        self.assertAlmostEqual(normalized["context"]["percent_used"], 32.81)
        self.assertTrue(normalized["activity"]["memory"]["used"])
        self.assertEqual(normalized["activity"]["tools"][0], "web.search")
        self.assertEqual(normalized["controls"]["reasoning_effort"], "high")
        self.assertEqual(normalized["cost"]["currency"], "USD")
        self.assertEqual(normalized["rate_limits"]["remaining_requests"], 42)
        self.assertEqual(normalized["citations"][0]["title"], "Example")

    def test_unknown_backend_and_provider_fields_are_not_dropped(self):
        normalized = normalize_response_meta({
            "provider_metadata": {"brand_new_api_field": {"hello": "world"}},
            "future_backend_field": [1, 2, 3],
        })
        self.assertEqual(
            normalized["provider_metadata"]["brand_new_api_field"],
            {"hello": "world"},
        )
        self.assertEqual(normalized["extra"]["future_backend_field"], [1, 2, 3])

    def test_json_safe_bounds_binary_values(self):
        self.assertEqual(json_safe(b"abc"), "<bytes:3>")


if __name__ == "__main__":
    unittest.main()
