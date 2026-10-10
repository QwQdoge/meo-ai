"""Real service/relay orchestration with an AI stub and in-memory IO/storage.

No provider credentials, shell execution, Account login or public network.
Unlike isolated adapter tests, the actual service normalizes tool events here.
"""
import asyncio
import unittest

from meo.cloud.api import AgentRunApi, ApiError
from meo.cloud.orchestrator import AgentRunOrchestrator, ResolvedDevice
from meo.cloud.relay import RelayRegistry, RelaySession
from meo.cloud.ws_server import RelayWebSocketServer
from meo.device.agentd import AgentdConfig
from meo.device.protocol import AgentRunStatus, DeviceRegistration
from meo.device.runtime import build_device_runtime
from meo.service.core import AgentServiceCore
from meo.service.request_state import RequestState


class StubAi:
    def __init__(self):
        self.conversations = set()
        self.sent = []
        self.choices = []

    def conversation_exists(self, conversation_id):
        return conversation_id in self.conversations

    def attach_existing_session(self, conversation_id):
        self.conversations.add(conversation_id)

    def send_message(self, conversation_id, text, callbacks):
        self.sent.append((conversation_id, text))
        self.callbacks = callbacks
        callbacks.on_text_delta("Stub AI: awaiting your choice.")
        callbacks.on_tool_event({
            "type": "tool_interaction", "tool_name": "stub.inspect",
            "interaction_id": "legacy-choice",
            "options": [{"index": 7, "title": "Deny"},
                        {"index": 42, "title": "Approve"}],
        })
        return callbacks

    def choose_tool_option(self, handle, legacy_index):
        self.choices.append(legacy_index)
        handle.on_tool_event({"type": "tool_result", "tool_name": "stub.inspect",
                              "display_text": "Approved" if legacy_index == 42 else "Denied"})
        handle.on_text_delta("Stub AI: finished.")
        handle.on_done()

    def cancel(self, handle):
        handle.on_done()


class MemoryStore:
    def __init__(self):
        self.runs = {}
        self.events = {}
        self.devices = []

    async def create_agent_run(self, **values):
        self.runs[values["run_id"]] = dict(values)

    async def update_agent_run(self, *, user_id, run_id, values):
        assert self.runs[run_id]["user_id"] == user_id
        self.runs[run_id].update(values)

    async def get_agent_run(self, *, user_id, run_id):
        run = self.runs.get(run_id)
        return run if run and run["user_id"] == user_id else None

    async def append_agent_event(self, **values):
        key = (values["run_id"], values["seq"])
        if key in self.events:
            return False
        self.events[key] = values
        return True

    async def touch_device(self, **values):
        self.devices.append(values)

    async def list_agent_events(self, *, user_id, run_id, after, limit=100):
        return tuple(event for (rid, seq), event in sorted(self.events.items())
                     if rid == run_id and seq > after and event["user_id"] == user_id)[:limit]


class Resolver:
    async def resolve(self, **kwargs):
        return ResolvedDevice("test-device")


class RemoteServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = StubAi()
        self.service = AgentServiceCore(self.backend)
        self.runtime = build_device_runtime(
            config=AgentdConfig(DeviceRegistration.create("test-device", "Test", ["agent.chat"]),
                                "wss://relay.example.test"),
            secrets=None, connector=None, service=self.service,
        )
        self.store = MemoryStore()
        self.registry = RelayRegistry()
        self.session = RelaySession("test-user", "test-device", ("agent.chat",))
        self.server = RelayWebSocketServer(self.registry, None, self.store)
        test = self

        class DeviceToCloud:
            async def send_json(self, message):
                await test.server._handle_device_message(
                    test.session, "Test", test.cloud_to_device, message,
                )

        class CloudToDevice:
            async def send_json(self, message):
                if message["type"] == "dispatch":
                    test.dispatch = dict(message)
                await test.runtime.agentd.handle_message(test.device_to_cloud, message)

        self.device_to_cloud = DeviceToCloud()
        self.cloud_to_device = CloudToDevice()
        self.registry.register(self.session, self.cloud_to_device)
        self.api = AgentRunApi(store=self.store, relay=self.registry,
                              orchestrator=AgentRunOrchestrator(
                                  store=self.store, relay=self.registry, resolver=Resolver()))

    async def flush_events(self):
        task = asyncio.create_task(self.runtime.events.send_loop(self.device_to_cloud))
        try:
            async with asyncio.timeout(2):
                while self.runtime.events.pending_count:
                    await asyncio.sleep(0)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def start_run(self):
        result = await self.api.create(user_id="test-user", payload={
            "conversation_id": "cloud-conversation", "text": "Inspect using stub AI",
        })
        self.run_id = result["run_id"]
        await self.flush_events()
        self.run = self.runtime.agentd.runs[self.run_id]
        self.assertEqual(self.run.status, AgentRunStatus.AWAITING_APPROVAL)
        self.assertEqual(self.store.runs[self.run_id]["status"], "awaiting_approval")
        self.decision = next(event["payload"]["event"] for event in self.store.events.values()
                             if event["run_id"] == self.run_id and event["event_type"] == "tool_event")
        self.assertEqual(self.decision["type"], "tool.requested")
        self.assertNotEqual(self.decision["decision_id"], "legacy-choice")

    async def test_approve_and_deny_complete_same_service_request(self):
        for option, legacy_index in ((0, 7), (1, 42)):
            with self.subTest(option=option):
                await self.start_run()
                request_id = self.run.local_request_id
                await self.api.decide(user_id="test-user", run_id=self.run_id,
                                      decision_id=self.decision["decision_id"], option_index=option)
                await self.flush_events()
                self.assertEqual(self.backend.choices[-1], legacy_index)
                self.assertEqual(self.run.local_request_id, request_id)
                self.assertEqual(self.run.status, AgentRunStatus.COMPLETED)
                self.assertEqual(self.service.get_request(request_id).state, RequestState.COMPLETED)
                self.assertEqual(self.store.runs[self.run_id]["status"], "completed")

    async def test_cancel_invalidates_service_decision(self):
        await self.start_run()
        await self.api.cancel(user_id="test-user", run_id=self.run_id)
        await self.flush_events()
        self.assertEqual(self.run.status, AgentRunStatus.CANCELLED)
        self.assertEqual(self.store.runs[self.run_id]["status"], "cancelled")
        with self.assertRaises(ApiError):
            await self.api.decide(user_id="test-user", run_id=self.run_id,
                                  decision_id=self.decision["decision_id"], option_index=1)
        self.assertEqual(self.backend.choices, [])

    async def test_reconnect_replays_unacked_events_without_reexecution(self):
        await self.start_run()
        request_id = self.run.local_request_id
        # Lose an event acknowledgement after cloud persistence.
        self.runtime.events.publish(self.run_id, {"type": "text_delta", "text": "in flight"})
        test = self

        class LoseAck:
            async def send_json(self, message):
                await test.server._handle_device_message(test.session, "Test", IgnoreAck(), message)

        class IgnoreAck:
            async def send_json(self, message):
                pass

        task = asyncio.create_task(self.runtime.events.send_loop(LoseAck()))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.runtime.events.pending_count, 1)
        count = len(self.store.events)
        self.runtime.events.requeue_all()
        self.registry.unregister("test-device", self.cloud_to_device)
        self.registry.register(self.session, self.cloud_to_device)
        await self.cloud_to_device.send_json(self.dispatch)
        await self.flush_events()
        self.assertEqual(len(self.backend.sent), 1)
        self.assertEqual(self.run.local_request_id, request_id)
        self.assertEqual(len(self.store.events), count)
        seqs = [seq for run_id, seq in self.store.events if run_id == self.run_id]
        self.assertEqual(seqs, list(range(len(seqs))))

    async def test_wrong_account_cannot_decide_or_cancel(self):
        await self.start_run()
        with self.assertRaises(ApiError) as error:
            await self.api.cancel(user_id="other-user", run_id=self.run_id)
        self.assertEqual(error.exception.status, 404)
        with self.assertRaises(ApiError):
            await self.api.decide(user_id="other-user", run_id=self.run_id,
                                  decision_id=self.decision["decision_id"], option_index=1)
        self.assertEqual(self.backend.choices, [])
