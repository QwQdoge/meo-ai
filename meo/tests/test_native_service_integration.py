"""Production QML/C++ client -> real HTTP/SSE service -> deterministic AI stub."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from meo.runtime.native_http_transport import create_native_http_server
from meo.service.core import AgentServiceCore
from meo.tests.test_http_transport import FakeBackend, FakeHandle


class StreamingStubAi(FakeBackend):
    def send_message(self, conversation_id, text, callbacks):
        handle = FakeHandle()
        self.handles.append(handle)

        def respond():
            callbacks.on_text_delta("This is a deterministic stub AI. ")
            if text == "cancel stub":
                if handle.cancel.wait(5):
                    callbacks.on_done()
                else:
                    callbacks.on_error("Stub cancellation was not received")
                return
            callbacks.on_tool_event({"type": "tool_result", "tool_name": "stub.search",
                                     "display_text": "Synthetic search result; no network request."})
            callbacks.on_tool_event({
                "type": "response_meta", "provider": "stub", "model": "offline-test",
                "usage": {"input_tokens": 5, "output_tokens": 8, "total_tokens": 13},
                "activity": {"search": {"used": True, "queries": ["synthetic query"], "result_count": 0}},
            })
            callbacks.on_text_delta("No provider credentials were used.")
            callbacks.on_done()

        threading.Thread(target=respond, daemon=True).start()
        return handle


@unittest.skipUnless(os.environ.get("MEO_AI_NATIVE_TEST_CLIENT"), "CTest native client executable required")
class NativeServiceIntegrationTests(unittest.TestCase):
    def run_client(self, prompt, *options):
        backend = StreamingStubAi()
        service = AgentServiceCore(backend)
        server = create_native_http_server(service, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as config:
                env = dict(os.environ, XDG_CONFIG_HOME=config,
                           QT_QPA_PLATFORM="offscreen", QSG_RHI_BACKEND="software",
                           QT_FORCE_STDERR_LOGGING="1",
                           MEO_AI_SERVICE_ENDPOINT=f"http://127.0.0.1:{server.server_port}")
                result = subprocess.run(
                    [os.environ["MEO_AI_NATIVE_TEST_CLIENT"], "--prompt", prompt, *options],
                    env=env, text=True, capture_output=True, timeout=25,
                )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["passed"], report)
            self.assertEqual(len(backend.handles), 1)
            return report, service
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_qml_stream_tool_and_response_details_metadata(self):
        report, service = self.run_client("complete stub", "--require-tool", "--require-meta")
        self.assertIn("deterministic stub AI", report["answer"])
        self.assertEqual(report["tool_events"][0]["type"], "tool.completed")
        self.assertEqual(report["metadata_events"][0]["usage"]["total_tokens"], 13)
        self.assertEqual(service.get_agent_state()["request_states"]["completed"], 1)

    def test_qml_stop_cancels_original_service_request(self):
        report, service = self.run_client("cancel stub", "--cancel-after-delta")
        self.assertTrue(report["cancel_requested"])
        self.assertEqual(service.get_agent_state()["request_states"]["cancelled"], 1)


if __name__ == "__main__":
    unittest.main()
