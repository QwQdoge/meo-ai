from __future__ import annotations

import threading
from typing import Any, Callable

from meo.adapters.account_multimodal import context_payload
from meo.system.account_ai import AccountAiUnavailable, DbusNextAccountAiClient
from meo.system.account_ai_interaction import request_account_ai_consent
from src.handlers.llm.llm import LLMHandler


_client_lock = threading.Lock()
_client: DbusNextAccountAiClient | None = None


def account_ai_client() -> DbusNextAccountAiClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = DbusNextAccountAiClient()
        return _client


class MeoAccountLLMHandler(LLMHandler):
    """LLM handler whose provider request is owned by Meo Account.

    The handler receives only connection metadata, prompt text and the final
    brokered response. Provider credentials never enter Newelle or AgentService.
    Every inference is prepared by the Account broker and must resolve through
    the native AgentService interaction bridge before it is invoked.
    """

    key = "meo_account"

    def get_models_list(self):
        try:
            connections = account_ai_client().list_connections()
        except Exception:
            return tuple()

        selected = self.get_setting("model", search_default=False, return_value="")
        selected = selected if isinstance(selected, str) else ""
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()
        known_connections: dict[str, str] = {}

        for connection in connections:
            connection_id = str(connection.get("id") or "").strip()
            if not connection_id:
                continue
            name = str(connection.get("displayName") or connection.get("provider") or "Meo Account").strip()
            known_connections[connection_id] = name
            model = str(connection.get("defaultModel") or "").strip()
            if not model:
                continue
            raw_id = f"{connection_id}:{model}"
            if raw_id in seen:
                continue
            seen.add(raw_id)
            choices.append((raw_id, f"{name} · {model}"))

        # A model discovered in the native Settings Center may not be the
        # connection's default model. Keep the active explicit selection visible
        # without asking Account to persist Meo AI's per-conversation choice.
        if selected and ":" in selected and selected not in seen:
            connection_id, model = selected.split(":", 1)
            name = known_connections.get(connection_id)
            if name and model:
                choices.append((selected, f"{name} · {model}"))

        return tuple(choices)

    def get_selected_model(self):
        value = self.get_setting("model", search_default=False, return_value="")
        return value if isinstance(value, str) else ""

    def stream_enabled(self) -> bool:
        # Account owns the HTTP exchange and currently returns one verified
        # response object. Keep Newelle's caller contract while avoiding fake
        # token streaming.
        return False

    def supports_vision(self) -> bool:
        # The Account protocol validates image inputs independently from the
        # provider credential. Individual provider/model capability errors are
        # surfaced by Account instead of leaking provider access into Meo AI.
        return True

    @staticmethod
    def _system_text(system_prompt: list[str]) -> str:
        values = [str(value).strip() for value in system_prompt if str(value).strip()]
        text = "\n\n".join(values)
        if len(text) > 12000:
            raise ValueError("System prompt is too large for the Account AI broker")
        return text

    def _selection(self) -> tuple[str, str]:
        selected = self.get_selected_model().strip()
        if ":" not in selected:
            raise AccountAiUnavailable(
                "Choose a Meo Account connection and model in Meo AI settings first"
            )
        connection_id, model = selected.split(":", 1)
        if not connection_id or not model:
            raise AccountAiUnavailable("The selected Meo Account model is invalid")
        return connection_id, model

    def _generate(
        self,
        prompt: str,
        history: list[dict[str, str]],
        system_prompt: list[str],
    ) -> str:
        connection_id, model = self._selection()
        system_text = self._system_text(system_prompt)
        user_text, images = context_payload(prompt, history)
        categories = ["user_prompt"]
        if history:
            categories.append("conversation_history")
        if system_text:
            categories.append("system_prompt")
        if images:
            categories.append("user_images")

        client = account_ai_client()
        arguments = client.inference_arguments(
            connection_id=connection_id,
            model=model,
            purpose="meo_ai_conversation",
            user_prompt=user_text,
            system_prompt=system_text,
            data_categories=tuple(categories),
            input_images=images,
            temperature=0.3,
            max_output_tokens=4096,
        )
        prepared = client.prepare_inference(arguments)
        interaction = request_account_ai_consent(prepared)
        try:
            approved = interaction.wait()
        except Exception:
            try:
                client.deny_prepared(prepared)
            except Exception:
                pass
            raise
        if not approved:
            client.deny_prepared(prepared)
            raise AccountAiUnavailable("Meo Account AI request was denied")
        result = client.invoke_prepared(prepared)
        return str(result["text"])

    def generate_text(
        self,
        prompt: str,
        history: list[dict[str, str]] = [],
        system_prompt: list[str] = [],
    ) -> str:
        return self._generate(prompt, history, system_prompt)

    def generate_text_stream(
        self,
        prompt: str,
        history: list[dict[str, str]] = [],
        system_prompt: list[str] = [],
        on_update: Callable[[str], Any] = lambda _: None,
        extra_args: list = [],
    ) -> str:
        text = self._generate(prompt, history, system_prompt)
        on_update(text, *tuple(extra_args))
        return text
