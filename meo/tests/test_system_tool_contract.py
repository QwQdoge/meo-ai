import unittest

from meo.system.system_tool import (
    CapabilityEffect,
    CapabilityMaturity,
    CapabilityVerification,
    SystemTool,
    SystemToolRequest,
)


class FakeRouter:
    def __init__(self):
        self.submitted = []
        self.decisions = []

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
            },
            {
                "id": "org.meo.test.erase",
                "title": "Erase test data",
                "owner": "org.meo.test",
                "effect": "irreversible",
                "verification": "owner-result",
                "maturity": "preview",
                "requiresConfirmation": True,
            },
        ]

    def submit_request(self, capability_id, arguments):
        self.submitted.append((capability_id, dict(arguments)))
        if capability_id == "org.meo.test.erase":
            return {
                "requestId": "router:confirm",
                "state": "awaiting_confirmation",
                "fingerprint": "abc123",
            }
        return {"requestId": "router:done", "state": "completed", "message": "Volume is 30%"}

    def get_request(self, request_id):
        return {"requestId": request_id, "state": "completed"}

    def decide_request(self, request_id, fingerprint, approve):
        self.decisions.append((request_id, fingerprint, approve))
        return {"requestId": request_id, "state": "completed" if approve else "denied"}


class SystemToolContractTests(unittest.TestCase):
    def test_router_metadata_is_strictly_parsed(self):
        capabilities = SystemTool(FakeRouter()).capabilities()
        volume = capabilities[0]
        self.assertEqual(volume.effect, CapabilityEffect.SESSION)
        self.assertEqual(volume.verification, CapabilityVerification.READ_BACK)
        self.assertEqual(volume.maturity, CapabilityMaturity.STABLE)
        self.assertFalse(volume.requires_confirmation)

    def test_unknown_capability_is_rejected_before_submit(self):
        router = FakeRouter()
        tool = SystemTool(router)
        with self.assertRaises(ValueError):
            tool.invoke(SystemToolRequest("org.meo.invented.action", {}))
        self.assertEqual(router.submitted, [])

    def test_preview_capability_is_not_promoted_or_blocked_by_agent(self):
        router = FakeRouter()
        result = SystemTool(router).invoke(SystemToolRequest("org.meo.test.erase", {"target": "demo"}))
        self.assertEqual(result.capability.maturity, CapabilityMaturity.PREVIEW)
        self.assertEqual(result.state, "awaiting_confirmation")
        self.assertEqual(router.decisions, [])

    def test_confirmation_requires_explicit_decide_call(self):
        router = FakeRouter()
        tool = SystemTool(router)
        result = tool.invoke(SystemToolRequest("org.meo.test.erase", {"target": "demo"}))
        self.assertEqual(result.state, "awaiting_confirmation")
        tool.decide(result.router_request_id, "abc123", False)
        self.assertEqual(router.decisions, [("router:confirm", "abc123", False)])

    def test_arguments_are_transport_safe_but_not_schema_coerced(self):
        router = FakeRouter()
        tool = SystemTool(router)
        result = tool.invoke(SystemToolRequest("org.meo.desktop.audio.setVolume", {"percent": 30}))
        self.assertEqual(result.state, "completed")
        self.assertEqual(router.submitted, [("org.meo.desktop.audio.setVolume", {"percent": 30})])
        with self.assertRaises(ValueError):
            SystemToolRequest("org.meo.desktop.audio.setVolume", {"percent": object()})
        with self.assertRaises(ValueError):
            SystemToolRequest("org.meo.desktop.audio.setVolume", {"percent": None})

    def test_bad_router_metadata_is_rejected(self):
        router = FakeRouter()
        router.list_capabilities = lambda: [{
            "id": "org.meo.test.action",
            "title": "Bad",
            "owner": "org.meo.other",
            "effect": "session",
            "verification": "read-back",
            "maturity": "stable",
            "requiresConfirmation": False,
        }]
        with self.assertRaises(ValueError):
            SystemTool(router).capabilities()


if __name__ == "__main__":
    unittest.main()
