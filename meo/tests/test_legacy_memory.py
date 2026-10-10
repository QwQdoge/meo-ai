from __future__ import annotations

from dataclasses import dataclass
import time
import unittest

from meo.adapters.legacy_memory import LegacyMemoryBridge


@dataclass
class FakeStoredMemory:
    id: str
    kind: str
    scope: str
    text: str
    created_at: float
    updated_at: float
    importance: float = 0.5
    pinned: bool = False
    source: str = "assistant"
    archived: bool = False


class FakeStore:
    def __init__(self):
        now = time.time()
        self.records = {
            "one": FakeStoredMemory("one", "fact", "shared", "User likes concise UI.", now, now),
            "two": FakeStoredMemory("two", "fact", "other", "Other scope", now, now),
        }

    def list_records(self, scope, *, kind=None, archived=False):
        del kind
        values = [record for record in self.records.values() if record.scope == scope]
        if archived is None:
            return values
        return [record for record in values if record.archived is archived]

    def get(self, memory_id):
        return self.records.get(memory_id)

    def add(self, kind, scope, text, *, importance=0.5, pinned=False, source="assistant"):
        now = time.time()
        record = FakeStoredMemory("created", kind, scope, text, now, now, importance, pinned, source)
        self.records[record.id] = record
        return record

    def update_text(self, memory_id, text):
        record = self.records[memory_id]
        record.text = text
        record.updated_at = time.time()
        return record

    def set_pinned(self, memory_id, pinned):
        self.records[memory_id].pinned = pinned

    def delete(self, memory_id):
        self.records.pop(memory_id, None)


class FakeMemoryHandler:
    def __init__(self):
        self.store = FakeStore()
        self.notifications = 0

    def get_scope(self):
        return "shared"

    def _notify(self):
        self.notifications += 1


class FakeSettings:
    def __init__(self):
        self.enabled = True

    def get_boolean(self, key):
        if key != "memory-on": raise KeyError(key)
        return self.enabled

    def set_boolean(self, key, value):
        if key != "memory-on": raise KeyError(key)
        self.enabled = bool(value)


class FakeController:
    def __init__(self):
        self.settings = FakeSettings()
        self.handlers = type("Handlers", (), {"memory": FakeMemoryHandler()})()


class LegacyMemoryBridgeTests(unittest.TestCase):
    def test_lists_only_current_scope_and_searches_text(self):
        bridge = LegacyMemoryBridge(FakeController())
        records = bridge.list_memories(query="concise")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].memory_id, "memory:one")
        self.assertEqual(records[0].scope, "account")
        self.assertIn("scope=shared", records[0].source)

    def test_toggle_create_update_pin_and_delete_use_store_authority(self):
        controller = FakeController()
        bridge = LegacyMemoryBridge(controller)
        self.assertTrue(bridge.memory_enabled())
        self.assertFalse(bridge.set_memory_enabled(False))

        created = bridge.create_memory("Remember this", pinned=True)
        self.assertEqual(created.memory_id, "memory:created")
        self.assertTrue(created.pinned)
        self.assertIn("source=user", created.source)

        updated = bridge.update_memory("memory:created", text="Remember updated", pinned=False)
        self.assertEqual(updated.text, "Remember updated")
        self.assertFalse(updated.pinned)
        bridge.delete_memory("memory:created")
        self.assertNotIn("created", controller.handlers.memory.store.records)
        self.assertEqual(controller.handlers.memory.notifications, 3)

    def test_cross_scope_memory_id_is_rejected(self):
        bridge = LegacyMemoryBridge(FakeController())
        with self.assertRaisesRegex(ValueError, "unknown memory_id"):
            bridge.update_memory("memory:two", pinned=True)

    def test_noninspectable_provider_fails_closed_for_mutation(self):
        controller = FakeController()
        controller.handlers.memory = object()
        bridge = LegacyMemoryBridge(controller)
        self.assertFalse(bridge.supported())
        self.assertEqual(bridge.list_memories(), [])
        with self.assertRaisesRegex(ValueError, "not inspectable"):
            bridge.create_memory("x")


if __name__ == "__main__":
    unittest.main()
