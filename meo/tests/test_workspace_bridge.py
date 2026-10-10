from __future__ import annotations

import unittest

from meo.device.workspace_bridge import (
    bind_conversation_workspace,
    ensure_remote_conversation,
    local_conversation_id,
)


class FakeController:
    def __init__(self) -> None:
        self.workspaces = {
            "default": {"path": "/home/user"},
            "workspace-meo-ai": {"path": "/home/user/Projects/meo-ai"},
        }
        self.chats = {1: {"workspace_id": "default"}}
        self.moves: list[tuple[int, str]] = []

    def move_chat_to_workspace(self, chat_id: int, workspace_id: str) -> None:
        if workspace_id not in self.workspaces:
            raise ValueError("Workspace not found")
        self.moves.append((chat_id, workspace_id))
        self.chats[chat_id]["workspace_id"] = workspace_id


class FakeBackend:
    def __init__(self) -> None:
        self.controller = FakeController()
        self._conversations: dict[str, int] = {}
        self.attached: list[str] = []

    def conversation_exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations

    def attach_existing_session(self, conversation_id: str) -> int:
        self.attached.append(conversation_id)
        self._conversations[conversation_id] = 1
        return 1


class WorkspaceBridgeTests(unittest.TestCase):
    def test_cloud_conversation_alias_is_stable_and_not_raw_id(self) -> None:
        first = local_conversation_id("cloud-conversation-123")
        second = local_conversation_id("cloud-conversation-123")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("meo:cloud:"))
        self.assertNotIn("cloud-conversation-123", first)

    def test_remote_conversation_is_attached_once(self) -> None:
        backend = FakeBackend()
        local_id = ensure_remote_conversation(backend, "cloud-conversation-123")
        again = ensure_remote_conversation(backend, "cloud-conversation-123")
        self.assertEqual(local_id, again)
        self.assertEqual(backend.attached, [local_id])

    def test_existing_opaque_workspace_is_bound_locally(self) -> None:
        backend = FakeBackend()
        local_id = ensure_remote_conversation(backend, "cloud-conversation-123")
        bind_conversation_workspace(backend, local_id, "workspace-meo-ai")
        self.assertEqual(
            backend.controller.chats[1]["workspace_id"],
            "workspace-meo-ai",
        )
        self.assertEqual(backend.controller.moves, [(1, "workspace-meo-ai")])

    def test_unknown_or_path_like_workspace_fails_closed(self) -> None:
        backend = FakeBackend()
        local_id = ensure_remote_conversation(backend, "cloud-conversation-123")
        for value in ("missing-workspace", "/home/user/Projects/meo-ai"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    bind_conversation_workspace(backend, local_id, value)


if __name__ == "__main__":
    unittest.main()
