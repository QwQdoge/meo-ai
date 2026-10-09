from __future__ import annotations

import os


class EnvironmentDeviceSecretProvider:
    """Development-only device credential source.

    Production packaging must replace this with Meo Account/KWallet-backed
    secure storage. This provider exists so relay integration can be exercised
    without ever persisting the credential in the agentd JSON config.
    """

    def __init__(self, variable: str = "MEO_AGENTD_DEVICE_TOKEN") -> None:
        self.variable = variable

    async def get_device_token(self) -> str:
        token = os.environ.get(self.variable, "").strip()
        if not token:
            raise RuntimeError(f"{self.variable} is not set")
        return token
