from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PermissionMode(str, Enum):
    ASK = "ask"
    SMART = "smart"
    FULL_ACCESS = "full_access"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_HIGH_RISK_CAPABILITIES = frozenset(
    {
        "system.admin",
        "package.install",
        "package.remove",
        "filesystem.delete",
        "git.push",
        "credentials.read",
        "network.expose",
    }
)

_MEDIUM_RISK_CAPABILITIES = frozenset(
    {
        "filesystem.write",
        "git.commit",
        "browser.submit",
        "system.settings.write",
    }
)


@dataclass(frozen=True)
class PermissionDecision:
    mode: PermissionMode
    risk: RiskLevel
    requires_approval: bool
    reason: str


def classify_capabilities(capabilities: set[str] | frozenset[str]) -> RiskLevel:
    if capabilities & _HIGH_RISK_CAPABILITIES:
        return RiskLevel.HIGH
    if capabilities & _MEDIUM_RISK_CAPABILITIES:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def decide_permission(
    *,
    requested_capabilities: set[str] | frozenset[str],
    mode: PermissionMode = PermissionMode.SMART,
) -> PermissionDecision:
    """Return the product-level approval decision.

    This is deliberately not the final security authority. Local owners, polkit,
    application permissions and the System AI Router may still reject an action.
    """

    risk = classify_capabilities(requested_capabilities)

    if mode is PermissionMode.ASK:
        return PermissionDecision(mode, risk, True, "Ask mode requires approval")

    if mode is PermissionMode.FULL_ACCESS:
        return PermissionDecision(
            mode,
            risk,
            False,
            "Full Access suppresses product prompts but not local authority checks",
        )

    if risk is RiskLevel.HIGH:
        return PermissionDecision(mode, risk, True, "High-risk action requires approval")

    return PermissionDecision(mode, risk, False, "Smart mode allows low/medium-risk work")
