from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import ConversationMessage
from meo.service.core import AgentServiceCore
from meo.service.resources import ConversationResourceStore


class ResourceBackend:
    def __init__(self):
        self.conversations = set()

    def list_conversations(self): return [{"id": item} for item in sorted(self.conversations)]
    def create_conversation(self):
        cid = f"conversation:{len(self.conversations) + 1}"
        self.conversations.add(cid)
        return cid
    def conversation_exists(self, conversation_id): return conversation_id in self.conversations
    def list_messages(self, _conversation_id): return [ConversationMessage("assistant", "ready")]
    def send_message(self, _conversation_id, _text, _callbacks): return object()
    def choose_tool_option(self, _execution_handle, _legacy_option_index): pass
    def cancel(self, _execution_handle): pass
    def list_models(self): return []
    def set_model(self, _conversation_id, _model_id): pass
    def list_skills(self): return []
    def set_skill_enabled(self, _skill_id, _enabled): pass
    def list_mcp_servers(self): return []


class ResourceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backend = ResourceBackend()
        service = AgentServiceCore(
            self.backend,
            resource_store=ConversationResourceStore(self.temp.name, max_resource_bytes=64),
        )
        self.server = create_http_server(service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.temp.cleanup()

    def json_request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def create_conversation(self):
        return self.json_request("POST", "/v1/conversations")[1]["conversation_id"]

    def test_binary_attachment_reserve_upload_and_list(self):
        cid = self.create_conversation()
        content = b"hello-file"
        status, reserved = self.json_request(
            "POST",
            f"/v1/conversations/{cid}/resources",
            {
                "kind": "attachment",
                "name": "notes.txt",
                "mime_type": "text/plain",
                "size_bytes": len(content),
            },
        )
        self.assertEqual(status, 201)
        resource = reserved["resource"]
        self.assertEqual(resource["state"], "uploading")
        self.assertEqual(resource["sha256"], "")

        resource_id = urllib.parse.quote(resource["resource_id"], safe="")
        request = urllib.request.Request(
            self.base + f"/v1/conversations/{cid}/resources/{resource_id}/content",
            data=content,
            method="PUT",
            headers={"Content-Type": "application/octet-stream"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
            uploaded = json.loads(response.read())
        self.assertEqual(uploaded["resource"]["state"], "ready")
        self.assertEqual(len(uploaded["resource"]["sha256"]), 64)

        _, listing = self.json_request("GET", f"/v1/conversations/{cid}/resources")
        self.assertEqual(listing["resources"], [uploaded["resource"]])

    def test_upload_rejects_size_mismatch_and_keeps_reservation(self):
        cid = self.create_conversation()
        _, reserved = self.json_request(
            "POST",
            f"/v1/conversations/{cid}/resources",
            {
                "kind": "image",
                "name": "shot.png",
                "mime_type": "image/png",
                "size_bytes": 8,
            },
        )
        resource_id = urllib.parse.quote(reserved["resource"]["resource_id"], safe="")
        request = urllib.request.Request(
            self.base + f"/v1/conversations/{cid}/resources/{resource_id}/content",
            data=b"short",
            method="PUT",
            headers={"Content-Type": "application/octet-stream"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 400)
        _, listing = self.json_request("GET", f"/v1/conversations/{cid}/resources")
        self.assertEqual(listing["resources"][0]["state"], "uploading")

    def test_reservation_rejects_oversize_before_upload(self):
        cid = self.create_conversation()
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request(
                "POST",
                f"/v1/conversations/{cid}/resources",
                {
                    "kind": "attachment",
                    "name": "too-large.bin",
                    "mime_type": "application/octet-stream",
                    "size_bytes": 65,
                },
            )
        self.assertEqual(raised.exception.code, 413)

    def test_put_requires_binary_content_type(self):
        cid = self.create_conversation()
        _, reserved = self.json_request(
            "POST",
            f"/v1/conversations/{cid}/resources",
            {
                "kind": "attachment",
                "name": "notes.txt",
                "mime_type": "text/plain",
                "size_bytes": 1,
            },
        )
        resource_id = urllib.parse.quote(reserved["resource"]["resource_id"], safe="")
        request = urllib.request.Request(
            self.base + f"/v1/conversations/{cid}/resources/{resource_id}/content",
            data=b"x",
            method="PUT",
            headers={"Content-Type": "text/plain"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 415)


if __name__ == "__main__":
    unittest.main()
