from __future__ import annotations

from typing import Dict
from uuid import uuid4

from .request_state import RequestLifecycle


class RequestRegistry:
    """In-memory Phase B request ownership with service-generated identities."""

    def __init__(self) -> None:
        self._requests: Dict[str, RequestLifecycle] = {}

    def create(self) -> RequestLifecycle:
        request = RequestLifecycle(request_id=f"request:{uuid4()}")
        self._requests[request.request_id] = request
        return request

    def get(self, request_id: str) -> RequestLifecycle:
        try:
            return self._requests[request_id]
        except KeyError as exc:
            raise ValueError("unknown request_id") from exc

    def contains(self, request_id: str) -> bool:
        return request_id in self._requests
