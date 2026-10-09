from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from meo.device.config import default_config_path, load_agentd_config
from meo.device.runtime import build_device_runtime
from meo.device.secrets import EnvironmentDeviceSecretProvider, KWalletDeviceSecretProvider
from meo.device.websocket_transport import connect_websocket_relay
from meo.runtime.main import build_service


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meo-agentd", description="Meo AI remote device bridge")
    p.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Non-secret agentd configuration file",
    )
    p.add_argument(
        "--backend-factory",
        default=os.environ.get(
            "MEO_AI_BACKEND_FACTORY",
            "meo.adapters.headless_newelle:create_backend",
        ),
        help="Headless local agent backend in module:function form",
    )
    p.add_argument(
        "--wallet",
        default=os.environ.get("MEO_AGENTD_WALLET", "kdewallet"),
        help="KWallet name used for the enrolled device credential",
    )
    p.add_argument(
        "--development-env-token",
        action="store_true",
        help="Development only: read MEO_AGENTD_DEVICE_TOKEN instead of KWallet",
    )
    p.add_argument(
        "--self-check",
        action="store_true",
        help="Validate config/backend construction and secure credential provider, then exit",
    )
    return p


async def run(args) -> int:
    config = load_agentd_config(args.config)
    if args.development_env_token:
        secrets = EnvironmentDeviceSecretProvider()
    else:
        secrets = KWalletDeviceSecretProvider(
            device_id=config.device.device_id,
            wallet=args.wallet,
        )

    service = build_service(args.backend_factory)
    runtime = build_device_runtime(
        config=config,
        secrets=secrets,
        connector=connect_websocket_relay,
        service=service,
    )

    if args.self_check:
        # Reading the credential is intentional here: it verifies that an
        # enrolled device can actually unlock its narrow token from KWallet.
        token = await secrets.get_device_token()
        if not token.strip():
            raise RuntimeError("device credential is unavailable")
        print(
            f"Meo agentd ready: {config.device.display_name} -> {config.relay_url} "
            f"({type(service.backend).__name__})"
        )
        return 0

    try:
        await runtime.agentd.run_forever()
    except asyncio.CancelledError:
        raise
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
