from __future__ import annotations

import asyncio
import unittest

from meo.system.account_ai import (
    AccountAiUnavailable,
    DbusNextAccountAiClient,
    MEO_AI_CLIENT_ID,
)


class FakeVariant:
    def __init__(self, signature, value):
        self.signature = signature
        self.value = value


class FakeBus:
    def disconnect(self):
        return None


class FakeAccountInterface:
    def __init__(self):
        self.operations = []
        self.cloud_operations = []
        self.requests = {}
        self.get_counts = {}

    async def call_list_available_local_ai_connections(self, client_id):
        assert client_id == MEO_AI_CLIENT_ID
        return [
            {
                "id": FakeVariant("s", "connection-one"),
                "provider": FakeVariant("s", "openai_compatible"),
                "displayName": FakeVariant("s", "Provider"),
                "defaultModel": FakeVariant("s", "model-one"),
            }
        ]

    async def call_start_local_ai_operation(self, client_id, action, arguments):
        assert client_id == MEO_AI_CLIENT_ID
        request_id = f"request-{len(self.operations) + 1}"
        decoded = DbusNextAccountAiClient._unwrap(arguments)
        self.operations.append((action, decoded))
        if action == "prepare_inference":
            self.requests[request_id] = [
                {"id": request_id, "state": "contacting_provider"},
                {
                    "id": request_id,
                    "state": "completed",
                    "consent": {
                        "requestId": "consent-one",
                        "payloadSha256": "a" * 64,
                        "confirmationVersion": 1,
                        "provider": "openai_compatible",
                        "providerName": "Provider",
                        "model": decoded["model"],
                        "purpose": decoded["purpose"],
                        "dataCategories": decoded["dataCategories"],
                    },
                },
            ]
        elif action == "invoke":
            self.requests[request_id] = [
                {"id": request_id, "state": "contacting_provider"},
                {
                    "id": request_id,
                    "state": "completed",
                    "operation": "local_ai_result",
                    "provider": "openai_compatible",
                    "model": decoded["model"],
                    "text": "brokered answer",
                },
            ]
        elif action == "deny_inference":
            self.requests[request_id] = [
                {"id": request_id, "state": "denied", "operation": "local_ai_denied"}
            ]
        else:
            self.requests[request_id] = [{"id": request_id, "state": "failed"}]
        return request_id

    async def call_start_cloud_ai_operation(self, client_id, action, arguments):
        assert client_id == MEO_AI_CLIENT_ID
        request_id = f"cloud-request-{len(self.cloud_operations) + 1}"
        decoded = DbusNextAccountAiClient._unwrap(arguments)
        self.cloud_operations.append((action, decoded))
        if action == "list_connections":
            self.requests[request_id] = [{
                "id": request_id,
                "state": "completed",
                "connections": [{
                    "id": "cloud-connection",
                    "provider": "openai_compatible",
                    "displayName": "Cloud Provider",
                    "source": "cloud",
                }],
            }]
        elif action == "discover_models":
            self.requests[request_id] = [{
                "id": request_id,
                "state": "completed",
                "models": [{"id": "cloud-model", "name": "Cloud Model"}],
            }]
        elif action == "prepare_inference":
            self.requests[request_id] = [{
                "id": request_id,
                "state": "completed",
                "consent": {
                    "requestId": "cloud-consent",
                    "payloadSha256": "b" * 64,
                    "confirmationVersion": 1,
                    "provider": "openai_compatible",
                    "providerName": "Cloud Provider",
                    "model": decoded["model"],
                    "purpose": decoded["purpose"],
                    "dataCategories": decoded["dataCategories"],
                },
            }]
        elif action == "invoke":
            self.requests[request_id] = [{
                "id": request_id,
                "state": "completed",
                "text": "cloud brokered answer",
            }]
        elif action == "deny_inference":
            self.requests[request_id] = [{"id": request_id, "state": "denied"}]
        else:
            self.requests[request_id] = [{"id": request_id, "state": "failed"}]
        return request_id

    async def call_get_request(self, request_id):
        sequence = self.requests[request_id]
        count = self.get_counts.get(request_id, 0)
        self.get_counts[request_id] = count + 1
        return sequence[min(count, len(sequence) - 1)]


class AccountAiClientTest(unittest.TestCase):
    def setUp(self):
        self.interface = FakeAccountInterface()

        async def connect():
            await asyncio.sleep(0)
            return FakeBus(), self.interface

        self.client = DbusNextAccountAiClient(
            timeout=1,
            operation_timeout=1,
            poll_interval=0.001,
            _connect=connect,
            _variant_factory=FakeVariant,
        )

    def tearDown(self):
        self.client.close()

    def test_lists_only_metadata(self):
        connections = self.client.list_connections()
        self.assertEqual(connections[0]["id"], "connection-one")
        self.assertEqual(connections[0]["defaultModel"], "model-one")
        self.assertNotIn("apiKey", connections[0])
        self.assertNotIn("secret", connections[0])

    def test_cloud_connections_models_and_inference_stay_brokered(self):
        connections = self.client.list_connections()
        cloud = next(item for item in connections if item.get("source") == "cloud")
        self.assertNotIn("apiKey", cloud)
        self.assertNotIn("secret", cloud)
        models = self.client.discover_models(cloud["id"], source="cloud")
        self.assertEqual(models, [{"id": "cloud-model", "name": "Cloud Model"}])

        prepared = self.client.prepare_inference(
            self.client.inference_arguments(
                connection_id=cloud["id"],
                model="cloud-model",
                purpose="conversation_response",
                user_prompt="Hello cloud",
            ),
            source="cloud",
        )
        result = self.client.invoke_prepared(prepared)
        self.assertEqual(result["text"], "cloud brokered answer")
        self.assertEqual([entry[0] for entry in self.interface.cloud_operations], [
            "list_connections", "discover_models", "prepare_inference", "invoke",
        ])
        self.assertTrue(prepared.source == "cloud")

    def test_prepare_and_invoke_reuse_identical_broker_arguments(self):
        arguments = self.client.inference_arguments(
            connection_id="connection-one",
            model="model-one",
            purpose="conversation_response",
            user_prompt="Hello",
            system_prompt="Be useful",
            data_categories=("user_prompt",),
        )
        prepared = self.client.prepare_inference(arguments)
        result = self.client.invoke_prepared(prepared)

        self.assertEqual(result["text"], "brokered answer")
        self.assertEqual(self.interface.operations[0][0], "prepare_inference")
        self.assertEqual(self.interface.operations[1][0], "invoke")
        prepared_args = self.interface.operations[0][1]
        invoked_args = dict(self.interface.operations[1][1])
        consent = invoked_args.pop("consent")
        self.assertEqual(invoked_args, prepared_args)
        self.assertTrue(consent["approved"])
        self.assertFalse(consent["remember"])
        self.assertEqual(consent["payloadSha256"], "a" * 64)

    def test_deny_uses_same_bound_consent(self):
        prepared = self.client.prepare_inference(
            self.client.inference_arguments(
                connection_id="connection-one",
                model="model-one",
                purpose="conversation_response",
                user_prompt="Sensitive prompt",
            )
        )
        result = self.client.deny_prepared(prepared)
        self.assertEqual(result["state"], "denied")
        action, arguments = self.interface.operations[-1]
        self.assertEqual(action, "deny_inference")
        self.assertFalse(arguments["consent"]["approved"])

    def test_secret_shaped_arguments_are_rejected_before_dbus(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            self.client.start_operation(
                "prepare_inference",
                {"connectionId": "x", "api_key": "must-not-enter-agent"},
            )
        self.assertEqual(self.interface.operations, [])

    def test_invalid_operation_is_rejected_locally(self):
        with self.assertRaises(ValueError):
            self.client.start_operation("raw_provider_request", {"connectionId": "x"})

    def test_prepare_surfaces_broker_failure_without_provider_secret(self):
        original = self.interface.call_start_local_ai_operation

        async def fail(client_id, action, arguments):
            request_id = await original(client_id, action, arguments)
            self.interface.requests[request_id] = [
                {"id": request_id, "state": "failed", "error": "Provider request rejected"}
            ]
            return request_id

        self.interface.call_start_local_ai_operation = fail
        with self.assertRaisesRegex(AccountAiUnavailable, "Provider request rejected"):
            self.client.prepare_inference(
                self.client.inference_arguments(
                    connection_id="connection-one",
                    model="model-one",
                    purpose="conversation_response",
                    user_prompt="Hello",
                )
            )


if __name__ == "__main__":
    unittest.main()
