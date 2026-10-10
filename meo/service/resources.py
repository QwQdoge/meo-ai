from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


RESOURCE_KINDS = {"attachment", "image", "long_text", "artifact"}
RESOURCE_STATES = {"ready", "failed"}
_DEFAULT_MAX_BYTES = 25 * 1024 * 1024
_MAX_NAME = 512
_MAX_MIME = 128


class ResourceError(ValueError):
    pass


@dataclass(frozen=True)
class ResourceRecord:
    resource_id: str
    conversation_id: str
    kind: str
    name: str
    mime_type: str
    size_bytes: int
    sha256: str
    state: str = "ready"

    def public_dict(self) -> dict:
        """Return frontend-safe metadata without a backing filesystem path."""
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "name": self.name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "state": self.state,
        }


class ConversationResourceStore:
    """Small persistent resource store scoped by conversation identity.

    This is deliberately not a generic filesystem API. Callers provide bytes and
    receive an opaque `resource_id`; local backing paths never enter the frontend
    contract. Workspace/repository access remains a separate capability boundary.
    """

    def __init__(self, root: str | Path, *, max_resource_bytes: int = _DEFAULT_MAX_BYTES) -> None:
        if isinstance(max_resource_bytes, bool) or not isinstance(max_resource_bytes, int) or max_resource_bytes < 1:
            raise ValueError("max_resource_bytes must be a positive integer")
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.metadata = self.root / "metadata"
        self.max_resource_bytes = max_resource_bytes
        self.objects.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.metadata.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._tighten_directory(self.root)
        self._tighten_directory(self.objects)
        self._tighten_directory(self.metadata)

    @staticmethod
    def _tighten_directory(path: Path) -> None:
        try:
            path.chmod(0o700)
        except OSError:
            pass

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> str:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ResourceError("conversation_id is required")
        if len(conversation_id) > 256:
            raise ResourceError("conversation_id is too long")
        return conversation_id

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ResourceError("resource name is required")
        if len(name) > _MAX_NAME:
            raise ResourceError("resource name is too long")
        if "/" in name or "\\" in name or Path(name).name != name or name in {".", ".."}:
            raise ResourceError("resource name must not contain a path")
        if any(ord(char) < 32 for char in name):
            raise ResourceError("resource name contains control characters")
        return name

    @staticmethod
    def _validate_kind(kind: str) -> str:
        if kind not in RESOURCE_KINDS:
            raise ResourceError("unsupported resource kind")
        return kind

    @staticmethod
    def _validate_mime(mime_type: str) -> str:
        if not isinstance(mime_type, str):
            raise ResourceError("mime_type must be a string")
        mime_type = mime_type.strip()
        if len(mime_type) > _MAX_MIME:
            raise ResourceError("mime_type is too long")
        return mime_type

    @staticmethod
    def _validate_state(state: str) -> str:
        if state not in RESOURCE_STATES:
            raise ResourceError("unsupported resource state")
        return state

    @staticmethod
    def _token(resource_id: str) -> str:
        if not isinstance(resource_id, str) or not resource_id.startswith("resource:"):
            raise ResourceError("invalid resource_id")
        token = resource_id.removeprefix("resource:")
        if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
            raise ResourceError("invalid resource_id")
        return token

    def _metadata_path(self, resource_id: str) -> Path:
        return self.metadata / f"{self._token(resource_id)}.json"

    def _object_path(self, resource_id: str) -> Path:
        return self.objects / self._token(resource_id)

    def _write_metadata(self, record: ResourceRecord) -> None:
        target = self._metadata_path(record.resource_id)
        raw = json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix="resource-meta-", dir=self.metadata)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read_record(self, resource_id: str) -> ResourceRecord:
        path = self._metadata_path(resource_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ResourceError("unknown resource_id") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResourceError("resource metadata is unreadable") from exc
        if not isinstance(value, dict):
            raise ResourceError("resource metadata is invalid")
        try:
            record = ResourceRecord(**value)
        except TypeError as exc:
            raise ResourceError("resource metadata is invalid") from exc
        self._token(record.resource_id)
        self._validate_conversation_id(record.conversation_id)
        self._validate_kind(record.kind)
        self._validate_name(record.name)
        self._validate_mime(record.mime_type)
        self._validate_state(record.state)
        if isinstance(record.size_bytes, bool) or not isinstance(record.size_bytes, int) or record.size_bytes < 0:
            raise ResourceError("resource metadata size is invalid")
        if not isinstance(record.sha256, str) or len(record.sha256) != 64:
            raise ResourceError("resource metadata digest is invalid")
        return record

    def put_bytes(
        self,
        conversation_id: str,
        *,
        kind: str,
        name: str,
        mime_type: str,
        data: bytes,
        state: str = "ready",
    ) -> ResourceRecord:
        conversation_id = self._validate_conversation_id(conversation_id)
        kind = self._validate_kind(kind)
        name = self._validate_name(name)
        mime_type = self._validate_mime(mime_type)
        state = self._validate_state(state)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ResourceError("resource data must be bytes")
        content = bytes(data)
        if len(content) > self.max_resource_bytes:
            raise ResourceError("resource exceeds configured size limit")

        resource_id = f"resource:{uuid4().hex}"
        object_path = self._object_path(resource_id)
        fd, temp_name = tempfile.mkstemp(prefix="resource-data-", dir=self.objects)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, object_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        record = ResourceRecord(
            resource_id=resource_id,
            conversation_id=conversation_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=sha256(content).hexdigest(),
            state=state,
        )
        try:
            self._write_metadata(record)
        except Exception:
            try:
                object_path.unlink()
            except FileNotFoundError:
                pass
            raise
        return record

    def put_text(
        self,
        conversation_id: str,
        *,
        name: str,
        text: str,
        kind: str = "long_text",
        mime_type: str = "text/plain; charset=utf-8",
    ) -> ResourceRecord:
        if not isinstance(text, str):
            raise ResourceError("text must be a string")
        return self.put_bytes(
            conversation_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            data=text.encode("utf-8"),
        )

    def get(self, conversation_id: str, resource_id: str) -> ResourceRecord:
        conversation_id = self._validate_conversation_id(conversation_id)
        record = self._read_record(resource_id)
        if record.conversation_id != conversation_id:
            raise ResourceError("resource does not belong to this conversation")
        return record

    def read_bytes(self, conversation_id: str, resource_id: str) -> bytes:
        record = self.get(conversation_id, resource_id)
        try:
            content = self._object_path(record.resource_id).read_bytes()
        except FileNotFoundError as exc:
            raise ResourceError("resource content is missing") from exc
        if len(content) != record.size_bytes or sha256(content).hexdigest() != record.sha256:
            raise ResourceError("resource content failed integrity validation")
        return content

    def list_resources(self, conversation_id: str) -> list[ResourceRecord]:
        conversation_id = self._validate_conversation_id(conversation_id)
        result: list[ResourceRecord] = []
        for path in sorted(self.metadata.glob("*.json")):
            try:
                resource_id = f"resource:{path.stem}"
                record = self._read_record(resource_id)
            except ResourceError:
                continue
            if record.conversation_id == conversation_id:
                result.append(record)
        return result

    def delete(self, conversation_id: str, resource_id: str) -> None:
        record = self.get(conversation_id, resource_id)
        for path in (self._object_path(record.resource_id), self._metadata_path(record.resource_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def default_resource_root() -> Path:
    configured = os.environ.get("XDG_DATA_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".local" / "share"
    return base / "meo-ai" / "resources"
