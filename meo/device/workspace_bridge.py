from __future__ import annotations

import hashlib


def local_conversation_id(cloud_conversation_id: str) -> str:
    value = str(cloud_conversation_id).strip()
    if not value:
        raise ValueError("cloud conversation_id is required")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"meo:cloud:{digest}"


def ensure_remote_conversation(backend, cloud_conversation_id: str) -> str:
    """Return one deterministic local conversation for a cloud conversation.

    The current Newelle compatibility adapter exposes `attach_existing_session`.
    A future native agent core can implement the same small seam without keeping
    the legacy chat internals.
    """

    local_id = local_conversation_id(cloud_conversation_id)
    if backend.conversation_exists(local_id):
        return local_id

    attach = getattr(backend, "attach_existing_session", None)
    if not callable(attach):
        raise RuntimeError("Agent backend cannot attach a remote conversation")
    attach(local_id)
    if not backend.conversation_exists(local_id):
        raise RuntimeError("Agent backend did not persist the remote conversation")
    return local_id


def bind_conversation_workspace(backend, conversation_id: str, workspace_ref: str) -> None:
    """Bind a local conversation to an existing opaque Newelle workspace ID.

    `workspace_ref` is never interpreted as a filesystem path. It must already
    exist in the local controller's workspace registry. Cloud state therefore
    cannot invent an arbitrary directory path.
    """

    workspace_ref = str(workspace_ref).strip()
    if not workspace_ref:
        raise ValueError("workspace_ref is required")

    controller = getattr(backend, "controller", None)
    workspaces = getattr(controller, "workspaces", None)
    if not isinstance(workspaces, dict) or workspace_ref not in workspaces:
        raise ValueError("unknown local workspace_ref")

    conversations = getattr(backend, "_conversations", None)
    if not isinstance(conversations, dict):
        raise RuntimeError("Agent backend does not expose conversation membership")
    chat_id = conversations.get(conversation_id)
    if chat_id is None:
        raise ValueError("local conversation is not attached")

    chats = getattr(controller, "chats", None)
    if not isinstance(chats, dict) or chat_id not in chats:
        raise RuntimeError("local conversation chat record is unavailable")
    current_workspace = chats[chat_id].get("workspace_id", "default")
    if current_workspace == workspace_ref:
        return

    move = getattr(controller, "move_chat_to_workspace", None)
    if not callable(move):
        raise RuntimeError("Agent backend cannot bind a conversation to a workspace")
    move(chat_id, workspace_ref)

    updated = chats.get(chat_id, {}).get("workspace_id", "default")
    if updated != workspace_ref:
        raise RuntimeError("Agent backend did not persist workspace membership")
