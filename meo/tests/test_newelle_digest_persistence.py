from __future__ import annotations

import unittest

from meo.adapters.newelle_multimodal import NewelleMultimodalBridge


class FakeBackend:
    def list_conversations(self):
        return [{"id": "meo:1", "legacy_chat_id": 7}]


class FakeController:
    def __init__(self) -> None:
        self.chats = {
            7: {
                "name": "Chat 8",
                "name_is_default": True,
                "chat": [],
            }
        }
        self.saved = 0
        self.renamed: list[tuple[int, str, bool]] = []

    def rename_chat(self, chat_id: int, name: str, save: bool = True) -> None:
        self.renamed.append((chat_id, name, save))
        self.chats[chat_id]["name"] = name
        self.chats[chat_id].pop("name_is_default", None)
        if save:
            self.save_chats()

    def save_chats(self) -> None:
        self.saved += 1


class NewelleDigestPersistenceTests(unittest.TestCase):
    def test_default_chat_accepts_generated_title_and_summary_and_saves_workspace(self) -> None:
        controller = FakeController()
        bridge = NewelleMultimodalBridge(FakeBackend(), controller)

        self.assertTrue(bridge.conversation_needs_digest("meo:1"))
        bridge.apply_conversation_digest(
            "meo:1",
            title="  Linux   Build Fix  ",
            summary="  Fixed   the build.  ",
        )

        self.assertEqual(controller.chats[7]["name"], "Linux Build Fix")
        self.assertEqual(controller.chats[7]["meo_summary"], "Fixed the build.")
        self.assertEqual(controller.renamed, [(7, "Linux Build Fix", False)])
        self.assertEqual(controller.saved, 1)
        self.assertFalse(bridge.conversation_needs_digest("meo:1"))

        conversation = bridge.list_conversations()[0]
        self.assertEqual(conversation["title"], "Linux Build Fix")
        self.assertEqual(conversation["summary"], "Fixed the build.")
        self.assertFalse(conversation["title_is_default"])
        self.assertFalse(conversation["title_is_automatic"])

    def test_newelle_first_message_title_is_still_eligible_for_ai_replacement(self) -> None:
        controller = FakeController()
        controller.chats[7] = {
            "name": "Fix my Linux build",
            "chat": [{"User": "User", "Message": "Fix my Linux build"}],
        }
        bridge = NewelleMultimodalBridge(FakeBackend(), controller)

        self.assertTrue(bridge.conversation_needs_digest("meo:1"))
        self.assertTrue(bridge.list_conversations()[0]["title_is_automatic"])

        bridge.apply_conversation_digest(
            "meo:1",
            title="Linux Build Fix",
            summary="The user asked for help fixing a Linux build.",
        )

        self.assertEqual(controller.chats[7]["name"], "Linux Build Fix")
        self.assertEqual(controller.renamed, [(7, "Linux Build Fix", False)])
        self.assertEqual(controller.saved, 1)
        self.assertFalse(bridge.conversation_needs_digest("meo:1"))

    def test_newelle_truncated_first_message_title_is_recognized(self) -> None:
        controller = FakeController()
        message = "Please investigate this Linux graphics driver regression and explain every relevant failure"
        controller.chats[7] = {
            "name": "Please investigate this Linux…",
            "chat": [{"User": "User", "Message": message}],
        }
        bridge = NewelleMultimodalBridge(FakeBackend(), controller)

        self.assertTrue(bridge.conversation_needs_digest("meo:1"))

    def test_user_renamed_chat_is_never_overwritten(self) -> None:
        controller = FakeController()
        controller.chats[7] = {
            "name": "My manual title",
            "chat": [{"User": "User", "Message": "Fix my Linux build"}],
        }
        bridge = NewelleMultimodalBridge(FakeBackend(), controller)

        self.assertFalse(bridge.conversation_needs_digest("meo:1"))
        self.assertFalse(bridge.list_conversations()[0]["title_is_automatic"])
        bridge.apply_conversation_digest("meo:1", title="AI title", summary="Useful summary")

        self.assertEqual(controller.chats[7]["name"], "My manual title")
        self.assertEqual(controller.chats[7]["meo_summary"], "Useful summary")
        self.assertEqual(controller.renamed, [])
        self.assertEqual(controller.saved, 1)
        self.assertEqual(bridge.list_conversations()[0]["title"], "My manual title")


if __name__ == "__main__":
    unittest.main()
