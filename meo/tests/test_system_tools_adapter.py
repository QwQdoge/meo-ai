import json
import unittest

from meo.adapters.system_tools import NewelleSystemToolAdapter
from meo.system.system_tool import SystemTool


VOLUME_SCHEMA = {
    "type": "object",
    "properties": {"percent": {"type": "integer"}},
    "required": ["percent"],
    "additionalProperties": False,
}
ERASE_SCHEMA = {
    "type": "object",
    "properties": {"target": {"type": "string"}},
    "required": ["target"],
    "additionalProperties": False,
}


class FakeOption:
    def __init__(self, title, callback):
        self.title = title
        self.callback = callback


class FakeToolResult:
    def __init__(self, output=None, requires_interaction=False, interaction_options=None, display_text=None, **_kwargs):
        self.output = output
        self.requires_interaction = requires_interaction
        self.interaction_options = list(interaction_options or [])
        self.display_text = display_text

    def set_output(self, output):
        self.output = output

    def set_intreaction_options(self, options):
        self.interaction_options = list(options)


class FakeTool:
    def __init__(self, name, description, func, schema=None, **kwargs):
        self.name = name
        self.description = description
        self.func = func
        self.schema = schema
        self.title = kwargs.get("title")
        self.prompt_editable = kwargs.get("prompt_editable")
        self.tools_group = kwargs.get("tools_group")

    def execute(self, **kwargs):
        return self.func(**kwargs)


class FakeRegistry:
    def __init__(self):
        self.tools = {}

    def get_tool(self, name):
        return self.tools.get(name)

    def register_tool(self, tool):
        self.tools[tool.name] = tool


class FakeRouter:
    def __init__(self):
        self.submitted = []
        self.decisions = []
        self.refreshes = {}

    def list_capabilities(self):
        return [
            {
                "id": "org.meo.desktop.audio.setVolume",
                "title": "Set volume",
                "owner": "org.meo.desktop.audio",
                "effect": "session",
                "verification": "read-back",
                "maturity": "stable",
                "requiresConfirmation": False,
                "argumentSchema": VOLUME_SCHEMA,
            },
            {
                "id": "org.meo.test.erase",
                "title": "Erase test data",
                "owner": "org.meo.test",
                "effect": "irreversible",
                "verification": "owner-result",
                "maturity": "preview",
                "requiresConfirmation": True,
                "argumentSchema": ERASE_SCHEMA,
            },
        ]

    def submit_request(self, capability_id, arguments):
        self.submitted.append((capability_id, dict(arguments)))
        if capability_id == "org.meo.test.erase":
            return {
                "requestId": "router-confirm",
                "state": "awaiting_confirmation",
                "fingerprint": "fingerprint-1",
                "title": "Erase test data",
                "target": arguments["target"],
                "impact": "This cannot be undone",
            }
        self.refreshes["router-volume"] = [
            {"requestId": "router-volume", "state": "completed", "message": "Volume is 30%"}
        ]
        return {"requestId": "router-volume", "state": "running", "title": "Set volume"}

    def get_request(self, request_id):
        values = self.refreshes.get(request_id, [])
        if values:
            return values.pop(0)
        return {"requestId": request_id, "state": "completed"}

    def decide_request(self, request_id, fingerprint, approve):
        self.decisions.append((request_id, fingerprint, approve))
        if approve:
            self.refreshes[request_id] = [
                {"requestId": request_id, "state": "completed", "message": "Erased"}
            ]
            return {"requestId": request_id, "state": "running"}
        return {"requestId": request_id, "state": "denied", "message": "Denied by user"}


class FakeController:
    def __init__(self):
        self.tools = FakeRegistry()
        self.rebuilds = 0

    def require_tool_update(self):
        self.rebuilds += 1
        self.tools = FakeRegistry()
        return "rebuilt"


class SystemToolsAdapterTests(unittest.TestCase):
    def adapter(self):
        router = FakeRouter()
        adapter = NewelleSystemToolAdapter(
            SystemTool(router),
            poll_timeout=1.0,
            poll_interval=0.001,
            _tool_types=(FakeTool, FakeToolResult, FakeOption),
        )
        return adapter, router

    def test_capabilities_become_fixed_tools_with_router_schema(self):
        adapter, _router = self.adapter()
        tools = adapter.build_tools()
        self.assertEqual(
            [tool.name for tool in tools],
            [
                "system_org_meo_desktop_audio_set_volume",
                "system_org_meo_test_erase",
            ],
        )
        self.assertEqual(tools[0].schema, VOLUME_SCHEMA)
        self.assertFalse(tools[0].prompt_editable)
        self.assertEqual(tools[0].tools_group, "Meo System")

    def test_reversible_action_waits_for_router_completion(self):
        adapter, router = self.adapter()
        volume = adapter.build_tools()[0]
        result = volume.execute(percent=30)
        output = json.loads(result.output)
        self.assertEqual(output["state"], "completed")
        self.assertEqual(output["message"], "Volume is 30%")
        self.assertEqual(
            router.submitted,
            [("org.meo.desktop.audio.setVolume", {"percent": 30})],
        )

    def test_confirmation_is_explicit_and_shows_trusted_router_details(self):
        adapter, router = self.adapter()
        erase = adapter.build_tools()[1]
        result = erase.execute(target="demo")
        self.assertTrue(result.requires_interaction)
        self.assertEqual([option.title for option in result.interaction_options], ["Deny", "Approve"])
        self.assertIn("Erase test data", result.display_text)
        self.assertIn("Target: demo", result.display_text)
        self.assertIn("Impact: This cannot be undone", result.display_text)
        self.assertEqual(router.decisions, [])
        self.assertIsNone(result.output)

        result.interaction_options[0].callback()
        self.assertEqual(router.decisions, [("router-confirm", "fingerprint-1", False)])
        self.assertEqual(json.loads(result.output)["state"], "denied")

    def test_approval_waits_until_owner_finishes(self):
        adapter, router = self.adapter()
        erase = adapter.build_tools()[1]
        result = erase.execute(target="demo")
        result.interaction_options[1].callback()
        self.assertEqual(router.decisions, [("router-confirm", "fingerprint-1", True)])
        output = json.loads(result.output)
        self.assertEqual(output["state"], "completed")
        self.assertEqual(output["message"], "Erased")

    def test_registration_survives_newelle_tool_registry_rebuild(self):
        adapter, _router = self.adapter()
        controller = FakeController()
        adapter.install(controller)
        self.assertIn("system_org_meo_desktop_audio_set_volume", controller.tools.tools)
        self.assertEqual(controller.require_tool_update(), "rebuilt")
        self.assertEqual(controller.rebuilds, 1)
        self.assertIn("system_org_meo_desktop_audio_set_volume", controller.tools.tools)
        adapter.uninstall()
        controller.require_tool_update()
        self.assertNotIn("system_org_meo_desktop_audio_set_volume", controller.tools.tools)


if __name__ == "__main__":
    unittest.main()
