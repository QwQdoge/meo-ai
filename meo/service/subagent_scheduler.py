from __future__ import annotations

"""Bounded, headless scheduler for trusted AgentService-owned child tasks.

An injected runner does the real work. This module does NOT interpret model
instructions as permission, choose devices, or run shell commands. All IDs,
task relationships, scheduling slots and event sequences are service-owned.
The registry is in-memory; a durable store/relay adapter is a separate step.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal
from uuid import uuid4


MAX_DEPTH = 2  # root=0, child=1, grandchild=2
MAX_PARALLEL = 3
MAX_CHILDREN = 3
MAX_TOTAL_TASKS = 13
MAX_OUTPUT_CHARS = 16000
MAX_EVENT_CHARS = 600

Execution = Literal["local", "remote", "cloud"]
TERMINAL = frozenset({"completed", "failed", "cancelled"})
_PERMISSION_ORDER = {"ask": 0, "smart": 1, "full_access": 2}


class TaskAuthorizationError(PermissionError):
    """The requested task is outside its trusted parent's effective grants."""


class EventHistoryGap(ValueError):
    """An event cursor predates the bounded local event journal."""


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    root_run_id: str
    parent_task_id: str | None
    owner_id: str
    project_id: str | None
    title: str
    depth: int
    relation: str
    execution: Execution
    capabilities: frozenset[str]
    permission_mode: str
    status: str
    output: str = ""


@dataclass
class _Task:
    task_id: str
    root_run_id: str
    parent_task_id: str | None
    owner_id: str
    project_id: str | None
    title: str
    depth: int
    execution: Execution
    capabilities: frozenset[str]
    permission_mode: str
    status: str = "queued"
    output: str = ""
    children: list[str] = field(default_factory=list)
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            task_id=self.task_id, root_run_id=self.root_run_id,
            parent_task_id=self.parent_task_id, owner_id=self.owner_id,
            project_id=self.project_id, title=self.title, depth=self.depth,
            relation="root" if self.parent_task_id is None else "subagent",
            execution=self.execution, capabilities=self.capabilities,
            permission_mode=self.permission_mode, status=self.status,
            output=self.output,
        )


# A runner must check the cancellation signal before side effects, use the
# provided capabilities as an upper bound, and enforce backend/device policy.
# It may report progress without being allowed to mutate scheduler state.
TaskRunner = Callable[[TaskSnapshot, asyncio.Event, Callable[[str], None]], Awaitable[str]]


class SubagentTaskScheduler:
    """Execute bounded child tasks with explicit ownership and replayable events.

    The event callback is a presentation hook, NOT durable persistence. The
    actual device/service executor remains responsible for tool authorization,
    approval and terminal acknowledgement.
    """

    def __init__(
        self,
        *,
        max_parallel: int = MAX_PARALLEL,
        max_events: int = 512,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        if not 1 <= max_parallel <= MAX_PARALLEL:
            raise ValueError("max_parallel must be between 1 and 3")
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._slots = asyncio.Semaphore(max_parallel)
        self._events_limit = max_events
        self._events: dict[str, deque[dict]] = {}
        self._next_seq: dict[str, int] = {}
        self._tasks: dict[str, _Task] = {}
        self._jobs: dict[str, asyncio.Task[None]] = {}
        self._on_event = on_event

    def _owned(self, owner_id: str, task_id: str) -> _Task:
        task = self._tasks.get(task_id)
        if task is None or task.owner_id != owner_id:
            raise TaskAuthorizationError("task not found")
        return task

    @staticmethod
    def _title(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 3500:
            raise ValueError("invalid task title")
        return value.strip()[:3500]

    @staticmethod
    def _permission(mode: str) -> None:
        if mode not in _PERMISSION_ORDER:
            raise ValueError("invalid permission mode")

    def _emit(self, task: _Task, kind: str, *, detail: str = "") -> None:
        root = task.root_run_id
        seq = self._next_seq[root]
        self._next_seq[root] = seq + 1
        event = {
            "schema": "org.meo.agent-task-activity/v1",
            "seq": seq, "root_run_id": root,
            "task_id": task.task_id,
            "parent_task_id": task.parent_task_id,
            "type": kind, "status": task.status,
            "execution": task.execution,
            "detail": str(detail)[:MAX_EVENT_CHARS],
        }
        self._events[root].append(event)
        if self._on_event is not None:
            try:
                self._on_event(dict(event))
            except Exception:
                # UI subscribers must not interrupt trusted execution.
                pass

    def create_root(
        self, *, owner_id: str, title: str,
        capabilities: frozenset[str] | set[str],
        project_id: str | None = None,
        permission_mode: str = "ask",
        execution: Execution = "local",
    ) -> TaskSnapshot:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be supplied by trusted service")
        self._permission(permission_mode)
        if execution not in ("local", "remote", "cloud"):
            raise ValueError("invalid execution location")
        title = self._title(title)
        root_id = str(uuid4())
        root = _Task(
            task_id=root_id, root_run_id=root_id, parent_task_id=None,
            owner_id=owner_id, project_id=project_id, title=title,
            depth=0, execution=execution,
            capabilities=frozenset(capabilities), permission_mode=permission_mode,
            status="running",
        )
        self._tasks[root_id] = root
        self._events[root_id] = deque(maxlen=self._events_limit)
        self._next_seq[root_id] = 1
        self._emit(root, "task.created")
        self._emit(root, "task.started")
        return root.snapshot()

    def spawn_child(
        self, *, owner_id: str, parent_task_id: str, title: str,
        requested_capabilities: frozenset[str] | set[str],
        destination_capabilities: frozenset[str] | set[str],
        runner: TaskRunner,
        execution: Execution = "local",
        permission_mode: str | None = None,
    ) -> TaskSnapshot:
        parent = self._owned(owner_id, parent_task_id)
        if parent.status != "running" or parent.cancelled.is_set():
            raise RuntimeError("parent is not accepting children")
        if parent.depth >= MAX_DEPTH:
            raise ValueError("maximum subagent depth exceeded")
        if len(parent.children) >= MAX_CHILDREN:
            raise ValueError("maximum children per parent exceeded")
        if sum(x.root_run_id == parent.root_run_id for x in self._tasks.values()) >= MAX_TOTAL_TASKS:
            raise ValueError("maximum tasks per run exceeded")
        if execution not in ("local", "remote", "cloud"):
            raise ValueError("invalid execution location")
        title = self._title(title)
        mode = permission_mode or parent.permission_mode
        self._permission(mode)
        if _PERMISSION_ORDER[mode] > _PERMISSION_ORDER[parent.permission_mode]:
            raise TaskAuthorizationError("child cannot relax its parent's permission mode")
        requested = frozenset(requested_capabilities)
        destination = frozenset(destination_capabilities)
        if not requested.issubset(parent.capabilities) or not requested.issubset(destination):
            raise TaskAuthorizationError("child capability escalation blocked")
        if not callable(runner):
            raise ValueError("runner must be a trusted callable")

        task_id = str(uuid4())
        child = _Task(
            task_id=task_id, root_run_id=parent.root_run_id,
            parent_task_id=parent.task_id, owner_id=parent.owner_id,
            project_id=parent.project_id, title=title, depth=parent.depth + 1,
            execution=execution, capabilities=requested, permission_mode=mode,
        )
        self._tasks[task_id] = child
        parent.children.append(task_id)
        self._emit(child, "task.created")
        self._jobs[task_id] = asyncio.create_task(self._execute(child, runner))
        return child.snapshot()

    async def _execute(self, child: _Task, runner: TaskRunner) -> None:
        async with self._slots:
            if child.cancelled.is_set():
                child.status = "cancelled"
                self._emit(child, "task.cancelled")
                return
            child.status = "running"
            self._emit(child, "task.started")

            def progress(detail: str) -> None:
                if child.status == "running" and not child.cancelled.is_set():
                    self._emit(child, "task.progress", detail=detail)

            try:
                output = await runner(child.snapshot(), child.cancelled, progress)
                if child.cancelled.is_set():
                    child.status = "cancelled"
                    self._emit(child, "task.cancelled")
                else:
                    child.output = str(output)[:MAX_OUTPUT_CHARS]
                    child.status = "completed"
                    self._emit(child, "task.completed")
            except asyncio.CancelledError:
                # A trusted runner may be interrupted on scheduler shutdown.
                child.status = "cancelled"
                self._emit(child, "task.cancelled")
                raise
            except Exception:
                if child.cancelled.is_set():
                    child.status = "cancelled"
                    self._emit(child, "task.cancelled")
                else:
                    child.status = "failed"
                    self._emit(child, "task.failed", detail="executor_failed")

    def cancel(self, *, owner_id: str, task_id: str) -> None:
        start = self._owned(owner_id, task_id)
        stack = [start.task_id]
        while stack:
            task = self._tasks[stack.pop()]
            stack.extend(task.children)
            if task.status in TERMINAL or task.cancelled.is_set():
                continue
            task.cancelled.set()
            task.status = "cancel_requested"
            self._emit(task, "task.cancel_requested")
        # Do not pretend remote work is cancelled here: only executor exit can
        # confirm terminal cancellation. The signal propagates to child runners.

    async def wait(self, *, owner_id: str, task_id: str) -> TaskSnapshot:
        task = self._owned(owner_id, task_id)
        if task_id in self._jobs:
            await self._jobs[task_id]
        return task.snapshot()

    async def finish_root(self, *, owner_id: str, root_run_id: str) -> TaskSnapshot:
        root = self._owned(owner_id, root_run_id)
        if root.parent_task_id is not None:
            raise ValueError("must finish a root task")
        # A child runner may spawn its own children. Await the entire bounded
        # tree rather than snapshotting jobs only once.
        while True:
            jobs = [job for task_id, job in self._jobs.items()
                    if self._tasks[task_id].root_run_id == root_run_id and not job.done()]
            if not jobs:
                break
            await asyncio.gather(*jobs, return_exceptions=True)
        if root.status in TERMINAL:
            return root.snapshot()
        descendants = [task for task in self._tasks.values()
                       if task.root_run_id == root_run_id and task.task_id != root_run_id]
        if root.cancelled.is_set():
            root.status = "cancelled"
            kind = "task.cancelled"
        elif any(task.status == "failed" for task in descendants):
            root.status = "failed"
            kind = "task.failed"
        else:
            root.status = "completed"
            kind = "task.completed"
        self._emit(root, kind)
        return root.snapshot()

    def snapshot(self, *, owner_id: str, task_id: str) -> TaskSnapshot:
        return self._owned(owner_id, task_id).snapshot()

    def tree(self, *, owner_id: str, root_run_id: str) -> dict:
        root = self._owned(owner_id, root_run_id)
        if root.parent_task_id is not None:
            raise ValueError("root_run_id required")

        def render(task: _Task) -> dict:
            return {
                "task_id": task.task_id, "parent_task_id": task.parent_task_id,
                "root_run_id": task.root_run_id, "relation": "root" if task.parent_task_id is None else "subagent",
                "execution": task.execution, "status": task.status, "title": task.title,
                "depth": task.depth,
                "children": [render(self._tasks[child]) for child in task.children],
            }

        return render(root)

    def events(self, *, owner_id: str, root_run_id: str, after: int = 0, limit: int = 100) -> list[dict]:
        root = self._owned(owner_id, root_run_id)
        if root.parent_task_id is not None:
            raise ValueError("root_run_id required")
        if not isinstance(after, int) or isinstance(after, bool) or after < 0:
            raise ValueError("invalid cursor")
        if not 1 <= limit <= 100:
            raise ValueError("invalid event limit")
        retained = self._events[root_run_id]
        if retained and after < retained[0]["seq"] - 1:
            raise EventHistoryGap("activity cursor predates retained events")
        return [dict(event) for event in retained if event["seq"] > after][:limit]
