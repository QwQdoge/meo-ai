from __future__ import annotations


_PUBLIC_FIELDS = (
    "title",
    "summary",
    "title_is_default",
    "title_is_automatic",
    "created_at",
    "updated_at",
    "message_count",
)


class PublicConversationCatalogBridge:
    """Expose only product-safe conversation metadata outside Newelle.

    The wrapped Newelle adapters may need an internal integer chat ID to map
    Meo conversation IDs back to inherited storage. That identifier is useful
    inside the adapter stack but is not part of the Meo AgentService contract.
    This outer bridge also uses it only as an ordering hint so the most recently
    created Newelle chats appear first, then removes it from the public result.
    """

    def __init__(self, backend) -> None:
        self._backend = backend

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    @staticmethod
    def _creation_order(item: dict) -> int:
        chat_id = item.get("legacy_chat_id")
        if isinstance(chat_id, int) and not isinstance(chat_id, bool):
            return chat_id
        return -1

    def list_conversations(self):
        raw = [item for item in self._backend.list_conversations() if isinstance(item, dict)]
        raw.sort(key=self._creation_order, reverse=True)

        public: list[dict] = []
        for item in raw:
            conversation_id = item.get("id", item.get("conversation_id"))
            if not isinstance(conversation_id, str) or not conversation_id.startswith("meo:"):
                continue
            output = {"id": conversation_id}
            for key in _PUBLIC_FIELDS:
                if key in item:
                    output[key] = item[key]
            public.append(output)
        return public
