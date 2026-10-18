from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_IMPORTANT_RE = re.compile(
    r"(?:error|fatal|failed|failure|exception|traceback|warning|warn|panic|segfault|"
    r"assert|denied|not found|exit(?:ed)?(?: code)?\s*[:=]?\s*[1-9]\d*)",
    re.IGNORECASE,
)
_PROGRESS_RE = re.compile(r"^(?:\s*\d{1,3}%|\s*[#=.>_-]{8,}|\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb)/)", re.IGNORECASE)


@dataclass(frozen=True)
class CompactedToolOutput:
    """Compact model-facing form of an immutable raw tool result."""

    text: str
    raw_ref: str
    raw_chars: int
    compact_chars: int
    compacted: bool
    important_lines: int = 0

    @property
    def saved_ratio(self) -> float:
        if self.raw_chars <= 0:
            return 0.0
        return max(0.0, 1.0 - (self.compact_chars / self.raw_chars))

    def public_stats(self) -> dict:
        return {
            "raw_ref": self.raw_ref,
            "raw_chars": self.raw_chars,
            "compact_chars": self.compact_chars,
            "compacted": self.compacted,
            "important_lines": self.important_lines,
            "saved_ratio": round(self.saved_ratio, 4),
        }


class ToolOutputCompactor:
    """Reduce noisy tool output without destroying or mutating the raw result.

    The caller remains responsible for durable raw-result storage. ``raw_ref`` is
    a content-derived reference that can be replaced by a persistence-layer ID.
    """

    def __init__(self, *, max_chars: int = 1800, head_lines: int = 10, tail_lines: int = 14) -> None:
        if max_chars < 256:
            raise ValueError("max_chars must be at least 256")
        self.max_chars = max_chars
        self.head_lines = max(1, head_lines)
        self.tail_lines = max(1, tail_lines)

    @staticmethod
    def raw_ref(text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:20]
        return f"tool-output:sha256:{digest}"

    def compact(self, raw: str, *, raw_ref: str | None = None) -> CompactedToolOutput:
        if not isinstance(raw, str):
            raw = str(raw)
        reference = raw_ref or self.raw_ref(raw)
        cleaned = _ANSI_RE.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
        if len(cleaned) <= self.max_chars:
            return CompactedToolOutput(cleaned, reference, len(raw), len(cleaned), False, 0)

        lines = cleaned.splitlines()
        important = [line for line in lines if _IMPORTANT_RE.search(line)]

        # Collapse progress spam and consecutive duplicate lines before choosing
        # the head/tail. This is deliberately deterministic for prompt caching.
        useful: list[str] = []
        previous = object()
        for line in lines:
            normalized = line.rstrip()
            if normalized == previous:
                continue
            previous = normalized
            if _PROGRESS_RE.search(normalized) and not _IMPORTANT_RE.search(normalized):
                continue
            useful.append(normalized)

        head = useful[: self.head_lines]
        tail = useful[-self.tail_lines :] if len(useful) > self.head_lines else []
        middle_important = [line for line in important if line not in head and line not in tail]
        # Error lines are generally more useful than arbitrary output. Bound the
        # count so a failing build cannot replace one token problem with another.
        middle_important = middle_important[:24]

        sections: list[str] = []
        if head:
            sections.extend(head)
        if middle_important:
            sections.append("… important lines …")
            sections.extend(middle_important)
        if tail:
            sections.append("… tail …")
            sections.extend(tail)

        marker = f"[tool output compacted; raw_ref={reference}; raw_chars={len(raw)}]"
        body = "\n".join(sections).strip()
        budget = max(0, self.max_chars - len(marker) - 1)
        if len(body) > budget:
            half = max(1, (budget - 24) // 2)
            body = body[:half].rstrip() + "\n… compacted …\n" + body[-half:].lstrip()
        compacted = marker + ("\n" + body if body else "")
        return CompactedToolOutput(
            compacted,
            reference,
            len(raw),
            len(compacted),
            True,
            len(important),
        )
