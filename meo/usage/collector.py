from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class UsageEvent:
    source: str
    source_event_id: str
    session_id: str
    project_key: str
    project_name: str
    provider: str
    model: str
    model_role: str
    occurred_at: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    duration_ms: int | None = None
    session_duration_ms: int | None = None
    estimated_cost_microusd: int | None = None
    metadata: dict[str, Any] | None = None

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.cache_write_tokens
            + self.output_tokens
            + self.reasoning_tokens
        )


SCHEMA = """
create table if not exists usage_events (
  source text not null,
  source_event_id text not null,
  session_id text not null default '',
  project_key text not null default '',
  project_name text not null default '',
  provider text not null default '',
  model text not null default '',
  model_role text not null default 'unknown',
  occurred_at text not null,
  input_tokens integer not null default 0,
  cached_input_tokens integer not null default 0,
  cache_write_tokens integer not null default 0,
  output_tokens integer not null default 0,
  reasoning_tokens integer not null default 0,
  duration_ms integer,
  session_duration_ms integer,
  estimated_cost_microusd integer,
  metadata text not null default '{}',
  primary key (source, source_event_id)
);
create index if not exists usage_events_time_idx on usage_events(occurred_at desc);
create index if not exists usage_events_model_idx on usage_events(model, occurred_at desc);
create index if not exists usage_events_project_idx on usage_events(project_key, occurred_at desc);
"""


def _default_db_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "meo-ai" / "usage.db"


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _iso_timestamp(value: Any, *, fallback: float | None = None) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    stamp = fallback if fallback is not None else datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def _project(path_value: str) -> tuple[str, str]:
    raw = path_value.strip()
    if not raw:
        return "", "Unassigned"
    normalized = os.path.normpath(os.path.expanduser(raw))
    name = Path(normalized).name or normalized
    digest = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:24]
    return digest, name[:160]


def _read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield line_number, value
    except OSError:
        return


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class UsageCollector:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def import_all(self) -> dict[str, int]:
        counts = {
            "codex": self.import_codex(),
            "claude_code": self.import_claude_code(),
        }
        self.db.commit()
        return counts

    def upsert(self, event: UsageEvent) -> None:
        payload = asdict(event)
        payload["metadata"] = json.dumps(event.metadata or {}, separators=(",", ":"), ensure_ascii=False)
        columns = tuple(payload)
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{name}=excluded.{name}" for name in columns if name not in {"source", "source_event_id"})
        self.db.execute(
            f"insert into usage_events ({','.join(columns)}) values ({placeholders}) "
            f"on conflict(source,source_event_id) do update set {updates}",
            tuple(payload[name] for name in columns),
        )

    def import_codex(self, root: Path | None = None) -> int:
        root = root or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        files: list[Path] = []
        sessions = root / "sessions"
        archived = root / "archived_sessions"
        if sessions.exists():
            files.extend(sessions.rglob("*.jsonl"))
        if archived.exists():
            files.extend(archived.rglob("*.jsonl"))

        count = 0
        for path in sorted(set(files)):
            count += self._import_codex_file(path)
        return count

    def _import_codex_file(self, path: Path) -> int:
        session_id = path.stem.removeprefix("rollout-")
        cwd = ""
        model = ""
        provider = "OpenAI"
        previous_total: dict[str, int] | None = None
        imported = 0

        for line_number, row in _read_jsonl(path):
            payload = _dict(row.get("payload"))
            record_type = _first_text(row.get("type"), payload.get("type"))
            if row.get("type") == "session_meta" or record_type == "session_meta":
                session_id = _first_text(payload.get("id"), row.get("id"), session_id)
                cwd = _first_text(payload.get("cwd"), row.get("cwd"), cwd)
                provider = _first_text(payload.get("model_provider"), row.get("model_provider"), provider)
                continue
            if row.get("type") == "turn_context":
                cwd = _first_text(payload.get("cwd"), cwd)
                model = _first_text(payload.get("model"), model)
                continue
            model = _first_text(payload.get("model"), row.get("model"), model)
            if payload.get("type") != "token_count":
                continue

            info = _dict(payload.get("info"))
            last = _dict(info.get("last_token_usage"))
            cumulative = _dict(info.get("total_token_usage"))
            usage = last
            if not usage and cumulative:
                current = {
                    "input_tokens": _safe_int(cumulative.get("input_tokens")),
                    "cached_input_tokens": _safe_int(cumulative.get("cached_input_tokens")),
                    "output_tokens": _safe_int(cumulative.get("output_tokens")),
                    "reasoning_output_tokens": _safe_int(cumulative.get("reasoning_output_tokens")),
                }
                if previous_total is None:
                    usage = current
                else:
                    usage = {key: max(0, value - previous_total.get(key, 0)) for key, value in current.items()}
                previous_total = current
            elif cumulative:
                previous_total = {
                    "input_tokens": _safe_int(cumulative.get("input_tokens")),
                    "cached_input_tokens": _safe_int(cumulative.get("cached_input_tokens")),
                    "output_tokens": _safe_int(cumulative.get("output_tokens")),
                    "reasoning_output_tokens": _safe_int(cumulative.get("reasoning_output_tokens")),
                }
            if not usage:
                continue

            cached = _safe_int(usage.get("cached_input_tokens"))
            raw_input = _safe_int(usage.get("input_tokens"))
            reasoning = _safe_int(usage.get("reasoning_output_tokens") or usage.get("reasoning_tokens"))
            raw_output = _safe_int(usage.get("output_tokens"))
            project_key, project_name = _project(cwd)
            timestamp = _iso_timestamp(row.get("timestamp"), fallback=path.stat().st_mtime)
            event_id = f"{session_id}:{line_number}"
            event = UsageEvent(
                source="codex",
                source_event_id=event_id[:240],
                session_id=session_id[:240],
                project_key=project_key,
                project_name=project_name,
                provider=provider[:120],
                model=(model or "Codex")[:180],
                model_role="execution",
                occurred_at=timestamp,
                input_tokens=max(0, raw_input - cached),
                cached_input_tokens=cached,
                output_tokens=max(0, raw_output - reasoning),
                reasoning_tokens=reasoning,
                metadata={"source_file": path.name},
            )
            if event.total_tokens:
                self.upsert(event)
                imported += 1
        return imported

    def import_claude_code(self, root: Path | None = None) -> int:
        root = root or Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
        if not root.exists():
            return 0
        count = 0
        for path in sorted(root.rglob("*.jsonl")):
            count += self._import_claude_file(path)
        return count

    def _import_claude_file(self, path: Path) -> int:
        # Claude Code can repeat the same assistant message while streaming or
        # recording thinking blocks. Keep only the most complete usage row per
        # message/request pair before writing to the local store.
        candidates: dict[str, UsageEvent] = {}
        fallback_session = path.stem
        for line_number, row in _read_jsonl(path):
            if row.get("type") != "assistant":
                continue
            message = _dict(row.get("message"))
            usage = _dict(message.get("usage"))
            if not usage:
                continue
            message_id = _first_text(message.get("id"), row.get("uuid"), str(line_number))
            request_id = _first_text(row.get("requestId"), row.get("request_id"))
            event_key = f"{message_id}:{request_id}" if request_id else message_id
            session_id = _first_text(row.get("sessionId"), row.get("session_id"), fallback_session)
            cwd = _first_text(row.get("cwd"))
            project_key, project_name = _project(cwd)
            input_tokens = _safe_int(usage.get("input_tokens"))
            cached = _safe_int(usage.get("cache_read_input_tokens"))
            cache_write = _safe_int(usage.get("cache_creation_input_tokens"))
            output = _safe_int(usage.get("output_tokens"))
            event = UsageEvent(
                source="claude_code",
                source_event_id=f"{session_id}:{event_key}"[:240],
                session_id=session_id[:240],
                project_key=project_key,
                project_name=project_name,
                provider="Anthropic",
                model=_first_text(message.get("model"), row.get("model"), "Claude")[:180],
                model_role="execution",
                occurred_at=_iso_timestamp(row.get("timestamp"), fallback=path.stat().st_mtime),
                input_tokens=input_tokens,
                cached_input_tokens=cached,
                cache_write_tokens=cache_write,
                output_tokens=output,
                metadata={"source_file": path.name},
            )
            previous = candidates.get(event.source_event_id)
            if previous is None or event.total_tokens >= previous.total_tokens:
                candidates[event.source_event_id] = event

        for event in candidates.values():
            if event.total_tokens:
                self.upsert(event)
        return len(candidates)

    def dashboard(self, days: int = 365) -> dict[str, Any]:
        days = max(7, min(int(days), 730))
        rows = list(self.db.execute("select * from usage_events order by occurred_at"))
        events = [dict(row) for row in rows]
        for event in events:
            event["total_tokens"] = sum(
                _safe_int(event[name])
                for name in ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens")
            )

        daily: dict[str, int] = defaultdict(int)
        models: dict[tuple[str, str], dict[str, Any]] = {}
        projects: dict[str, dict[str, Any]] = {}
        sources: dict[str, dict[str, Any]] = {}
        sessions: dict[tuple[str, str], tuple[datetime, datetime]] = {}

        for event in events:
            stamp = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            day = stamp.date().isoformat()
            total = event["total_tokens"]
            daily[day] += total
            model_key = (event["model"] or "Unknown", event["provider"] or "Unknown")
            model_row = models.setdefault(model_key, {"name": model_key[0], "provider": model_key[1], "tokens": 0, "events": 0})
            model_row["tokens"] += total
            model_row["events"] += 1
            project_key = event["project_key"] or "unassigned"
            project_row = projects.setdefault(project_key, {"name": event["project_name"] or "Unassigned", "project_key": event["project_key"], "tokens": 0, "sessions_set": set(), "last_used_at": event["occurred_at"]})
            project_row["tokens"] += total
            if event["session_id"]:
                project_row["sessions_set"].add((event["source"], event["session_id"]))
            project_row["last_used_at"] = max(project_row["last_used_at"], event["occurred_at"])
            source_row = sources.setdefault(event["source"], {"source": event["source"], "tokens": 0, "events": 0, "last_used_at": event["occurred_at"]})
            source_row["tokens"] += total
            source_row["events"] += 1
            source_row["last_used_at"] = max(source_row["last_used_at"], event["occurred_at"])
            if event["session_id"]:
                key = (event["source"], event["session_id"])
                if key in sessions:
                    first, last = sessions[key]
                    sessions[key] = (min(first, stamp), max(last, stamp))
                else:
                    sessions[key] = (stamp, stamp)

        active_dates = sorted(date.fromisoformat(day) for day in daily)
        longest_streak = current_streak = 0
        streak = 0
        previous: date | None = None
        for active in active_dates:
            streak = streak + 1 if previous and active == previous + timedelta(days=1) else 1
            longest_streak = max(longest_streak, streak)
            previous = active
        if active_dates and active_dates[-1] >= date.today() - timedelta(days=1):
            cursor = active_dates[-1]
            lookup = set(active_dates)
            while cursor in lookup:
                current_streak += 1
                cursor -= timedelta(days=1)

        cutoff = date.today() - timedelta(days=days - 1)
        daily_list = [{"date": day, "tokens": tokens} for day, tokens in sorted(daily.items()) if date.fromisoformat(day) >= cutoff]
        project_list = []
        for row in projects.values():
            item = {key: value for key, value in row.items() if key != "sessions_set"}
            item["sessions"] = len(row["sessions_set"])
            project_list.append(item)

        longest_session_ms = max(
            [int((last - first).total_seconds() * 1000) for first, last in sessions.values()] + [0]
        )
        return {
            "summary": {
                "lifetime_tokens": sum(event["total_tokens"] for event in events),
                "peak_day_tokens": max(daily.values(), default=0),
                "active_days": len(active_dates),
                "longest_streak": longest_streak,
                "current_streak": current_streak,
                "longest_session_ms": longest_session_ms,
                "estimated_cost_microusd": sum(_safe_int(event.get("estimated_cost_microusd")) for event in events),
            },
            "token_breakdown": {
                "input": sum(_safe_int(event["input_tokens"]) for event in events),
                "cached_input": sum(_safe_int(event["cached_input_tokens"]) for event in events),
                "cache_write": sum(_safe_int(event["cache_write_tokens"]) for event in events),
                "output": sum(_safe_int(event["output_tokens"]) for event in events),
                "reasoning": sum(_safe_int(event["reasoning_tokens"]) for event in events),
            },
            "daily": daily_list,
            "models": sorted(models.values(), key=lambda item: (-item["tokens"], item["name"]))[:16],
            "projects": sorted(project_list, key=lambda item: (-item["tokens"], item["name"]))[:16],
            "sources": sorted(sources.values(), key=lambda item: (-item["tokens"], item["source"])),
        }

    def cloud_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.db.execute("select * from usage_events order by occurred_at"):
            item = dict(row)
            try:
                item["metadata"] = json.loads(item["metadata"] or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            rows.append(item)
        return rows
