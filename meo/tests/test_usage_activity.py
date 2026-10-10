from __future__ import annotations

import json
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

    def test_unchanged_claude_history_is_not_reparsed_after_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "claude" / "projects" / "project"
            root.mkdir(parents=True)
            transcript = root / "session.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/tmp/meo-ai",
                        "timestamp": "2026-10-10T10:00:00Z",
                        "message": {
                            "id": "message-1",
                            "model": "claude-test",
                            "usage": {"input_tokens": 10, "output_tokens": 20},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            db_path = Path(directory) / "usage.db"

            first = UsageCollector(db_path)
            try:
                self.assertEqual(first.import_claude_code(root.parent), 1)
                first.db.commit()
            finally:
                first.close()

            second = UsageCollector(db_path)
            try:
                self.assertEqual(second.import_claude_code(root.parent), 0)
                self.assertEqual(len(second.cloud_rows()), 1)
            finally:
                second.close()

    def test_growing_claude_history_is_reimported_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "projects" / "project"
            root.mkdir(parents=True)
            transcript = root / "session.jsonl"
            first_row = {
                "type": "assistant",
                "sessionId": "session-1",
                "cwd": "/tmp/meo-ai",
                "timestamp": "2026-10-10T10:00:00Z",
                "message": {
                    "id": "message-1",
                    "model": "claude-test",
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                },
            }
            second_row = {
                "type": "assistant",
                "sessionId": "session-1",
                "cwd": "/tmp/meo-ai",
                "timestamp": "2026-10-10T10:01:00Z",
                "message": {
                    "id": "message-2",
                    "model": "claude-test",
                    "usage": {"input_tokens": 30, "output_tokens": 40},
                },
            }
            transcript.write_text(json.dumps(first_row) + "\n", encoding="utf-8")

            collector = UsageCollector(Path(directory) / "usage.db")
            try:
                self.assertEqual(collector.import_claude_code(Path(directory) / "projects"), 1)
                collector.db.commit()
                with transcript.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(second_row) + "\n")
                # The active file changed, so it is reparsed. Existing event IDs
                # are upserted and only two durable usage rows remain.
                self.assertEqual(collector.import_claude_code(Path(directory) / "projects"), 2)
                collector.db.commit()
                rows = collector.cloud_rows()
            finally:
                collector.close()

        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["input_tokens"] for row in rows), 40)
        self.assertEqual(sum(row["output_tokens"] for row in rows), 60)

    def test_import_bookkeeping_paths_never_enter_cloud_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "projects" / "private-project"
            root.mkdir(parents=True)
            transcript = root / "secret-location.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/home/user/private/work",
                        "timestamp": "2026-10-10T10:00:00Z",
                        "message": {
                            "id": "message-1",
                            "model": "claude-test",
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            collector = UsageCollector(Path(directory) / "usage.db")
            try:
                collector.import_claude_code(Path(directory) / "projects")
                rows = collector.cloud_rows()
            finally:
                collector.close()

        self.assertEqual(len(rows), 1)
        self.assertNotIn(str(root), json.dumps(rows))
        self.assertNotIn("/home/user/private/work", json.dumps(rows))
        self.assertEqual(rows[0]["project_name"], "work")


if __name__ == "__main__":
    unittest.main()
