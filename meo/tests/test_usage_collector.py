from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meo.usage.collector import UsageCollector


class UsageCollectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.collector = UsageCollector(self.root / "usage.db")

    def tearDown(self) -> None:
        self.collector.close()
        self.temp.cleanup()

    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_codex_uses_incremental_last_usage_without_double_counting(self) -> None:
        path = self.root / "codex" / "sessions" / "2026" / "10" / "10" / "rollout-test.jsonl"
        self.write_jsonl(
            path,
            [
                {"type": "session_meta", "payload": {"id": "s1", "cwd": "/work/meo-ai", "model_provider": "OpenAI"}},
                {"type": "turn_context", "payload": {"model": "gpt-5.6-codex"}},
                {
                    "timestamp": "2026-10-10T01:00:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 1000,
                                "cached_input_tokens": 400,
                                "output_tokens": 300,
                                "reasoning_output_tokens": 100,
                            },
                            "total_token_usage": {
                                "input_tokens": 1000,
                                "cached_input_tokens": 400,
                                "output_tokens": 300,
                                "reasoning_output_tokens": 100,
                            },
                        },
                    },
                },
            ],
        )
        self.assertEqual(self.collector.import_codex(self.root / "codex"), 1)
        dashboard = self.collector.dashboard()
        self.assertEqual(dashboard["summary"]["lifetime_tokens"], 1300)
        self.assertEqual(dashboard["token_breakdown"]["input"], 600)
        self.assertEqual(dashboard["token_breakdown"]["cached_input"], 400)
        self.assertEqual(dashboard["token_breakdown"]["output"], 200)
        self.assertEqual(dashboard["token_breakdown"]["reasoning"], 100)
        self.assertEqual(dashboard["projects"][0]["name"], "meo-ai")

    def test_claude_code_deduplicates_streamed_message_usage(self) -> None:
        path = self.root / "claude" / "projects" / "demo" / "session.jsonl"
        base = {
            "type": "assistant",
            "sessionId": "claude-session",
            "requestId": "request-1",
            "cwd": "/work/meo-ai",
            "timestamp": "2026-10-10T02:00:00Z",
        }
        self.write_jsonl(
            path,
            [
                {
                    **base,
                    "message": {"id": "msg-1", "model": "claude-sonnet", "usage": {"input_tokens": 50, "output_tokens": 5}},
                },
                {
                    **base,
                    "message": {
                        "id": "msg-1",
                        "model": "claude-sonnet",
                        "usage": {
                            "input_tokens": 50,
                            "cache_read_input_tokens": 100,
                            "cache_creation_input_tokens": 20,
                            "output_tokens": 30,
                        },
                    },
                },
            ],
        )
        self.assertEqual(self.collector.import_claude_code(self.root / "claude" / "projects"), 1)
        dashboard = self.collector.dashboard()
        self.assertEqual(dashboard["summary"]["lifetime_tokens"], 200)
        self.assertEqual(dashboard["models"][0]["name"], "claude-sonnet")
        self.assertEqual(dashboard["sources"][0]["events"], 1)


if __name__ == "__main__":
    unittest.main()
