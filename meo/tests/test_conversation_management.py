import types
import unittest

from meo.adapters.conversation_management import ConversationManagementBridge


class FakeSettings:
    def __init__(self):
        self.values = {}

    def set_int(self, key, value):
        self.values[key] = value


class FakeController:
    def __init__(self):
        self.chats = {
            1: {"name": "First", "chat": [], "workspace_id": "default"},
            2: {"name": "Second", "chat": [], "workspace_id": "default"},
        }
        self.folders = {
            7: {"name": "Folder", "chat_ids": [1, 2], "workspace_id": "default"},
        }
        self.newelle_settings = types.SimpleNamespace(chat_id=1)
        self.settings = FakeSettings()
        self.ui_controller = types.SimpleNamespace(update_history=lambda: None)
        self.save_count = 0
        self.next_chat_id = 3

    def rename_chat(self, chat_id, title, save=True):
        self.chats[chat_id]["name"] = title
        self.chats[chat_id].pop("name_is_default", None)
        if save:
            self.save_chats()

    def _get_fallback_chat_id(self):
        visible = [chat_id for chat_id, chat in self.chats.items() if not chat.get("call")]
        return min(visible) if visible else None

    def create_visible_chat(self):
        chat_id = self.next_chat_id
        self.next_chat_id += 1
        self.chats[chat_id] = {"name": f"Chat {chat_id}", "chat": [], "workspace_id": "default"}
        self.save_chats()
        return chat_id

    def save_chats(self):
        self.save_count += 1


class FakeBackend:
    def __init__(self, controller):
        self.controller = controller
        self.mapping = {"meo:first": 1, "meo:second": 2}

    def list_conversations(self):
        return [
            {"id": conversation_id, "legacy_chat_id": chat_id}
            for conversation_id, chat_id in sorted(self.mapping.items())
            if chat_id in self.controller.chats
        ]

    def _hydrate_conversations(self):
        self.mapping = {
            conversation_id: chat_id
            for conversation_id, chat_id in self.mapping.items()
            if chat_id in self.controller.chats
        }


class ConversationManagementBridgeTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.backend = FakeBackend(self.controller)
        self.bridge = ConversationManagementBridge(self.backend, self.controller)

    def test_rename_uses_public_conversation_id_and_marks_manual_title(self):
        self.bridge.rename_conversation("meo:first", "  Product   review  ")
        self.assertEqual(self.controller.chats[1]["name"], "Product review")
        self.assertTrue(self.controller.chats[1]["meo_title_user_set"])
        self.assertEqual(self.controller.save_count, 1)

    def test_delete_removes_folder_reference_and_selects_fallback(self):
        self.bridge.delete_conversation("meo:first")
        self.assertNotIn(1, self.controller.chats)
        self.assertEqual(self.controller.folders[7]["chat_ids"], [2])
        self.assertEqual(self.controller.newelle_settings.chat_id, 2)
        self.assertEqual(self.controller.settings.values["chat"], 2)
        self.assertNotIn("meo:first", self.backend.mapping)
        self.assertEqual(self.controller.save_count, 1)

    def test_delete_last_chat_creates_safe_newelle_fallback(self):
        del self.controller.chats[2]
        self.backend.mapping = {"meo:first": 1}
        self.controller.folders[7]["chat_ids"] = [1]
        self.bridge.delete_conversation("meo:first")
        self.assertEqual(self.controller.newelle_settings.chat_id, 3)
        self.assertIn(3, self.controller.chats)
        self.assertEqual(self.controller.settings.values["chat"], 3)
        self.assertGreaterEqual(self.controller.save_count, 1)

    def test_unknown_conversation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown conversation_id"):
            self.bridge.rename_conversation("meo:missing", "Missing")
        with self.assertRaisesRegex(ValueError, "unknown conversation_id"):
            self.bridge.delete_conversation("meo:missing")


if __name__ == "__main__":
    unittest.main()
