from __future__ import annotations

from contextlib import contextmanager
import gettext
import importlib
import os
import sys
import types
import threading

from meo.adapters.presentation_legacy_chat import MeoLegacyChatInterfaceAdapter
from meo.runtime.headless_probe import require_headless


class MeoHeadlessUIController:
    """UI extension surface used by the Newelle core without constructing widgets."""

    def __init__(self, controller):
        self.controller = controller

    def require_tool_update(self):
        return self.controller.require_tool_update()

    def refresh_extension_resources(self, refreshes):
        return None

    def set_model_loading(self, status):
        return None

    def get_current_chat_id(self):
        return self.controller.newelle_settings.chat_id

    def get_current_message_id(self):
        return self.controller.msgid

    def get_current_tool_call_id(self):
        return getattr(self.controller, "current_tool_uuid", None)

    def get_tool_result_by_id(self, tool_uuid: str):
        prefix = "[Tool: "
        for entry in self.controller.chat:
            if entry.get("User") != "Console":
                continue
            message = entry.get("Message", "")
            if not message.startswith(prefix) or f"ID: {tool_uuid}]" not in message:
                continue
            lines = message.split("\n", 1)
            return lines[1] if len(lines) > 1 else ""
        return None

    def open_link(self, *_args, **_kwargs): return None
    def add_tab(self, *_args, **_kwargs): return None
    def new_browser_tab(self, *_args, **_kwargs): return None
    def new_explorer_tab(self, *_args, **_kwargs): return None
    def new_editor_tab(self, *_args, **_kwargs): return None
    def new_terminal_tab(self, *_args, **_kwargs): return None
    def add_text_to_input(self, *_args, **_kwargs): return None
    def add_reading_widget(self, *_args, **_kwargs): return None
    def remove_reading_widget(self, *_args, **_kwargs): return None
    def refresh_audio_message(self, *_args, **_kwargs): return None
    def update_history(self): return None
    def send_notification(self, text): return text


@contextmanager
def _controller_import_shims():
    """Bypass two known UI-only imports while the upstream controller is extracted."""
    repository = importlib.import_module("gi.repository")
    missing = object()
    previous_adw = repository.__dict__.get("Adw", missing)
    previous_ui_module = sys.modules.get("src.ui_controller", missing)

    repository.Adw = types.SimpleNamespace()
    shim = types.ModuleType("src.ui_controller")
    shim.UIController = object
    sys.modules["src.ui_controller"] = shim
    try:
        yield
    finally:
        if previous_adw is missing:
            repository.__dict__.pop("Adw", None)
        else:
            repository.Adw = previous_adw
        if previous_ui_module is missing:
            sys.modules.pop("src.ui_controller", None)
        else:
            sys.modules["src.ui_controller"] = previous_ui_module


def _import_controller_class():
    require_headless()
    with _controller_import_shims():
        module = importlib.import_module("src.controller")
    require_headless()
    return module.NewelleController


def _system_tools_enabled() -> bool:
    return os.environ.get("MEO_AI_ENABLE_SYSTEM_TOOL", "").strip().lower() in {"1", "true", "yes", "on"}


def _install_presentation_tools(controller, backend) -> None:
    from meo.adapters.presentation_tools import NewellePresentationToolAdapter

    adapter = NewellePresentationToolAdapter()
    adapter.install(controller)
    backend._meo_presentation_tool_adapter = adapter


def _install_system_tools(controller, backend) -> None:
    if not _system_tools_enabled():
        return

    from meo.adapters.system_tools import NewelleSystemToolAdapter
    from meo.system.dbus_router import DbusNextRouterClient
    from meo.system.system_tool import SystemTool

    router_client = DbusNextRouterClient()
    adapter = NewelleSystemToolAdapter(SystemTool(router_client))
    try:
        adapter.install(controller)
    except Exception:
        router_client.close()
        raise
    backend._meo_router_client = router_client
    backend._meo_system_tool_adapter = adapter


def create_backend():
    """Construct the compatibility core without constructing a Newelle window."""
    gettext.install("newelle")
    Controller = _import_controller_class()
    controller = Controller(sys.path)
    controller.ui_init(headless=True)
    controller.set_ui_controller(MeoHeadlessUIController(controller))

    from src.utility.replacehelper import ReplaceHelper
    ReplaceHelper.set_controller(controller)

    from src.handlers.interfaces.chat_interface import ChatInterface

    interface_path = os.path.join(controller.config_dir, "meo-agent-service", "chat")
    interface = ChatInterface(controller.settings, interface_path)
    interface.set_controller(controller)
    backend = MeoLegacyChatInterfaceAdapter(interface)
    backend._meo_controller = controller
    _install_presentation_tools(controller, backend)
    _install_system_tools(controller, backend)
    require_headless()

    from gi.repository import GLib
    backend._meo_glib_loop = GLib.MainLoop()
    backend._meo_glib_thread = threading.Thread(
        target=backend._meo_glib_loop.run, name="meo-tool-dispatch", daemon=True
    )
    backend._meo_glib_thread.start()

    # Keep Newelle GSettings details behind one temporary adapter. AgentService
    # and the native frontend see only typed Meo control IDs.
    from meo.adapters.control_backend import ControlledLegacyBackend
    return ControlledLegacyBackend(backend, controller)
