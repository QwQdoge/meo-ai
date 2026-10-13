from __future__ import annotations

import base64
import json
from typing import Iterable

from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo


_MAX_IMAGE_COUNT = 8
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


class NewelleMultimodalBridge:
    """Translate AgentService resources and auxiliary calls into Newelle APIs.

    The compatibility layer deliberately does not invent a second provider
    protocol. Newelle handlers already advertise `supports_vision()`, parse
    fenced `image` blocks, and expose history-free `generate_text()` calls.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controller = controller

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def _provider_supports_vision(self, provider_name: str) -> bool:
        from src.constants import AVAILABLE_LLMS

        provider = AVAILABLE_LLMS.get(provider_name)
        if not isinstance(provider, dict):
            return False
        handler_class = provider.get("class")
        if not callable(handler_class):
            return False
        handlers = getattr(self._controller, "handlers", None)
        directory = getattr(handlers, "directory", None)
        try:
            handler = handler_class(self._controller.settings, directory)
            supported = getattr(handler, "supports_vision", None)
            return bool(supported()) if callable(supported) else False
        except Exception:
            return False

    def list_models(self) -> list[ModelInfo]:
        raw = list(self._backend.list_models())
        providers = {
            item.model_id.split(":", 1)[0]
            for item in raw
            if isinstance(item.model_id, str) and ":" in item.model_id
        }
        capabilities = {
            provider: self._provider_supports_vision(provider)
            for provider in providers
        }
        return [
            ModelInfo(
                item.model_id,
                item.label,
                item.provider,
                selection_scope=item.selection_scope,
                selected=item.selected,
                supports_vision=(
                    item.supports_vision
                    or capabilities.get(item.model_id.split(":", 1)[0], False)
                ),
            )
            for item in raw
        ]

    def generate_auxiliary(
        self,
        model_id: str,
        prompt: str,
        system_prompt: list[str] | None = None,
    ) -> str:
        """Run a provider model without adding verifier prompts to chat history.

        RoutedBackend serializes legacy requests, so temporarily changing the
        provider's model setting here cannot cross-contaminate another routed
        request. The exact settings JSON is restored in `finally`.
        """
        from src.constants import AVAILABLE_LLMS

        if not isinstance(model_id, str) or ":" not in model_id:
            raise ValueError("auxiliary model_id must include provider:model")
        provider_name, raw_model_id = model_id.split(":", 1)
        provider = AVAILABLE_LLMS.get(provider_name)
        if not isinstance(provider, dict) or not raw_model_id:
            raise ValueError(f"unknown auxiliary model: {model_id}")
        if model_id not in {item.model_id for item in self.list_models()}:
            raise ValueError(f"auxiliary model is not available: {model_id}")
        handler_class = provider.get("class")
        if not callable(handler_class):
            raise ValueError(f"provider has no LLM handler: {provider_name}")

        settings = self._controller.settings
        previous_raw = settings.get_string("llm-settings")
        try:
            payload = json.loads(previous_raw)
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            payload = {}
        provider_settings = payload.get(provider_name)
        if not isinstance(provider_settings, dict):
            provider_settings = {}
        else:
            provider_settings = dict(provider_settings)
        provider_settings["model"] = raw_model_id
        payload[provider_name] = provider_settings

        handlers = getattr(self._controller, "handlers", None)
        directory = getattr(handlers, "directory", None)
        try:
            settings.set_string("llm-settings", json.dumps(payload))
            handler = handler_class(settings, directory)
            result = handler.generate_text(prompt, [], list(system_prompt or []))
            if not isinstance(result, str):
                raise ValueError("auxiliary model returned a non-text response")
            return result
        finally:
            settings.set_string("llm-settings", previous_raw)

    def _conversation_chat_id(self, conversation_id: str) -> int | None:
        try:
            conversations = self._backend.list_conversations()
        except Exception:
            return None
        for item in conversations:
            if not isinstance(item, dict) or item.get("id") != conversation_id:
                continue
            chat_id = item.get("legacy_chat_id")
            return chat_id if isinstance(chat_id, int) else None
        return None

    def _conversation_record(self, conversation_id: str) -> tuple[int, dict] | None:
        chat_id = self._conversation_chat_id(conversation_id)
        if chat_id is None:
            return None
        chats = getattr(self._controller, "chats", None)
        record = chats.get(chat_id) if isinstance(chats, dict) else None
        if not isinstance(record, dict):
            return None
        return chat_id, record

    def conversation_needs_digest(self, conversation_id: str) -> bool:
        target = self._conversation_record(conversation_id)
        if target is None:
            return False
        _chat_id, record = target
        return record.get("name_is_default") is True

    def apply_conversation_digest(self, conversation_id: str, *, title: str, summary: str = "") -> None:
        """Persist generated metadata without overwriting a user-renamed chat."""
        target = self._conversation_record(conversation_id)
        if target is None:
            raise ValueError("unknown conversation_id")
        chat_id, record = target
        title = " ".join(str(title or "").split()).strip()
        summary = " ".join(str(summary or "").split()).strip()
        if not title:
            raise ValueError("generated conversation title is empty")

        if record.get("name_is_default") is True:
            rename = getattr(self._controller, "rename_chat", None)
            if callable(rename):
                try:
                    rename(chat_id, title, save=False)
                except TypeError:
                    rename(chat_id, title)
            else:
                record["name"] = title
                record.pop("name_is_default", None)
        if summary:
            record["meo_summary"] = summary

        save = getattr(self._controller, "save_chat", None)
        if callable(save):
            try:
                save(chat_id)
            except TypeError:
                save()

    def _selected_supports_vision(self) -> bool:
        return any(item.selected and item.supports_vision for item in self.list_models())

    @staticmethod
    def _is_image(resource: InputResource) -> bool:
        base_mime = resource.mime_type.split(";", 1)[0].strip().casefold()
        return resource.kind == "image" or base_mime.startswith("image/")

    @staticmethod
    def _image_block(resource: InputResource) -> str:
        base_mime = resource.mime_type.split(";", 1)[0].strip().casefold()
        if not base_mime.startswith("image/"):
            raise ValueError(f"image resource has invalid MIME type: {resource.mime_type or resource.kind}")
        if not resource.data:
            raise ValueError(f"image resource is empty: {resource.name}")
        payload = base64.b64encode(resource.data).decode("ascii")
        name = " ".join((resource.name or "Attached image").split())[:240]
        return f"Attached image: {name}\n```image\ndata:{base_mime};base64,{payload}\n```"

    def send_message_with_resources(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ):
        images = tuple(resource for resource in resources if self._is_image(resource))
        if not images:
            method = getattr(self._backend, "send_message_with_resources", None)
            if not callable(method):
                raise ValueError("selected backend does not support resource inputs")
            return method(conversation_id, text, resources, callbacks)

        if len(images) > _MAX_IMAGE_COUNT:
            raise ValueError(f"at most {_MAX_IMAGE_COUNT} images can be sent in one request")
        image_bytes = sum(len(resource.data) for resource in images)
        if image_bytes > _MAX_IMAGE_BYTES:
            raise ValueError("combined image input exceeds 20 MiB")
        if not self._selected_supports_vision():
            raise ValueError("selected model does not support vision inputs")

        image_context = "\n\n".join(self._image_block(resource) for resource in images)
        bridged_text = f"{image_context}\n\n{text}" if text else image_context
        remaining = tuple(resource for resource in resources if not self._is_image(resource))
        if remaining:
            method = getattr(self._backend, "send_message_with_resources", None)
            if not callable(method):
                raise ValueError("selected backend does not support non-image resource inputs")
            return method(conversation_id, bridged_text, remaining, callbacks)
        return self._backend.send_message(conversation_id, bridged_text, callbacks)
