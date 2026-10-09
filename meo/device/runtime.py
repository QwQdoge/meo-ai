from __future__ import annotations

from dataclasses import dataclass

from meo.device.agentd import (
    AgentdConfig,
    DeviceSecretProvider,
    MeoAgentd,
    RelayConnector,
)
from meo.device.events import RelayEventQueue
from meo.device.executor import AgentServiceExecutor
from meo.service.core import AgentServiceCore


@dataclass(frozen=True)
class MeoDeviceRuntime:
    agentd: MeoAgentd
    events: RelayEventQueue
    executor: AgentServiceExecutor


def build_device_runtime(
    *,
    config: AgentdConfig,
    secrets: DeviceSecretProvider,
    connector: RelayConnector,
    service: AgentServiceCore,
) -> MeoDeviceRuntime:
    """Wire the existing AgentService into one reliable remote-device runtime."""

    events = RelayEventQueue(config.device.device_id)
    executor = AgentServiceExecutor(service, events.publish)
    agentd = MeoAgentd(
        config,
        secrets,
        connector,
        executor,
        events=events,
    )
    return MeoDeviceRuntime(
        agentd=agentd,
        events=events,
        executor=executor,
    )
