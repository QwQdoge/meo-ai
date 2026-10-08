import unittest

from meo.system.dbus_router import DbusNextRouterClient, RouterUnavailable


class FakeVariant:
    def __init__(self, signature, value):
        self.signature = signature
        self.value = value


class FakeBus:
    def __init__(self):
        self.disconnected = 0

    def disconnect(self):
        self.disconnected += 1


class FakeInterface:
    def __init__(self):
        self.submitted = []
        self.lookups = []
        self.decisions = []

    async def call_list_capabilities(self):
        return [
            FakeVariant(
                "a{sv}",
                {
                    "id": FakeVariant("s", "org.meo.desktop.audio.setVolume"),
                    "title": FakeVariant("s", "Set volume"),
                    "owner": FakeVariant("s", "org.meo.desktop.audio"),
                    "effect": FakeVariant("s", "session"),
                    "verification": FakeVariant("s", "read-back"),
                    "maturity": FakeVariant("s", "stable"),
                    "requiresConfirmation": FakeVariant("b", False),
                    "argumentSchema": FakeVariant(
                        "a{sv}",
                        {
                            "type": FakeVariant("s", "object"),
                            "properties": FakeVariant(
                                "a{sv}",
                                {
                                    "percent": FakeVariant(
                                        "a{sv}",
                                        {"type": FakeVariant("s", "integer")},
                                    )
                                },
                            ),
                            "required": FakeVariant("as", ["percent"]),
                            "additionalProperties": FakeVariant("b", False),
                        },
                    ),
                },
            )
        ]

    async def call_submit_request(self, capability_id, arguments):
        self.submitted.append((capability_id, arguments))
        return {
            "requestId": FakeVariant("s", "router-1"),
            "capability": FakeVariant("s", capability_id),
            "state": FakeVariant("s", "running"),
        }

    async def call_get_request(self, request_id):
        self.lookups.append(request_id)
        return {
            "requestId": FakeVariant("s", request_id),
            "state": FakeVariant("s", "completed"),
            "message": FakeVariant("s", "Volume is 30%"),
        }

    async def call_decide_request(self, request_id, fingerprint, approve):
        self.decisions.append((request_id, fingerprint, approve))
        return {
            "requestId": FakeVariant("s", request_id),
            "state": FakeVariant("s", "denied" if not approve else "running"),
        }


class DbusRouterClientTests(unittest.TestCase):
    def make_client(self):
        bus = FakeBus()
        interface = FakeInterface()
        connects = []

        async def connect():
            connects.append(True)
            return bus, interface

        client = DbusNextRouterClient(
            timeout=1.0,
            _connect=connect,
            _variant_factory=FakeVariant,
        )
        return client, bus, interface, connects

    def test_one_connection_is_reused_for_submit_get_and_decide(self):
        client, bus, interface, connects = self.make_client()
        try:
            capabilities = client.list_capabilities()
            self.assertEqual(capabilities[0]["id"], "org.meo.desktop.audio.setVolume")
            schema = capabilities[0]["argumentSchema"]
            self.assertEqual(schema["properties"]["percent"]["type"], "integer")
            submitted = client.submit_request(
                "org.meo.desktop.audio.setVolume",
                {"percent": 30},
            )
            self.assertEqual(submitted["requestId"], "router-1")
            refreshed = client.get_request("router-1")
            self.assertEqual(refreshed["state"], "completed")
            decision = client.decide_request("router-1", "fingerprint", False)
            self.assertEqual(decision["state"], "denied")
            self.assertEqual(len(connects), 1)
            self.assertEqual(interface.lookups, ["router-1"])
            self.assertEqual(interface.decisions, [("router-1", "fingerprint", False)])
        finally:
            client.close()
        self.assertEqual(bus.disconnected, 1)

    def test_qvariant_map_arguments_keep_exact_scalar_types(self):
        client, _bus, interface, _connects = self.make_client()
        try:
            client.submit_request(
                "org.meo.test.action",
                {
                    "integer": 30,
                    "enabled": True,
                    "label": "demo",
                    "ratio": 0.5,
                    "names": ["one", "two"],
                    "nested": {"value": 1},
                },
            )
            arguments = interface.submitted[0][1]
            self.assertEqual(arguments["integer"].signature, "i")
            self.assertEqual(arguments["enabled"].signature, "b")
            self.assertEqual(arguments["label"].signature, "s")
            self.assertEqual(arguments["ratio"].signature, "d")
            self.assertEqual(arguments["names"].signature, "as")
            self.assertEqual(arguments["nested"].signature, "a{sv}")
            self.assertEqual(arguments["nested"].value["value"].signature, "i")
        finally:
            client.close()

    def test_ambiguous_or_out_of_range_values_fail_closed(self):
        client, _bus, interface, _connects = self.make_client()
        try:
            with self.assertRaises(ValueError):
                client.submit_request("org.meo.test.action", {"items": []})
            with self.assertRaises(ValueError):
                client.submit_request("org.meo.test.action", {"integer": 2**40})
            with self.assertRaises(ValueError):
                client.submit_request("org.meo.test.action", {"mixed": [1, "two"]})
            self.assertEqual(interface.submitted, [])
        finally:
            client.close()

    def test_closed_client_refuses_new_calls(self):
        client, _bus, _interface, _connects = self.make_client()
        client.close()
        with self.assertRaises(RouterUnavailable):
            client.list_capabilities()


if __name__ == "__main__":
    unittest.main()
