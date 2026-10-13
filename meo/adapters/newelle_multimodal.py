from __future__ import annotations

import base64
from typing import Iterable

from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo


_MAX_IMAGE_COUNT = 8
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


class NewelleMultimodalBridge:
    """Translate AgentService image resources into Newelle's existing image blocks.

    The compatibility layer deliberately does not invent a second provider
    protocol. Newelle handlers already advertise `supports_vision()` and parse
    fenced `image` blocks. This bridge only connects the opaque local resource
    bytes to that established input contract.
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
