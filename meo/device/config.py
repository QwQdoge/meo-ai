from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from meo.device.agentd import AgentdConfig, config_from_json


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "meo" / "agentd.json"


def relay_url_from_cloud(cloud_url: str) -> str:
    parsed = urlsplit(cloud_url.strip())
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "https":
        scheme = "wss"
    elif parsed.scheme == "http" and loopback:
        scheme = "ws"
    else:
        raise ValueError("cloud_url must use https:// (http is allowed only for loopback development)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("cloud_url is invalid")
    base_path = parsed.path.rstrip("/")
    return urlunsplit((scheme, parsed.netloc, f"{base_path}/v1/device-relay", "", ""))


def save_agentd_config(config: AgentdConfig, path: Path | None = None) -> Path:
    config.validate()
    destination = (path or default_config_path()).expanduser()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        destination.parent.chmod(0o700)
    except OSError:
        pass

    payload = {
        "device_id": config.device.device_id,
        "display_name": config.device.display_name,
        "capabilities": list(config.device.capabilities),
        "relay_url": config.relay_url,
        "heartbeat_seconds": config.heartbeat_seconds,
        "reconnect_min_seconds": config.reconnect_min_seconds,
        "reconnect_max_seconds": config.reconnect_max_seconds,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".agentd-", suffix=".json", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        destination.chmod(0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def load_agentd_config(path: Path | None = None) -> AgentdConfig:
    source = (path or default_config_path()).expanduser()
    try:
        raw = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            "This device is not connected to Meo yet. Run the device pairing command first."
        ) from exc
    return config_from_json(raw)
