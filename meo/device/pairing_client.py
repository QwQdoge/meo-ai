from __future__ import annotations

import argparse
import asyncio
import json
import socket
import time
import webbrowser
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from meo.device.agentd import AgentdConfig
from meo.device.config import relay_url_from_cloud, save_agentd_config
from meo.device.protocol import DeviceRegistration
from meo.device.secrets import KWalletDeviceSecretProvider


@dataclass(frozen=True)
class PairingClientConfig:
    cloud_url: str
    device_id: str
    display_name: str
    capabilities: tuple[str, ...] = ("agent.chat",)

    def validate(self) -> None:
        parsed = urlparse(self.cloud_url)
        if parsed.scheme != "https":
            if not (
                parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            ):
                raise ValueError("cloud_url must use https:// (http is allowed only for loopback development)")
        if not self.device_id.strip() or not self.display_name.strip():
            raise ValueError("device identity is required")
        if not self.capabilities:
            raise ValueError("at least one capability is required")


class PairingClient:
    def __init__(self, config: PairingClientConfig) -> None:
        config.validate()
        self.config = config
        self.base_url = config.cloud_url.rstrip("/")

    async def enroll(self) -> str:
        started = await asyncio.to_thread(
            self._post,
            "/v1/device-enrollments/start",
            {
                "device_id": self.config.device_id,
                "display_name": self.config.display_name,
                "capabilities": list(self.config.capabilities),
            },
        )
        code = self._required_text(started, "user_code")
        secret = self._required_text(started, "pairing_secret")
        verification_uri = self._required_text(started, "verification_uri_complete")
        interval = started.get("poll_interval_seconds", 2)
        if not isinstance(interval, int) or isinstance(interval, bool) or not (1 <= interval <= 30):
            interval = 2

        print(f"Connect this device to Meo: {code}")
        print(verification_uri)
        try:
            webbrowser.open(verification_uri, new=2, autoraise=True)
        except Exception:
            pass

        deadline = time.monotonic() + 10 * 60
        while time.monotonic() < deadline:
            result = await asyncio.to_thread(
                self._post,
                "/v1/device-enrollments/poll",
                {"pairing_secret": secret},
            )
            state = result.get("state")
            if state == "pending":
                await asyncio.sleep(interval)
                continue
            if state == "approved":
                return self._required_text(result, "device_token")
            if state == "consumed":
                raise RuntimeError("pairing was already completed; start a new device connection")
            if state == "expired":
                raise RuntimeError("pairing code expired; start again")
            if state == "rejected":
                raise RuntimeError("device connection was rejected")
            raise RuntimeError("Meo Cloud returned an invalid pairing state")
        raise RuntimeError("pairing timed out; start again")

    def _post(self, path: str, body: dict) -> dict:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                error = json.loads(exc.read().decode("utf-8"))
                message = error.get("error", {}).get("message")
            except Exception:
                message = None
            raise RuntimeError(message or f"Meo Cloud returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("could not reach Meo Cloud") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Meo Cloud returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Meo Cloud returned an invalid response")
        return value

    @staticmethod
    def _required_text(value: dict, key: str) -> str:
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"Meo Cloud response is missing {key}")
        return item.strip()


async def _main_async(args) -> None:
    device_id = args.device_id or socket.gethostname().lower().replace(" ", "-")
    display_name = args.display_name or socket.gethostname()
    capabilities = tuple(args.capability or ("agent.chat",))
    config = PairingClientConfig(
        cloud_url=args.cloud_url,
        device_id=device_id,
        display_name=display_name,
        capabilities=capabilities,
    )
    token = await PairingClient(config).enroll()
    store = KWalletDeviceSecretProvider(device_id=device_id, wallet=args.wallet)
    await store.store_device_token(token)

    agentd_config = AgentdConfig(
        device=DeviceRegistration.create(device_id, display_name, capabilities),
        relay_url=relay_url_from_cloud(args.cloud_url),
    )
    config_path = save_agentd_config(agentd_config)
    print("Connected to Meo.")
    print("Device credential: KWallet")
    print(f"Agent configuration: {config_path}")
    print("Start the bridge with: meo-agentd")


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect this computer to Meo AI")
    parser.add_argument("--cloud-url", required=True, help="Meo AI Cloud base URL")
    parser.add_argument("--device-id", help="Stable Meo device ID; defaults to hostname")
    parser.add_argument("--display-name", help="Friendly device name")
    parser.add_argument(
        "--capability",
        action="append",
        help="Device capability; may be repeated (default: agent.chat)",
    )
    parser.add_argument("--wallet", default="kdewallet", help="KWallet name")
    args = parser.parse_args()
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
