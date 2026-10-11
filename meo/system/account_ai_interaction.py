from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
from typing import Callable
from uuid import uuid4

from meo.system.account_ai import PreparedAccountInference


class AccountAiConsentUnavailable(RuntimeError):
    pass


@dataclass
class AccountAiConsentInteraction:
    prepared: PreparedAccountInference
    interaction_id: str = field(default_factory=lambda: f"account-ai:{uuid4()}")
    _event: threading.Event = field(default_factory=threading.Event, repr=False)
    _selected: int | None = field(default=None, repr=False)

    @property
    def consent(self) -> dict:
        return dict(self.prepared.consent)

    def public_event(self) -> dict:
        consent = self.consent
        provider = str(consent.get("providerName") or consent.get("provider") or "AI provider")
        model = str(consent.get("model") or "model")
        purpose = str(consent.get("purpose") or "AI request")
        categories = consent.get("dataCategories")
        if not isinstance(categories, list):
            categories = []
        category_text = ", ".join(str(value) for value in categories) or "prompt data"
        prompt_characters = consent.get("promptCharacters")
        size_text = (
            f" · {prompt_characters} prompt characters"
            if isinstance(prompt_characters, int) and prompt_characters >= 0
            else ""
        )
        return {
            "type": "tool_interaction",
            "interaction_id": self.interaction_id,
            "tool_name": "Meo Account AI",
            "display_text": (
                f"Send {category_text} to {provider} using {model} for {purpose}{size_text}. "
                "The saved provider credential remains inside Meo Account/KWallet."
            ),
            "options": [
                {"index": 0, "title": "Allow once"},
                {"index": 1, "title": "Deny"},
            ],
        }

    def resolve(self, option_index: int) -> bool:
        if option_index not in (0, 1):
            raise ValueError("Account AI consent option must be Allow once or Deny")
        if self._event.is_set():
            return False
        self._selected = option_index
        self._event.set()
        return True

    def wait(self, timeout: float = 285.0) -> bool:
        if timeout <= 0:
            raise ValueError("consent timeout must be positive")
        if not self._event.wait(timeout):
            raise AccountAiConsentUnavailable("Meo Account AI consent timed out")
        return self._selected == 0


_thread_state = threading.local()


@contextmanager
def bind_account_ai_consent_sink(sink: Callable[[AccountAiConsentInteraction], None]):
    previous = getattr(_thread_state, "sink", None)
    _thread_state.sink = sink
    try:
        yield
    finally:
        if previous is None:
            try:
                delattr(_thread_state, "sink")
            except AttributeError:
                pass
        else:
            _thread_state.sink = previous


def request_account_ai_consent(prepared: PreparedAccountInference) -> AccountAiConsentInteraction:
    sink = getattr(_thread_state, "sink", None)
    if not callable(sink):
        raise AccountAiConsentUnavailable(
            "Account AI inference requires an interactive Meo AgentService request"
        )
    interaction = AccountAiConsentInteraction(prepared)
    sink(interaction)
    return interaction
