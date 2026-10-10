from __future__ import annotations

import unittest

from meo.service.memory import MemoryRecord
from meo.service.search_trace import SearchSource, SearchTrace
from meo.service.sync_contract import SyncContractError, SyncObject, resolve_revision, sanitize_sync_payload


class RuntimeProductContractTests(unittest.TestCase):
    def test_memory_keeps_scope_provenance_and_sync_state(self):
        record = MemoryRecord(
            memory_id="memory:1",
            text="User prefers concise answers.",
            scope="account",
            source="conversation:abc",
            created_at="2026-10-10T03:00:00Z",
            pinned=True,
            sync_state="synced",
        )
        public = record.public_dict()
        self.assertEqual(public["scope"], "account")
        self.assertEqual(public["source"], "conversation:abc")
        self.assertTrue(public["pinned"])
        self.assertEqual(public["sync_state"], "synced")

    def test_search_trace_preserves_queries_sources_and_runtime(self):
        trace = SearchTrace(
            trace_id="search:1",
            kind="web",
            queries=("Meo AI", "Meo AI AgentService"),
            provider="example-search",
            duration_ms=412.5,
            result_count=8,
            sources=(
                SearchSource("source:1", "Result", "https://example.invalid", "example-search", "snippet"),
            ),
            filters={"language": "en"},
        )
        public = trace.public_dict()
        self.assertEqual(public["queries"][1], "Meo AI AgentService")
        self.assertEqual(public["sources"][0]["title"], "Result")
        self.assertEqual(public["duration_ms"], 412.5)
        self.assertEqual(public["result_count"], 8)

    def test_sync_payload_rejects_credentials_instead_of_roaming_them(self):
        with self.assertRaises(SyncContractError):
            sanitize_sync_payload({"provider": "openai", "api_key": "secret"})
        with self.assertRaises(SyncContractError):
            sanitize_sync_payload({"headers": {"Authorization": "Bearer secret"}})

    def test_sync_object_supports_tombstones_and_explicit_revision_conflicts(self):
        local = SyncObject(
            object_id="conversation:1",
            category="conversation",
            revision=3,
            updated_at="2026-10-10T03:00:00Z",
            payload={"title": "Local"},
            device_id="laptop",
        )
        older = SyncObject(
            object_id="conversation:1",
            category="conversation",
            revision=2,
            updated_at="2026-10-10T02:00:00Z",
            payload={"title": "Old"},
            device_id="phone",
        )
        self.assertEqual(resolve_revision(local, older), "use_local")

        same_revision_other_payload = SyncObject(
            object_id="conversation:1",
            category="conversation",
            revision=3,
            updated_at="2026-10-10T03:01:00Z",
            payload={"title": "Remote edit"},
            device_id="phone",
        )
        self.assertEqual(resolve_revision(local, same_revision_other_payload), "conflict")

        tombstone = SyncObject(
            object_id="memory:gone",
            category="memory",
            revision=4,
            updated_at="2026-10-10T03:02:00Z",
            payload={},
            deleted=True,
            state="deleted",
        )
        self.assertTrue(tombstone.public_dict()["deleted"])


if __name__ == "__main__":
    unittest.main()
