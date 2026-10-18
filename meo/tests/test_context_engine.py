from __future__ import annotations

import unittest

from meo.service.context_engine import (
    BalancedContextStrategy,
    ContextBudget,
    ContextEngine,
    ContextMessage,
    TaskMemoryItem,
    internal_agent_instruction,
    stable_static_prompt,
)
from meo.service.tool_output import ToolOutputCompactor


class ContextEngineTests(unittest.TestCase):
    def test_recent_messages_are_preserved(self):
        engine = ContextEngine()
        messages = [ContextMessage("user", f"old {i} " + "x " * 80, f"m:{i}") for i in range(12)]
        prepared = engine.prepare(
            messages,
            current_message="latest task",
            budget=ContextBudget(total_tokens=700),
        )
        refs = {item.source_ref for item in prepared.messages}
        self.assertIn("m:11", refs)
        self.assertIn("m:10", refs)
        self.assertGreaterEqual(prepared.stats.recent_messages, 2)

    def test_relevant_old_message_beats_irrelevant_old_message(self):
        strategy = BalancedContextStrategy(recent_window=2)
        messages = [
            ContextMessage("user", "database migration uses Neon branch alpha schema", "relevant"),
            ContextMessage("assistant", "weather and lunch ideas " * 30, "noise"),
            ContextMessage("user", "recent short turn", "recent-1"),
            ContextMessage("assistant", "recent reply", "recent-2"),
        ]
        prepared = strategy.prepare(
            messages,
            current_message="continue Neon database migration schema",
            memories=(),
            budget=ContextBudget(total_tokens=90),
        )
        refs = {item.source_ref for item in prepared.messages}
        self.assertIn("relevant", refs)
        self.assertNotIn("noise", refs)

    def test_tool_compaction_keeps_error_and_raw_reference(self):
        compactor = ToolOutputCompactor(max_chars=420)
        raw = "starting\n" + "progress 123456789\n" * 100 + "ERROR: build failed in app.py\n" + "tail\n" * 40
        result = compactor.compact(raw)
        self.assertTrue(result.compacted)
        self.assertIn("ERROR: build failed", result.text)
        self.assertIn(result.raw_ref, result.text)
        self.assertEqual(raw.count("ERROR"), 1)  # raw input was never changed
        self.assertLess(result.compact_chars, result.raw_chars)

    def test_old_tool_output_is_compacted_in_context(self):
        strategy = BalancedContextStrategy(recent_window=2)
        raw = "compile\n" + ("noise\n" * 800) + "fatal: linker failed\n"
        messages = [
            ContextMessage("tool", raw, "tool:raw", kind="tool", pinned=True),
            ContextMessage("assistant", "older answer", "old"),
            ContextMessage("user", "fix linker", "new-user"),
            ContextMessage("assistant", "working", "new-assistant"),
        ]
        prepared = strategy.prepare(
            messages,
            current_message="fix linker failure",
            memories=(),
            budget=ContextBudget(total_tokens=900),
        )
        tool = next(item for item in prepared.messages if item.source_ref == "tool:raw")
        self.assertIn("fatal: linker failed", tool.text)
        self.assertGreaterEqual(prepared.stats.compacted_tool_outputs, 1)

    def test_structured_memory_is_budgeted(self):
        engine = ContextEngine()
        prepared = engine.prepare(
            [ContextMessage("user", "continue release", "recent")],
            current_message="release branch",
            memories=[
                TaskMemoryItem("Release must stay on branch beta", "constraint", "memory:1", pinned=True),
                TaskMemoryItem("irrelevant old preference " * 100, "fact", "memory:2"),
            ],
            budget=ContextBudget(total_tokens=120),
        )
        self.assertTrue(any(item.source_ref == "memory:1" for item in prepared.memories))
        self.assertGreaterEqual(prepared.stats.memory_items, 1)

    def test_low_confidence_fallback_is_reported(self):
        strategy = BalancedContextStrategy(recent_window=2, min_confidence=0.95)
        messages = [
            ContextMessage("assistant", "unrelated alpha", "old-1"),
            ContextMessage("assistant", "unrelated beta", "old-2"),
            ContextMessage("user", "new one", "new-1"),
            ContextMessage("assistant", "new two", "new-2"),
        ]
        prepared = strategy.prepare(
            messages,
            current_message="completely different topic",
            memories=(),
            budget=ContextBudget(total_tokens=500),
        )
        self.assertTrue(prepared.stats.fallback_used)
        self.assertEqual(prepared.stats.fallback_reason, "low_relevance_confidence")

    def test_internal_terse_mode_never_applies_to_final_answer(self):
        self.assertTrue(internal_agent_instruction(terse=True, final_user_response=False))
        self.assertEqual(internal_agent_instruction(terse=True, final_user_response=True), "")
        self.assertEqual(internal_agent_instruction(terse=False, final_user_response=False), "")

    def test_static_prompt_serialization_is_deterministic(self):
        parts = ["  system rules  ", "tool schema", ""]
        self.assertEqual(stable_static_prompt(parts), stable_static_prompt(parts))
        self.assertEqual(stable_static_prompt(parts), "system rules\n\ntool schema")

    def test_stats_do_not_expose_message_contents(self):
        engine = ContextEngine()
        secret_marker = "private-hidden-marker"
        prepared = engine.prepare(
            [ContextMessage("user", secret_marker, "m:1")],
            current_message="x",
            budget=ContextBudget(total_tokens=100),
        )
        self.assertNotIn(secret_marker, repr(prepared.stats.public_dict()))


if __name__ == "__main__":
    unittest.main()
