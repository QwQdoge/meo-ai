from __future__ import annotations

import asyncio
import unittest

from meo.device.events import RelayEventQueue


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class RelayEventQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_assigns_ordered_per_run_sequence(self) -> None:
        queue = RelayEventQueue("legion")
        queue.publish("run-1", {"type": "text_delta", "text": "a"})
        queue.publish("run-1", {"type": "text_delta", "text": "b"})
        connection = FakeConnection()
        task = asyncio.create_task(queue.send_loop(connection))
        try:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual([event["seq"] for event in connection.sent], [0, 1])
        self.assertEqual(queue.pending_count, 2)

    async def test_acknowledge_removes_only_exact_event(self) -> None:
        queue = RelayEventQueue("legion")
        queue.publish("run-1", {"type": "done", "status": "completed"})
        self.assertTrue(queue.acknowledge("run-1", 0))
        self.assertFalse(queue.acknowledge("run-1", 0))
        self.assertEqual(queue.pending_count, 0)

    async def test_requeue_all_replays_only_unacked_events_once(self) -> None:
        queue = RelayEventQueue("legion")
        queue.publish("run-1", {"type": "text_delta", "text": "a"})
        queue.publish("run-1", {"type": "text_delta", "text": "b"})
        queue.acknowledge("run-1", 0)
        queue.requeue_all()

        connection = FakeConnection()
        task = asyncio.create_task(queue.send_loop(connection))
        try:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(len(connection.sent), 1)
        self.assertEqual(connection.sent[0]["seq"], 1)


if __name__ == "__main__":
    unittest.main()
