"""HTTP + WebSocket + production TS web client, with stub AI/auth/database.

Uses loopback only. This tests auth enforcement, not live Account verification.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from meo.cloud.account_auth import AccountIdentity
from meo.cloud.enrollment import DeviceCredentialClaims
from meo.cloud.server import CloudServerConfig, build_application
from meo.device.agentd import AgentdConfig
from meo.device.protocol import DeviceRegistration
from meo.device.runtime import build_device_runtime
from meo.service.core import AgentServiceCore
from meo.tests.test_remote_service_integration import MemoryStore, StubAi


class TestAccountVerifier:
    async def verify(self, token):
        if token not in {"test-user", "other-user"}:
            raise PermissionError("invalid test token")
        return AccountIdentity(token)


class TestDeviceVerifier:
    async def verify(self, token):
        if token != "test-device-token":
            raise PermissionError("invalid test device token")
        now = datetime.now(timezone.utc)
        return DeviceCredentialClaims(
            "test-credential", "test-user", "test-device",
            frozenset({"relay.connect", "agent.receive"}),
            now - timedelta(minutes=1), now + timedelta(hours=1),
        )


@unittest.skipUnless(os.environ.get("MEO_AI_RUN_CLOUD_NETWORK_TEST") == "1",
                     "opt-in aiohttp and Node 24+ required")
class CloudNetworkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import ClientSession, web
        self.store = MemoryStore()
        self.backend = StubAi()
        self.service = AgentServiceCore(self.backend)
        self.runtime = build_device_runtime(
            config=AgentdConfig(DeviceRegistration.create("test-device", "Test", ["agent.chat"]),
                                "wss://relay.example.test"),
            secrets=None, connector=None, service=self.service,
        )
        with patch("meo.cloud.server.SupabaseRestStore", return_value=self.store), \
             patch("meo.cloud.server.SupabaseAccountTokenVerifier", return_value=TestAccountVerifier()), \
             patch("meo.cloud.server.DeviceBearerVerifier", return_value=TestDeviceVerifier()):
            app = build_application(CloudServerConfig("https://example.test", "test", "test"))
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.http = ClientSession()
        self.ws = await self.http.ws_connect(
            self.base + "/v1/device-relay", protocols=["meo-agentd.v1"],
            headers={"Authorization": "Bearer test-device-token"},
        )
        test = self

        class DeviceSocket:
            async def send_json(self, payload):
                await test.ws.send_json({"protocol_version": 1, **payload})

            async def receive_json(self):
                return await test.ws.receive_json()

        self.agent_task = asyncio.create_task(self.runtime.agentd._serve(DeviceSocket()))
        # Wait for authenticated hello registration before HTTP dispatch.
        async with asyncio.timeout(2):
            while not self.store.devices:
                await asyncio.sleep(0)

    async def asyncTearDown(self):
        self.agent_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.agent_task
        await self.ws.close()
        await self.http.close()
        await self.runner.cleanup()

    async def run_browser(self, mode):
        module = (Path(__file__).resolve().parents[1] / "web/agent-client.ts").as_uri()
        script = '''
import { MeoAgentClient } from MODULE;
const base = process.argv[1];
const mode = process.argv[2];
const client = new MeoAgentClient({cloudBaseUrl: base, eventsUrl: base + "/v1/agent-runs/events",
                                 getAccessToken: async () => "test-user"});
const {runId} = await client.createRun({conversationId: "cloud-conversation", text: "Stub AI"});
const events = [];
for await (const event of client.events(runId)) {
  events.push(event);
  if (event.event === "tool_event" && event.data.event.type === "tool.requested") {
    if (mode === "reconnect") break;
    if (mode === "cancel") await client.cancelRun(runId);
    else await client.decide(runId, event.data.event.decision_id, mode === "approve" ? 1 : 0);
  }
}
if (mode === "reconnect") {
  const pending = events.at(-1);
  await client.decide(runId, pending.data.event.decision_id, 1);
  for await (const event of client.events(runId, pending.id)) events.push(event);
}
const last = events.at(-1);
const replay = [];
for await (const event of client.events(runId, last.id)) replay.push(event);
console.log(JSON.stringify({runId, events, replay}));
'''.replace("MODULE", json.dumps(module))
        proc = await asyncio.create_subprocess_exec(
            shutil.which("node"), "--input-type=module", "-e", script, self.base, mode,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        self.assertEqual(proc.returncode, 0, stderr.decode())
        return json.loads(stdout)

    async def test_web_client_approval_denial_cancel_and_cursor_replay(self):
        for mode in ("approve", "deny", "cancel", "reconnect"):
            with self.subTest(mode=mode):
                report = await self.run_browser(mode)
                events = report["events"]
                self.assertEqual([e["id"] for e in events], list(range(len(events))))
                self.assertEqual(events[-1]["event"], "done")
                self.assertEqual(events[-1]["data"]["status"], "cancelled" if mode == "cancel" else "completed")
                self.assertEqual(report["replay"], [])
        self.assertEqual(len(self.backend.sent), 4)
        self.assertEqual(self.backend.choices, [42, 7, 42])

    async def test_http_event_ownership_and_device_auth_reject_invalid_callers(self):
        report = await self.run_browser("approve")
        url = self.base + "/v1/agent-runs/events?run_id=" + report["runId"]
        for token, expected in ((None, 401), ("invalid", 401), ("other-user", 404)):
            headers = {} if token is None else {"Authorization": f"Bearer {token}"}
            async with self.http.get(url, headers=headers) as response:
                self.assertEqual(response.status, expected)
        async with self.http.get(self.base + "/v1/device-relay") as response:
            self.assertEqual(response.status, 401)

    async def test_terminal_replay_drains_pages_and_reports_cursor_gaps(self):
        self.store.runs["paged-run"] = {
            "user_id": "test-user", "status": "completed", "last_event_seq": 104,
        }
        for seq in range(105):
            await self.store.append_agent_event(user_id="test-user", run_id="paged-run", seq=seq,
                                               event_type="text_delta", payload={"text": str(seq)})
        url = self.base + "/v1/agent-runs/events?run_id=paged-run"
        headers = {"Authorization": "Bearer test-user"}
        async with self.http.get(url, headers=headers) as response:
            text = await response.text()
            self.assertEqual(response.status, 200)
            self.assertEqual(sum(line.startswith("id:") for line in text.splitlines()), 105)
        del self.store.events[("paged-run", 0)]
        async with self.http.get(url, headers=headers) as response:
            self.assertIn('"code":"event_gap"', await response.text())
        async with self.http.get(url + "&after=-2", headers=headers) as response:
            self.assertEqual(response.status, 400)
        self.assertEqual(self.backend.sent, [])


if __name__ == "__main__":
    unittest.main()
