from __future__ import annotations

from dataclasses import dataclass
import asyncio
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

    def publish(self, run_id: str, event: dict) -> None:
        run_id = str(run_id).strip()
        if not run_id:
            raise ValueError("run_id is required")
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event type is required")
        seq = self._next_seq.get(run_id, 0)
        self._next_seq[run_id] = seq + 1
        payload = {key: value for key, value in event.items() if key != "type"}
        pending = PendingRelayEvent(
            run_id=run_id,
            seq=seq,
            event_type=event_type.strip(),
            payload=payload,
        )
        key = (run_id, seq)
        self._pending[key] = pending
        self._ready.put_nowait(key)

    def acknowledge(self, run_id: str, seq: int) -> bool:
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError("seq must be a non-negative integer")
        return self._pending.pop((run_id, seq), None) is not None

    def requeue_all(self) -> None:
        while True:
            try:
                self._ready.get_nowait()
            except asyncio.QueueEmpty:
                break
        for key in sorted(self._pending):
            self._ready.put_nowait(key)

    async def send_loop(self, connection) -> None:
        while True:
            key = await self._ready.get()
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
        return len(self._pending)
