from __future__ import annotations

from typing import Any

from meo.service.controls import AiControl, ControlOption, find_control


class LegacyAiControls:
    """Typed Meo control surface backed by current Newelle runtime settings.

    This adapter keeps legacy GSettings keys out of AgentService/frontend APIs so
    those storage details can disappear later without changing the Meo contract.
    """

    def __init__(self, controller) -> None:
        self.controller = controller

    @property
    def settings(self):
        settings = getattr(self.controller, "settings", None)
        if settings is None:
            raise RuntimeError("legacy controller settings are unavailable")
        return settings

    def _bool(self, key: str, default: bool = False) -> bool:
        try:
            return bool(self.settings.get_boolean(key))
        except Exception:
            return default

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.settings.get_int(key))
        except Exception:
            return default

    def _string(self, key: str, default: str = "") -> str:
        try:
            value = self.settings.get_string(key)
            return value if isinstance(value, str) else default
        except Exception:
            return default

    def _llm(self):
        handlers = getattr(self.controller, "handlers", None)
        return getattr(handlers, "llm", None)

    def list_controls(self) -> list[AiControl]:
        controls = [
            AiControl(
                "memory.enabled",
                "Memory",
                "toggle",
                self._bool("memory-on"),
                description="Allow the assistant memory handler to use saved long-term context.",
            ),
            AiControl(
                "search.web_enabled",
                "Web search",
                "toggle",
                self._bool("websearch-on", True),
                description="Allow the search tool to use the configured web-search provider.",
            ),
            AiControl(
                "retrieval.documents_enabled",
                "Document retrieval",
                "toggle",
                self._bool("rag-on-documents", True),
                description="Use indexed documents as request context when available.",
            ),
            AiControl(
                "retrieval.local_folder_enabled",
                "Local folder retrieval",
                "toggle",
                self._bool("rag-on"),
                description="Allow retrieval from configured local document folders.",
            ),
            AiControl(
                "tools.auto_run",
                "Automatic tool execution",
                "toggle",
                self._bool("auto-run"),
                description="Let compatible legacy tools continue automatically when their own policy permits it.",
                safety_note="This does not bypass Meo System Router policy or privileged-action confirmation.",
            ),
            AiControl(
                "tools.parallel",
                "Parallel tool execution",
                "toggle",
                self._bool("parallel-tool-execution"),
                description="Run independent model tool calls in parallel when the runtime supports it.",
            ),
            AiControl(
                "tools.max_calls",
                "Maximum tool calls",
                "integer",
                self._int("max-tool-calls", 70),
                description="Upper bound on tool calls accepted during one model turn.",
                minimum=1,
                maximum=300,
                step=1,
            ),
            AiControl(
                "tools.max_iterations",
                "Maximum agent iterations",
                "integer",
                self._int("max-run-times", 5),
                description="Upper bound on repeated model/tool execution cycles.",
                minimum=1,
                maximum=100,
                step=1,
            ),
            AiControl(
                "context.max_tokens",
                "Context limit",
                "integer",
                self._int("context-max", 128000),
                description="Maximum context budget used by the compatibility context manager.",
                minimum=1024,
                maximum=4_000_000,
                step=1024,
            ),
            AiControl(
                "context.suggested_tokens",
                "Suggested context target",
                "integer",
                self._int("context-suggested", 30000),
                description="Preferred working context size before trimming or summarization.",
                minimum=1024,
                maximum=4_000_000,
                step=1024,
            ),
            AiControl(
                "context.summarization",
                "Context summarization",
                "toggle",
                self._bool("context-summarization"),
                description="Summarize older context when the context manager needs to reduce history.",
            ),
            AiControl(
                "usage.tracking",
                "Usage tracking",
                "toggle",
                self._bool("usage-tracking"),
                description="Keep local model/token usage statistics for inspection.",
            ),
        ]

        llm = self._llm()
        if llm is not None:
            try:
                modes = llm.get_thinking_modes()
            except Exception:
                modes = None
            if modes:
                options = tuple(ControlOption(str(value), str(label)) for value, label in modes)
                try:
                    selected = str(llm.get_thinking_mode())
                except Exception:
                    selected = options[0].value
                if selected not in {option.value for option in options}:
                    selected = options[0].value
                controls.append(AiControl(
                    "model.thinking_effort",
                    "Thinking effort",
                    "select",
                    selected,
                    description="Provider/model reasoning effort. Only shown when the current handler exposes discrete modes.",
                    options=options,
                ))

            try:
                streaming = llm.get_setting("streaming", search_default=False)
            except Exception:
                streaming = None
            if isinstance(streaming, bool):
                controls.append(AiControl(
                    "model.streaming",
                    "Streaming",
                    "toggle",
                    streaming,
                    description="Stream model output as it is generated.",
                ))

        return controls

    def set_control(self, control_id: str, value: Any) -> AiControl:
        control = find_control(self.list_controls(), control_id)
        value = control.validate_value(value)

        boolean_keys = {
            "memory.enabled": "memory-on",
            "search.web_enabled": "websearch-on",
            "retrieval.documents_enabled": "rag-on-documents",
            "retrieval.local_folder_enabled": "rag-on",
            "tools.auto_run": "auto-run",
            "tools.parallel": "parallel-tool-execution",
            "context.summarization": "context-summarization",
            "usage.tracking": "usage-tracking",
        }
        integer_keys = {
            "tools.max_calls": "max-tool-calls",
            "tools.max_iterations": "max-run-times",
            "context.max_tokens": "context-max",
            "context.suggested_tokens": "context-suggested",
        }

        if control_id in boolean_keys:
            self.settings.set_boolean(boolean_keys[control_id], value)
        elif control_id in integer_keys:
            self.settings.set_int(integer_keys[control_id], value)
        elif control_id == "model.thinking_effort":
            llm = self._llm()
            if llm is None:
                raise ValueError("current model does not expose thinking effort")
            llm.set_thinking_mode(value)
        elif control_id == "model.streaming":
            llm = self._llm()
            if llm is None:
                raise ValueError("current model does not expose streaming control")
            llm.set_setting("streaming", value)
        else:
            raise ValueError(f"control is not writable: {control_id}")

        update = getattr(self.controller, "update_settings", None)
        if callable(update):
            update()
        return find_control(self.list_controls(), control_id)
