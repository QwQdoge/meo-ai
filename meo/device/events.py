from __future__ import annotations

from dataclasses import dataclass
import asyncio
import threading
from typing import Any


@dataclass(frozen=True)
class PendingRelayEvent:
    run_id: str
    seq: int
    event_type: str
    payload: dict[str, Any]


class RelayEventQueue:
    """Assign ordered per-run sequence numbers and retain events until acked."""

    def __init__(self, device_id: str) -> None:
        if not device_id.strip():
            raise ValueError("device_id is required")
        self.device_id = device_id.strip()
        self._next_seq: dict[str, int] = {}
        self._pending: dict[tuple[str, int], PendingRelayEvent] = {}
        self._ready: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def publish(self, run_id: str, event: dict) -> None:
        run_id = str(run_id).strip()
        if not run_id:
            raise ValueError("run_id is required")
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event type is required")
        payload = {key: value for key, value in event.items() if key != "type"}
        # Provider callbacks may arrive on worker threads. asyncio.Queue must
        # only be awakened on the relay loop, with sequence assignment serialized.
        with self._lock:
            seq = self._next_seq.get(run_id, 0)
            self._next_seq[run_id] = seq + 1
            pending = PendingRelayEvent(run_id, seq, event_type.strip(), payload)
            key = (run_id, seq)
            self._pending[key] = pending
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._ready.put_nowait, key)
            else:
                self._ready.put_nowait(key)

    def acknowledge(self, run_id: str, seq: int) -> bool:
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError("seq must be a non-negative integer")
        with self._lock:
            return self._pending.pop((run_id, seq), None) is not None

    def requeue_all(self) -> None:
        while True:
            try:
                self._ready.get_nowait()
            except asyncio.QueueEmpty:
                break
        with self._lock:
            for key in sorted(self._pending):
                self._ready.put_nowait(key)

    async def send_loop(self, connection) -> None:
        with self._lock:
            self._loop = asyncio.get_running_loop()
        while True:
            key = await self._ready.get()
            with self._lock:
                pending = self._pending.get(key)
            if pending is None:
                continue
            await connection.send_json(
                {
                    "type": "event",
                    "device_id": self.device_id,
                    "run_id": pending.run_id,
                    "seq": pending.seq,
                    "event_type": pending.event_type,
                    "payload": pending.payload,
                }
            )

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)
