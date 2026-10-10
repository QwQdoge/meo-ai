from __future__ import annotations

import argparse
import importlib
import os
from typing import Callable

from meo.runtime.headless_probe import require_headless
from meo.runtime.http_transport import create_http_server
from meo.service.core import AgentServiceCore
from meo.service.backend_adapter import AgentBackendAdapter
from meo.service.model_roles import ModelRoleRegistry, default_model_role_path


BackendFactory = Callable[[], AgentBackendAdapter]


def load_backend_factory(spec: str) -> BackendFactory:
    if ":" not in spec:
        raise ValueError("backend factory must use module:function syntax")
    module_name, function_name = spec.split(":", 1)
    if not module_name or not function_name:
        raise ValueError("backend factory must use module:function syntax")
    require_headless()
    module = importlib.import_module(module_name)
    require_headless()
    factory = getattr(module, function_name, None)
    if not callable(factory):
        raise ValueError(f"backend factory is not callable: {spec}")
    return factory


def build_service(spec: str) -> AgentServiceCore:
    factory = load_backend_factory(spec)
    backend = factory()
    require_headless()
    return AgentServiceCore(
        backend=backend,
        model_roles=ModelRoleRegistry(default_model_role_path()),
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meo-agent-service")
    p.add_argument(
        "--backend-factory",
        default=os.environ.get("MEO_AI_BACKEND_FACTORY", ""),
        help="Headless backend factory in module:function form",
    )
    p.add_argument(
        "--self-check",
        action="store_true",
        help="Validate the runtime import boundary and optional backend construction, then exit",
    )
    p.add_argument(
        "--host",
        default=os.environ.get("MEO_AI_SERVICE_HOST", "127.0.0.1"),
        help="Loopback bind address; non-loopback addresses are rejected",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MEO_AI_SERVICE_PORT", "8765")),
        help="AgentService loopback HTTP port",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    require_headless()

    if args.self_check and not args.backend_factory:
        print("Meo AgentService headless boundary: clean (no backend loaded)")
        return 0

    if not args.backend_factory:
        raise SystemExit("MEO_AI_BACKEND_FACTORY or --backend-factory is required")

    service = build_service(args.backend_factory)
    if args.self_check:
        print(f"Meo AgentService backend ready: {type(service.backend).__name__}")
        return 0

    server = create_http_server(service, host=args.host, port=args.port)
    host, port = server.server_address[:2]
    print(f"Meo AgentService listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
