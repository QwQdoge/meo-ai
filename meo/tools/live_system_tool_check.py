#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from meo.system.dbus_router import DbusNextRouterClient, RouterUnavailable
from meo.system.system_tool import SystemTool, SystemToolRequest


READ_VOLUME = "org.meo.desktop.audio.getVolume"
SET_VOLUME = "org.meo.desktop.audio.setVolume"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Live acceptance helper for Meo AI -> org.meo.AIRouter1. "
        "The default path only inspects capability metadata."
    )
    p.add_argument(
        "--read-volume",
        action="store_true",
        help="Exercise the read-only volume capability if available",
    )
    p.add_argument(
        "--set-volume",
        type=int,
        metavar="PERCENT",
        help="Explicitly exercise the session-scoped set-volume capability (0-100)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="D-Bus call timeout in seconds",
    )
    return p


def print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def wait_and_print(tool: SystemTool, result) -> bool:
    view = dict(result.router_view)
    if result.router_request_id and result.state not in {
        "completed",
        "failed",
        "rejected",
        "denied",
        "expired",
        "awaiting_confirmation",
    }:
        view = tool.wait_terminal(result.router_request_id, timeout=35.0, poll_interval=0.1)
    print_json(view)
    return view.get("state") == "completed"


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.set_volume is not None and not 0 <= args.set_volume <= 100:
        raise SystemExit("--set-volume must be between 0 and 100")

    try:
        with DbusNextRouterClient(timeout=args.timeout) as router:
            tool = SystemTool(router)
            capabilities = tool.capabilities()
            print("Router capabilities:")
            for capability in capabilities:
                print_json({
                    "id": capability.capability_id,
                    "title": capability.title,
                    "owner": capability.owner,
                    "effect": capability.effect.value,
                    "verification": capability.verification.value,
                    "maturity": capability.maturity.value,
                    "requires_confirmation": capability.requires_confirmation,
                    "argument_schema": capability.argument_schema,
                })

            ids = {capability.capability_id for capability in capabilities}
            failed = False

            if args.read_volume:
                if READ_VOLUME not in ids:
                    print(f"SKIP: {READ_VOLUME} is not currently executable", file=sys.stderr)
                else:
                    print("Read-volume result:")
                    failed |= not wait_and_print(
                        tool,
                        tool.invoke(SystemToolRequest(READ_VOLUME, {})),
                    )

            if args.set_volume is not None:
                if SET_VOLUME not in ids:
                    print(f"SKIP: {SET_VOLUME} is not currently executable", file=sys.stderr)
                else:
                    print(f"Set-volume result ({args.set_volume}%):")
                    failed |= not wait_and_print(
                        tool,
                        tool.invoke(SystemToolRequest(SET_VOLUME, {"percent": args.set_volume})),
                    )

            return 1 if failed else 0
    except (RouterUnavailable, ValueError, TimeoutError) as exc:
        print(f"SystemTool live acceptance failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
