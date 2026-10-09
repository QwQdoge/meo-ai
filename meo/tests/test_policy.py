from __future__ import annotations

import unittest

from meo.cloud.policy import (
    PermissionMode,
    RiskLevel,
    decide_permission,
)


class PermissionPolicyTests(unittest.TestCase):
    def test_smart_allows_read_only_work_without_prompt(self) -> None:
        decision = decide_permission(
            requested_capabilities=frozenset({"agent.chat", "filesystem.read"}),
        )
        self.assertEqual(decision.risk, RiskLevel.LOW)
        self.assertFalse(decision.requires_approval)

    def test_smart_requires_approval_for_high_risk_effect(self) -> None:
        decision = decide_permission(
            requested_capabilities=frozenset({"agent.chat", "git.push"}),
        )
        self.assertEqual(decision.risk, RiskLevel.HIGH)
        self.assertTrue(decision.requires_approval)

    def test_ask_always_requires_approval(self) -> None:
        decision = decide_permission(
            requested_capabilities=frozenset({"filesystem.read"}),
            mode=PermissionMode.ASK,
        )
        self.assertTrue(decision.requires_approval)

    def test_full_access_does_not_claim_to_replace_local_authority(self) -> None:
        decision = decide_permission(
            requested_capabilities=frozenset({"system.admin"}),
            mode=PermissionMode.FULL_ACCESS,
        )
        self.assertFalse(decision.requires_approval)
        self.assertIn("local authority", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
