from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .collector import UsageCollector


def _cloud_config() -> tuple[str, str, str] | None:
    url = os.environ.get("MEO_SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("MEO_SUPABASE_PUBLISHABLE_KEY", "").strip()
    token = os.environ.get("MEO_ACCOUNT_ACCESS_TOKEN", "").strip()
    if not (url and key and token):
        return None
    if not url.startswith("https://"):
        raise RuntimeError("MEO_SUPABASE_URL must use https://")
    return url, key, token


def _request_json(url: str, key: str, token: str, *, method: str = "GET", body: Any = None, prefer: str = "") -> Any:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if prefer:
        headers["Prefer"] = prefer
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"Supabase returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Supabase: {exc.reason}") from exc
    if not raw:
        return None
    return json.loads(raw)


def sync_to_supabase(collector: UsageCollector) -> dict[str, Any]:
    config = _cloud_config()
    if config is None:
        return {
            "configured": False,
            "uploaded": 0,
            "message": "Sign in to Meo Account to sync activity across devices.",
        }
    url, key, token = config
    account = _request_json(f"{url}/auth/v1/user", key, token)
    user_id = account.get("id") if isinstance(account, dict) else None
    if not isinstance(user_id, str) or not user_id:
        raise RuntimeError("Meo Account token did not resolve to a Supabase user")

    rows = collector.cloud_rows()
    uploaded = 0
    for offset in range(0, len(rows), 250):
        batch = []
        for row in rows[offset : offset + 250]:
            item = dict(row)
            item["user_id"] = user_id
            batch.append(item)
        if not batch:
            continue
        _request_json(
            f"{url}/rest/v1/ai_usage_events?on_conflict=user_id,source,source_event_id",
            key,
            token,
            method="POST",
            body=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        uploaded += len(batch)
    return {"configured": True, "uploaded": uploaded, "message": "Activity is synced with Meo Account."}


def cloud_dashboard(days: int) -> dict[str, Any] | None:
    config = _cloud_config()
    if config is None:
        return None
    url, key, token = config
    result = _request_json(
        f"{url}/rest/v1/rpc/get_ai_usage_dashboard",
        key,
        token,
        method="POST",
        body={"p_days": days},
    )
    return result if isinstance(result, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m meo.usage.cli")
    parser.add_argument("command", choices=("dashboard", "import", "sync", "refresh"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args(argv)

    collector = UsageCollector()
    try:
        imported: dict[str, int] | None = None
        sync_result: dict[str, Any] | None = None
        if args.command in {"import", "refresh"}:
            imported = collector.import_all()
        if args.command in {"sync", "refresh"} and not args.local_only:
            sync_result = sync_to_supabase(collector)

        dashboard = None if args.local_only else cloud_dashboard(args.days)
        if dashboard is None:
            dashboard = collector.dashboard(args.days)
            source = "local"
        else:
            source = "cloud"

        output = dict(dashboard)
        output["data_source"] = source
        output["sync_configured"] = _cloud_config() is not None
        if imported is not None:
            output["imported"] = imported
        if sync_result is not None:
            output["sync"] = sync_result
        print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        collector.close()


if __name__ == "__main__":
    raise SystemExit(main())
