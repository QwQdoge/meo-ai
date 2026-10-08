from __future__ import annotations

import json
import re
from typing import Any

from meo.system.system_tool import (
    CapabilityDescriptor,
    SystemTool,
    SystemToolRequest,
    TERMINAL_ROUTER_STATES,
)


class NewelleSystemToolAdapter:
    """Compatibility adapter exposing Router capabilities as Newelle tools.

    Each Router capability becomes one fixed Newelle tool whose parameter schema
    comes directly from Router `argumentSchema`. This avoids a generic tool where
    the model could invent capability IDs or where meo-ai would duplicate Router
    argument definitions.
    """

    def __init__(
        self,
        system_tool: SystemTool,
        *,
        poll_timeout: float = 35.0,
        poll_interval: float = 0.1,
        _tool_types: tuple[type, type, type] | None = None,
    ) -> None:
        self.system_tool = system_tool
        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval
        self._tool_types_override = _tool_types
        self._installed_controller = None
        self._original_require_tool_update = None

    def _tool_types(self):
        if self._tool_types_override is not None:
            return self._tool_types_override
        # Compatibility-only dependency: src.tools imports GLib. Keep it out of
        # meo/system so the stable SystemTool contract remains UI/runtime neutral.
        from src.tools import InteractionOption, Tool, ToolResult

        return Tool, ToolResult, InteractionOption

    @staticmethod
    def tool_name(capability_id: str) -> str:
        name = re.sub(r"[^A-Za-z0-9]+", "_", capability_id).strip("_")
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
        return f"system_{name}"

    @staticmethod
    def _description(descriptor: CapabilityDescriptor) -> str:
        return (
            f"{descriptor.title}. Meo system capability owned by {descriptor.owner}; "
            f"effect={descriptor.effect.value}, maturity={descriptor.maturity.value}. "
            "Arguments and execution are validated by the System AI Router."
        )

    @staticmethod
    def _confirmation_text(descriptor: CapabilityDescriptor, view: dict[str, Any]) -> str:
        """Render trusted Router confirmation fields for the frontend.

        The title comes from capability metadata; target/impact come from the
        Router request view after typed argument validation. Model prose is not
        used to construct this confirmation text.
        """

        lines = [descriptor.title]
        target = view.get("target")
        impact = view.get("impact")
        if isinstance(target, str) and target.strip():
            lines.append(f"Target: {target.strip()}")
        if isinstance(impact, str) and impact.strip():
            lines.append(f"Impact: {impact.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _model_output(descriptor: CapabilityDescriptor, view: dict[str, Any]) -> str:
        safe = {
            "capability": descriptor.capability_id,
            "state": view.get("state", "unknown"),
        }
        for key in ("message", "title", "target"):
            value = view.get(key)
            if isinstance(value, str) and value:
                safe[key] = value
        return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))

    def _finish_after_decision(
        self,
        tool_result,
        descriptor: CapabilityDescriptor,
        request_id: str,
        fingerprint: str,
        approve: bool,
    ) -> None:
        try:
            view = dict(self.system_tool.decide(request_id, fingerprint, approve))
            state = view.get("state")
            if approve and isinstance(state, str) and state not in TERMINAL_ROUTER_STATES:
                view = self.system_tool.wait_terminal(
                    request_id,
                    timeout=self.poll_timeout,
                    poll_interval=self.poll_interval,
                )
            tool_result.set_output(self._model_output(descriptor, view))
        except Exception as exc:
            tool_result.set_output(
                json.dumps(
                    {
                        "capability": descriptor.capability_id,
                        "state": "error",
                        "message": str(exc),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

    def _execute(self, descriptor: CapabilityDescriptor, **arguments):
        _Tool, ToolResult, InteractionOption = self._tool_types()
        result = self.system_tool.invoke(
            SystemToolRequest(descriptor.capability_id, dict(arguments))
        )
        view = dict(result.router_view)

        if result.state == "awaiting_confirmation":
            request_id = result.router_request_id
            fingerprint = view.get("fingerprint")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("Router confirmation request is missing requestId")
            if not isinstance(fingerprint, str) or not fingerprint:
                raise ValueError("Router confirmation request is missing fingerprint")

            tool_result = ToolResult(
                requires_interaction=True,
                display_text=self._confirmation_text(descriptor, view),
            )
            tool_result.set_intreaction_options(
                [
                    InteractionOption(
                        "Deny",
                        lambda: self._finish_after_decision(
                            tool_result, descriptor, request_id, fingerprint, False
                        ),
                    ),
                    InteractionOption(
                        "Approve",
                        lambda: self._finish_after_decision(
                            tool_result, descriptor, request_id, fingerprint, True
                        ),
                    ),
                ]
            )
            return tool_result

        if result.router_request_id and result.state not in TERMINAL_ROUTER_STATES:
            view = self.system_tool.wait_terminal(
                result.router_request_id,
                timeout=self.poll_timeout,
                poll_interval=self.poll_interval,
            )

        tool_result = ToolResult(display_text=descriptor.title)
        tool_result.set_output(self._model_output(descriptor, view))
        return tool_result

    def build_tools(self) -> list[object]:
        Tool, _ToolResult, _InteractionOption = self._tool_types()
        descriptors = self.system_tool.capabilities()
        names: set[str] = set()
        tools = []
        for descriptor in descriptors:
            name = self.tool_name(descriptor.capability_id)
            if name in names:
                raise ValueError("Router capability IDs collide as Newelle tool names")
            names.add(name)

            def execute(_descriptor=descriptor, **kwargs):
                return self._execute(_descriptor, **kwargs)

            tools.append(
                Tool(
                    name,
                    self._description(descriptor),
                    execute,
                    schema=dict(descriptor.argument_schema),
                    title=descriptor.title,
                    prompt_editable=False,
                    default_on=True,
                    tools_group="Meo System",
                    default_lazy_load=False,
                )
            )
        return tools

    def register_into(self, registry) -> None:
        for tool in self.build_tools():
            existing = getattr(registry, "get_tool", lambda _name: None)(tool.name)
            if existing is not None:
                raise ValueError(f"Newelle tool name already registered: {tool.name}")
            registry.register_tool(tool)

    def install(self, controller) -> None:
        if self._installed_controller is not None:
            if self._installed_controller is controller:
                return
            raise RuntimeError("SystemTool adapter is already installed on another controller")

        original = controller.require_tool_update
        self._installed_controller = controller
        self._original_require_tool_update = original

        def require_tool_update():
            result = original()
            self.register_into(controller.tools)
            return result

        controller.require_tool_update = require_tool_update
        self.register_into(controller.tools)

    def uninstall(self) -> None:
        controller = self._installed_controller
        original = self._original_require_tool_update
        if controller is None or original is None:
            return
        controller.require_tool_update = original
        self._installed_controller = None
        self._original_require_tool_update = None
