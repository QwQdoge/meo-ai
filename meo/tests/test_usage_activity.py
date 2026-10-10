from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meo.usage.collector import UsageCollector, UsageEvent


class UsageActivityTests(unittest.TestCase):
    def test_cloud_rows_export_only_normalized_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            collector = UsageCollector(Path(directory) / "usage.db")
            try:
                collector.upsert(
                    UsageEvent(
                        source="codex",
                        source_event_id="session-1:1",
                        session_id="session-1",
                        project_key="abc123",
                        project_name="meo-ai",
                        provider="OpenAI",
                        model="gpt-test",
                        model_role="execution",
                        occurred_at="2026-10-10T10:00:00+00:00",
                        input_tokens=100,
                        cached_input_tokens=20,
                        output_tokens=30,
                        reasoning_tokens=10,
                        metadata={"source_file": "rollout.jsonl"},
                    )
                )
                rows = collector.cloud_rows()
            finally:
                collector.close()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "codex")
        self.assertEqual(row["project_name"], "meo-ai")
        self.assertEqual(row["input_tokens"], 100)
        self.assertNotIn("user_id", row)
        self.assertNotIn("total_tokens", row)
        self.assertEqual(row["metadata"], {"source_file": "rollout.jsonl"})

    def test_dashboard_totals_match_normalized_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            collector = UsageCollector(Path(directory) / "usage.db")
            try:
                collector.upsert(
                    UsageEvent(
                        source="claude_code",
                        source_event_id="message-1",
                        session_id="session-1",
                        project_key="project",
                        project_name="Project",
                        provider="Anthropic",
                        model="claude-test",
                        model_role="execution",
                        occurred_at="2026-10-10T10:00:00+00:00",
                        input_tokens=10,
                        cached_input_tokens=20,
                        cache_write_tokens=30,
                        output_tokens=40,
                    )
                )
                dashboard = collector.dashboard()
            finally:
                collector.close()

        self.assertEqual(dashboard["summary"]["lifetime_tokens"], 100)
        self.assertEqual(dashboard["token_breakdown"]["input"], 10)
        self.assertEqual(dashboard["token_breakdown"]["cached_input"], 20)
        self.assertEqual(dashboard["token_breakdown"]["cache_write"], 30)
        self.assertEqual(dashboard["token_breakdown"]["output"], 40)


if __name__ == "__main__":
    unittest.main()
