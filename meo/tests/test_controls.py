from __future__ import annotations

import unittest

from meo.service.controls import AiControl, ControlOption, find_control


class ControlContractTests(unittest.TestCase):
    def test_toggle_is_small_frontend_safe_contract(self):
        control = AiControl(
            "memory.enabled",
            "Memory",
            "toggle",
            True,
            description="Use long-term memory when available.",
        )
        self.assertEqual(
            control.public_dict(),
            {
                "control_id": "memory.enabled",
                "label": "Memory",
                "kind": "toggle",
                "value": True,
                "description": "Use long-term memory when available.",
                "scope": "profile",
                "writable": True,
                "restart_required": False,
            },
        )
        self.assertFalse(control.validate_value(False))
        with self.assertRaisesRegex(ValueError, "boolean"):
            control.validate_value("false")

    def test_integer_range_is_enforced(self):
        control = AiControl(
            "tools.max_calls",
            "Maximum tool calls",
            "integer",
            20,
            minimum=1,
            maximum=100,
            step=1,
        )
        self.assertEqual(control.validate_value(50), 50)
        with self.assertRaisesRegex(ValueError, "below minimum"):
            control.validate_value(0)
        with self.assertRaisesRegex(ValueError, "above maximum"):
            control.validate_value(101)

    def test_select_only_accepts_provider_supported_values(self):
        control = AiControl(
            "model.thinking_effort",
            "Thinking effort",
            "select",
            "medium",
            options=(
                ControlOption("low", "Low"),
                ControlOption("medium", "Medium"),
                ControlOption("high", "High"),
            ),
        )
        self.assertEqual(control.validate_value("high"), "high")
        self.assertEqual(control.public_dict()["options"][2]["label"], "High")
        with self.assertRaisesRegex(ValueError, "not supported"):
            control.validate_value("extreme")

    def test_readonly_control_cannot_be_mutated(self):
        control = AiControl("sync.status", "Cloud sync", "readonly", "not configured", writable=False)
        with self.assertRaisesRegex(ValueError, "read-only"):
            control.validate_value("ready")

    def test_find_control_rejects_unknown_identity(self):
        controls = [AiControl("search.enabled", "Web search", "toggle", False)]
        self.assertEqual(find_control(controls, "search.enabled").label, "Web search")
        with self.assertRaisesRegex(ValueError, "unknown control_id"):
            find_control(controls, "missing")


if __name__ == "__main__":
    unittest.main()
