from __future__ import annotations

import asyncio
import unittest

from meo.service.subagent_scheduler import (
    EventHistoryGap,
    MAX_PARALLEL,
    SubagentTaskScheduler,
    TaskAuthorizationError,
)


class SubagentTaskSchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scheduler = SubagentTaskScheduler()
        self.root = self.scheduler.create_root(
            owner_id="owner-a",
            title="Review project",
            project_id="project-1",
            capabilities={"agent.chat", "filesystem.read", "filesystem.write"},
            permission_mode="ask",
        )

    async def test_parallelism_is_bounded_and_outputs_are_owned(self) -> None:
        active = 0
        peak = 0
        entered = asyncio.Event()
        gate = asyncio.Event()

        async def runner(snapshot, cancel, progress):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            progress("started")
            if active == MAX_PARALLEL:
                entered.set()
            await gate.wait()
            active -= 1
            return snapshot.title + " done"

        children = [
            self.scheduler.spawn_child(
                owner_id="owner-a", parent_task_id=self.root.task_id,
                title=f"Analysis {i}", requested_capabilities={"filesystem.read"},
                destination_capabilities={"agent.chat", "filesystem.read"},
                runner=runner,
                execution="remote" if i == 2 else "local",
            ) for i in range(3)
        ]
        await asyncio.wait_for(entered.wait(), 2)
        self.assertEqual(peak, 3)
        self.assertEqual(len({child.task_id for child in children}), 3)
        self.assertTrue(all(child.parent_task_id == self.root.task_id for child in children))
        gate.set()
        root = await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)
        self.assertEqual(root.status, "completed")
        self.assertEqual(peak, 3)
        for child in children:
            done = self.scheduler.snapshot(owner_id="owner-a", task_id=child.task_id)
            self.assertEqual(done.status, "completed")
            self.assertIn("done", done.output)
            self.assertEqual(done.project_id, "project-1")
            self.assertEqual(done.permission_mode, "ask")
        self.assertEqual(self.scheduler.tree(owner_id="owner-a", root_run_id=self.root.task_id)
                         ["children"][2]["execution"], "remote")

    async def test_rejects_capability_escalation_and_relaxed_permission(self) -> None:
        async def noop(*_):
            return "ok"

        def child(**overrides):
            fields = dict(
                owner_id="owner-a", parent_task_id=self.root.task_id,
                title="Child", requested_capabilities={"filesystem.read"},
                destination_capabilities={"filesystem.read"}, runner=noop,
            )
            fields.update(overrides)
            return self.scheduler.spawn_child(**fields)

        with self.assertRaises(TaskAuthorizationError):
            child(requested_capabilities={"credentials.read"})
        with self.assertRaises(TaskAuthorizationError):
            child(destination_capabilities={"agent.chat"})
        with self.assertRaises(TaskAuthorizationError):
            child(permission_mode="full_access")

        safe = child(requested_capabilities=set(), permission_mode="ask")
        self.assertEqual(safe.capabilities, frozenset())
        await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)

    async def test_parent_cancel_propagates_and_is_not_instant_terminal(self) -> None:
        started = asyncio.Event()
        allowed_to_return = asyncio.Event()

        async def cooperative(snapshot, cancellation, report):
            started.set()
            await cancellation.wait()
            await allowed_to_return.wait()
            return "result after cancellation"

        first = self.scheduler.spawn_child(
            owner_id="owner-a", parent_task_id=self.root.task_id,
            title="Long task", requested_capabilities=set(), destination_capabilities=set(),
            runner=cooperative,
        )
        await asyncio.wait_for(started.wait(), 2)
        self.scheduler.cancel(owner_id="owner-a", task_id=self.root.task_id)
        self.assertEqual(self.scheduler.snapshot(owner_id="owner-a", task_id=first.task_id).status,
                         "cancel_requested")
        self.assertEqual(self.scheduler.snapshot(owner_id="owner-a", task_id=self.root.task_id).status,
                         "cancel_requested")
        allowed_to_return.set()
        status = await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)
        self.assertEqual(status.status, "cancelled")
        self.assertEqual(self.scheduler.snapshot(owner_id="owner-a", task_id=first.task_id).status, "cancelled")
        names = [event["type"] for event in self.scheduler.events(
            owner_id="owner-a", root_run_id=self.root.task_id,
        )]
        self.assertIn("task.cancel_requested", names)
        self.assertIn("task.cancelled", names)

    async def test_grandchild_and_max_depth(self) -> None:
        finished_grandchild = asyncio.Event()

        async def grandchild(snapshot, cancellation, report):
            self.assertEqual(snapshot.depth, 2)
            self.assertEqual(snapshot.root_run_id, self.root.task_id)
            report("done")
            finished_grandchild.set()
            return "report"

        async def parent(snapshot, cancellation, report):
            nested = self.scheduler.spawn_child(
                owner_id="owner-a", parent_task_id=snapshot.task_id,
                title="Nested remote", requested_capabilities={"filesystem.read"},
                destination_capabilities={"filesystem.read"}, runner=grandchild, execution="remote",
            )
            with self.assertRaises(ValueError):
                self.scheduler.spawn_child(
                    owner_id="owner-a", parent_task_id=nested.task_id,
                    title="Illegal third level", requested_capabilities=set(),
                    destination_capabilities=set(), runner=grandchild,
                )
            return "parent result"

        child = self.scheduler.spawn_child(
            owner_id="owner-a", parent_task_id=self.root.task_id,
            title="Parent", requested_capabilities={"filesystem.read"},
            destination_capabilities={"filesystem.read"}, runner=parent,
        )
        root = await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)
        self.assertEqual(root.status, "completed")
        self.assertTrue(finished_grandchild.is_set())
        tree = self.scheduler.tree(owner_id="owner-a", root_run_id=self.root.task_id)
        self.assertEqual(tree["children"][0]["task_id"], child.task_id)
        self.assertEqual(tree["children"][0]["children"][0]["execution"], "remote")

    async def test_no_cross_account_reads_cancels_or_event_replay(self) -> None:
        with self.assertRaises(TaskAuthorizationError):
            self.scheduler.snapshot(owner_id="owner-b", task_id=self.root.task_id)
        with self.assertRaises(TaskAuthorizationError):
            self.scheduler.tree(owner_id="owner-b", root_run_id=self.root.task_id)
        with self.assertRaises(TaskAuthorizationError):
            self.scheduler.events(owner_id="owner-b", root_run_id=self.root.task_id)
        with self.assertRaises(TaskAuthorizationError):
            self.scheduler.cancel(owner_id="owner-b", task_id=self.root.task_id)

    async def test_cap_children_per_parent(self) -> None:
        async def noop(*_):
            return "ok"
        for i in range(3):
            self.scheduler.spawn_child(
                owner_id="owner-a", parent_task_id=self.root.task_id,
                title=f"Task {i}", requested_capabilities=set(),
                destination_capabilities=set(), runner=noop,
            )
        with self.assertRaises(ValueError):
            self.scheduler.spawn_child(
                owner_id="owner-a", parent_task_id=self.root.task_id,
                title="Fourth", requested_capabilities=set(), destination_capabilities=set(), runner=noop,
            )
        await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)

    async def test_bounded_events_and_gap_detection(self) -> None:
        scheduler = SubagentTaskScheduler(max_events=3)
        root = scheduler.create_root(owner_id="owner-a", title="Root", capabilities=set())
        async def noisy(snapshot, cancellation, progress):
            for i in range(5):
                progress(f"progress {i}")
            return "result"
        scheduler.spawn_child(
            owner_id="owner-a", parent_task_id=root.task_id, title="Noisy",
            requested_capabilities=set(), destination_capabilities=set(), runner=noisy,
        )
        await scheduler.finish_root(owner_id="owner-a", root_run_id=root.task_id)
        with self.assertRaises(EventHistoryGap):
            scheduler.events(owner_id="owner-a", root_run_id=root.task_id, after=0)
        retained = scheduler.events(owner_id="owner-a", root_run_id=root.task_id, after=5)
        self.assertEqual([event["seq"] for event in retained], sorted(e["seq"] for e in retained))
        self.assertTrue(all(event["root_run_id"] == root.task_id for event in retained))

    async def test_callback_errors_do_not_abort_real_executor_and_output_is_bounded(self) -> None:
        def broken(_event):
            raise RuntimeError("UI failed")
        scheduler = SubagentTaskScheduler(on_event=broken)
        root = scheduler.create_root(owner_id="owner-a", title="Root", capabilities=set())
        async def output(snapshot, cancellation, progress):
            progress("x" * 2000)
            return "a" * 18000
        child = scheduler.spawn_child(
            owner_id="owner-a", parent_task_id=root.task_id, title="Output",
            requested_capabilities=set(), destination_capabilities=set(), runner=output,
        )
        await scheduler.finish_root(owner_id="owner-a", root_run_id=root.task_id)
        self.assertEqual(len(scheduler.snapshot(owner_id="owner-a", task_id=child.task_id).output), 16000)
        self.assertTrue(all(len(e["detail"]) <= 600 for e in scheduler.events(
            owner_id="owner-a", root_run_id=root.task_id,
        )))

    async def test_failed_child_reports_failure_without_exposing_exception(self) -> None:
        async def fails(snapshot, cancellation, progress):
            raise ValueError("SECRET_TOKEN_EXAMPLE")
        child = self.scheduler.spawn_child(
            owner_id="owner-a", parent_task_id=self.root.task_id,
            title="Failed", requested_capabilities=set(), destination_capabilities=set(),
            runner=fails,
        )
        root = await self.scheduler.finish_root(owner_id="owner-a", root_run_id=self.root.task_id)
        self.assertEqual(root.status, "failed")
        self.assertEqual(self.scheduler.snapshot(owner_id="owner-a", task_id=child.task_id).status, "failed")
        self.assertNotIn("SECRET_TOKEN_EXAMPLE", repr(self.scheduler.events(
            owner_id="owner-a", root_run_id=self.root.task_id,
        )))

if __name__ == "__main__":
    unittest.main()
