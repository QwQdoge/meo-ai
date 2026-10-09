from __future__ import annotations

import unittest

from meo.device.protocol import AgentRunBinding, AgentRunStatus, DeviceRegistration


class DeviceRegistrationTests(unittest.TestCase):
    def test_create_normalizes_and_validates(self) -> None:
        registration = DeviceRegistration.create(
            " legion ",
            " Legion Y9000X ",
            ["agent.chat", "agent.workspace"],
        )

        self.assertEqual(registration.device_id, "legion")
        self.assertEqual(registration.display_name, "Legion Y9000X")
        self.assertEqual(
            registration.capabilities,
            ("agent.chat", "agent.workspace"),
        )

    def test_duplicate_capability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DeviceRegistration.create(
                "legion",
                "Legion",
                ["agent.chat", "agent.chat"],
            )


class AgentRunBindingTests(unittest.TestCase):
    def test_local_request_binding_is_idempotent_but_not_replaceable(self) -> None:
        run = AgentRunBinding("run-1", "conversation-1", "legion")

        run.bind_local_request("request-1")
        run.bind_local_request("request-1")
        self.assertEqual(run.require_local_request(), "request-1")

        with self.assertRaises(ValueError):
            run.bind_local_request("request-2")

    def test_reconnect_event_replay_is_idempotent(self) -> None:
        run = AgentRunBinding("run-1", "conversation-1", "legion")

        self.assertTrue(run.observe_event(0))
        self.assertTrue(run.observe_event(1))
        self.assertFalse(run.observe_event(1))
        self.assertFalse(run.observe_event(0))
        self.assertEqual(run.last_event_seq, 1)

    def test_terminal_status_is_explicit(self) -> None:
        run = AgentRunBinding(
            "run-1",
            "conversation-1",
            "legion",
            status=AgentRunStatus.COMPLETED,
        )
        self.assertTrue(run.terminal)

    def test_invalid_event_sequence_is_rejected(self) -> None:
        run = AgentRunBinding("run-1", "conversation-1", "legion")
        for value in (-1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    run.observe_event(value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
