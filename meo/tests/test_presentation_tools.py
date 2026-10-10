import json
import unittest

from meo.adapters.presentation_tools import (
    NewellePresentationToolAdapter,
    decode_presentation_display,
    encode_presentation_display,
)


class _FakeToolResult:
    def __init__(self, output=None, display_text=None, **_kwargs):
        self.output = output
        self.display_text = display_text

    def set_output(self, output):
        self.output = output


class _FakeTool:
    def __init__(self, name, description, func, schema=None, **kwargs):
        self.name = name
        self.description = description
        self.func = func
        self.schema = schema
        self.kwargs = kwargs


class _Registry:
    def __init__(self):
        self.tools = {}

    def get_tool(self, name):
        return self.tools.get(name)

    def register_tool(self, tool):
        self.tools[tool.name] = tool


class PresentationToolTests(unittest.TestCase):
    def test_encode_decode_round_trip(self):
        encoded = encode_presentation_display(
            {
                "kind": "metric",
                "title": "Build time",
                "subtitle": "Native preview",
                "value": "42 s",
                "detail": "Release build",
            }
        )
        event = decode_presentation_display("meo_present_card", encoded)
        self.assertEqual(event["type"], "presentation_card")
        self.assertEqual(event["card"]["value"], "42 s")

    def test_non_presentation_tool_is_not_promoted(self):
        encoded = encode_presentation_display({"kind": "info", "title": "Hello"})
        self.assertIsNone(decode_presentation_display("other_tool", encoded))
        self.assertIsNone(decode_presentation_display("meo_present_card", "plain text"))

    def test_tool_is_data_only_and_returns_small_model_ack(self):
        adapter = NewellePresentationToolAdapter(_tool_types=(_FakeTool, _FakeToolResult))
        tool = adapter.build_tool()
        self.assertEqual(tool.name, "meo_present_card")
        self.assertFalse(tool.schema["additionalProperties"])
        self.assertEqual(
            tool.schema["properties"]["kind"]["enum"],
            ["info", "status", "metric", "file", "system"],
        )

        result = tool.func(kind="status", title="Tests", value="Passing")
        promoted = decode_presentation_display(tool.name, result.display_text)
        self.assertEqual(promoted["card"]["title"], "Tests")
        self.assertEqual(json.loads(result.output)["presented"], True)

    def test_register_is_idempotent(self):
        adapter = NewellePresentationToolAdapter(_tool_types=(_FakeTool, _FakeToolResult))
        registry = _Registry()
        adapter.register_into(registry)
        adapter.register_into(registry)
        self.assertEqual(list(registry.tools), ["meo_present_card"])


if __name__ == "__main__":
    unittest.main()
