from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
from typing import Any, Iterator


class JournalGapError(ValueError):
    """Raised when a reconnect cursor predates retained in-memory events."""


@dataclass(frozen=True)
class JournalSnapshot:
    oldest_seq: int
    latest_seq: int
    closed: bool


class RequestEventJournal:
    """Bounded, multi-subscriber in-memory request event journal.

    The journal supports transport reconnect while one AgentService process is
    alive. It is deliberately not durable execution state: service restart does
    not replay an uncertain model/tool request.
    """

    def __init__(self, max_events: int = 512) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._next_seq = 1
        self._closed = False
        self._condition = threading.Condition()

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._condition:
            if self._closed:
                raise RuntimeError("cannot append to a closed event journal")
            value = dict(event)
            value["seq"] = self._next_seq
            self._next_seq += 1
            self._events.append(value)
            self._condition.notify_all()
            return dict(value)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def snapshot(self) -> JournalSnapshot:
        with self._condition:
            oldest = self._events[0]["seq"] if self._events else self._next_seq
            return JournalSnapshot(oldest, self._next_seq - 1, self._closed)

    def subscribe(self, after_seq: int = 0) -> Iterator[dict[str, Any]]:
        if not isinstance(after_seq, int) or isinstance(after_seq, bool) or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        cursor = after_seq
        while True:
            with self._condition:
                oldest = self._events[0]["seq"] if self._events else self._next_seq
                if cursor and cursor < oldest - 1:
                    raise JournalGapError(
                        f"event cursor {cursor} predates retained journal starting at {oldest}"
                    )
                available = [event for event in self._events if event["seq"] > cursor]
                if available:
                    cursor = available[-1]["seq"]
                elif self._closed:
                    return
                else:
                    self._condition.wait()
                    continue
            for event in available:
                yield dict(event)
