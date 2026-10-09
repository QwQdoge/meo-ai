from __future__ import annotations

import asyncio
import os
import shutil
import subprocess


class EnvironmentDeviceSecretProvider:
    """Development-only device credential source.

    Production packaging must use secure OS storage. This provider exists so
    relay integration can be exercised without persisting a credential in the
    agentd JSON config.
    """

    def __init__(self, variable: str = "MEO_AGENTD_DEVICE_TOKEN") -> None:
        self.variable = variable

    async def get_device_token(self) -> str:
        token = os.environ.get(self.variable, "").strip()
        if not token:
            raise RuntimeError(f"{self.variable} is not set")
        return token


class KWalletDeviceSecretProvider:
    """Read and write the narrow Meo device credential through KDE Wallet.

    ``kwallet-query`` is invoked directly without a shell. Tokens are passed on
    stdin when written and never appear in command arguments, process listings,
    config JSON, or logs.
    """

    def __init__(
        self,
        *,
        device_id: str,
        wallet: str = "kdewallet",
        folder: str = "Passwords",
    ) -> None:
        device_id = device_id.strip()
        if not device_id:
            raise ValueError("device_id is required")
        self.device_id = device_id
        self.wallet = wallet
        self.folder = folder
        self.entry = f"Meo AI device {device_id}"

    async def get_device_token(self) -> str:
        token = await asyncio.to_thread(self._read)
        if not token.startswith("meo_dev_"):
            raise RuntimeError("stored Meo device credential is invalid")
        return token

    async def store_device_token(self, token: str) -> None:
        token = token.strip()
        if not token.startswith("meo_dev_") or len(token) < 40:
            raise ValueError("invalid Meo device credential")
        await asyncio.to_thread(self._write, token)

    def _command(self) -> str:
        path = shutil.which("kwallet-query")
        if not path:
            raise RuntimeError("kwallet-query is not installed")
        return path

    def _read(self) -> str:
        result = subprocess.run(
            [
                self._command(),
                "--folder",
                self.folder,
                "--read-password",
                self.entry,
                self.wallet,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError("Meo device credential is not available in KWallet")
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("Meo device credential is empty")
        return token

    def _write(self, token: str) -> None:
        result = subprocess.run(
            [
                self._command(),
                "--folder",
                self.folder,
                "--write-password",
                self.entry,
                self.wallet,
            ],
            input=token,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError("could not store Meo device credential in KWallet")
