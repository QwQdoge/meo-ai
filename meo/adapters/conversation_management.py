from __future__ import annotations


class ConversationManagementBridge:
    """Newelle-backed conversation lifecycle without exposing legacy chat IDs.

    AgentService conversation IDs remain the public identity. This bridge owns
    the one deliberate translation into Newelle's integer chat storage so the
    native product does not need to know or persist legacy IDs.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controller = controller

    def _legacy_chat_id(self, conversation_id: str) -> int:
        for item in self._backend.list_conversations():
            if not isinstance(item, dict) or item.get("id") != conversation_id:
                continue
            chat_id = item.get("legacy_chat_id")
            if isinstance(chat_id, int) and not isinstance(chat_id, bool):
                return chat_id
        raise ValueError("unknown conversation_id")

    def _save(self) -> None:
        save = getattr(self._controller, "save_chats", None)
        if callable(save):
            save()

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        title = " ".join(str(title or "").split()).strip()
        if not title:
            raise ValueError("conversation title is required")
        if len(title) > 240:
            raise ValueError("conversation title is too long")

        chat_id = self._legacy_chat_id(conversation_id)
        chats = getattr(self._controller, "chats", None)
        if not isinstance(chats, dict) or chat_id not in chats:
            raise ValueError("unknown conversation_id")

        rename = getattr(self._controller, "rename_chat", None)
        if callable(rename):
            try:
                rename(chat_id, title, save=False)
            except TypeError:
                rename(chat_id, title)
        else:
            chats[chat_id]["name"] = title
            chats[chat_id].pop("name_is_default", None)

        # A manual title must win over later automatic digest generation.
        chats[chat_id]["meo_title_user_set"] = True
        self._save()

    def delete_conversation(self, conversation_id: str) -> None:
        chat_id = self._legacy_chat_id(conversation_id)
        chats = getattr(self._controller, "chats", None)
        if not isinstance(chats, dict) or chat_id not in chats:
            raise ValueError("unknown conversation_id")

        folders = getattr(self._controller, "folders", None)
        if isinstance(folders, dict):
            for folder in folders.values():
                if not isinstance(folder, dict):
                    continue
                chat_ids = folder.get("chat_ids")
                if isinstance(chat_ids, list):
                    folder["chat_ids"] = [item for item in chat_ids if item != chat_id]

        del chats[chat_id]

        current_settings = getattr(self._controller, "newelle_settings", None)
        if getattr(current_settings, "chat_id", None) == chat_id:
            fallback = None
            resolver = getattr(self._controller, "_get_fallback_chat_id", None)
            if callable(resolver):
                fallback = resolver()
            if fallback is None:
                create = getattr(self._controller, "create_visible_chat", None)
                if callable(create):
                    fallback = create()
            if isinstance(fallback, int) and not isinstance(fallback, bool):
                current_settings.chat_id = fallback
                settings = getattr(self._controller, "settings", None)
                setter = getattr(settings, "set_int", None)
                if callable(setter):
                    setter("chat", fallback)

        hydrate = getattr(self._backend, "_hydrate_conversations", None)
        if callable(hydrate):
            hydrate()
        self._save()

        ui = getattr(self._controller, "ui_controller", None)
        update_history = getattr(ui, "update_history", None)
        if callable(update_history):
            update_history()
