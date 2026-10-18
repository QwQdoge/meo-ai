from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Callable, Iterable, Protocol

from .tool_output import ToolOutputCompactor


_WORD_RE = re.compile(r"[\w.+#/@:-]+", re.UNICODE)
_IMPORTANCE_RE = re.compile(
    r"(?:decid(?:e|ed|ing)|must|require|constraint|todo|block(?:ed|er)|error|failed|"
    r"fix|remember|important|file|path|branch|commit|api|deadline)",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    """Cheap conservative estimator that needs no provider tokenizer.

    CJK-heavy text is closer to one token per character while Latin prose is
    usually several characters per token, so use a blended estimate.
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u3400" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, cjk + math.ceil(other / 3.6))


@dataclass(frozen=True)
class ContextMessage:
    role: str
    text: str
    source_ref: str = ""
    kind: str = "message"
    pinned: bool = False


@dataclass(frozen=True)
class TaskMemoryItem:
    text: str
    category: str = "fact"
    source_ref: str = ""
    pinned: bool = False


@dataclass(frozen=True)
class ContextBudget:
    total_tokens: int
    static_tokens: int = 0
    reserve_output_tokens: int = 0
    recent_fraction: float = 0.45
    memory_fraction: float = 0.20

    @property
    def dynamic_tokens(self) -> int:
        return max(0, self.total_tokens - self.static_tokens - self.reserve_output_tokens)


@dataclass(frozen=True)
class ContextStats:
    strategy: str
    raw_tokens: int
    selected_tokens: int
    budget_tokens: int
    recent_messages: int
    selected_old_messages: int
    memory_items: int
    compacted_tool_outputs: int
    fallback_used: bool = False
    fallback_reason: str = ""
    confidence: float = 1.0

    @property
    def saved_ratio(self) -> float:
        if self.raw_tokens <= 0:
            return 0.0
        return max(0.0, 1.0 - self.selected_tokens / self.raw_tokens)

    def public_dict(self) -> dict:
        # Deliberately aggregate-only: never expose prompt text or hidden items.
        return {
            "strategy": self.strategy,
            "raw_tokens": self.raw_tokens,
            "selected_tokens": self.selected_tokens,
            "budget_tokens": self.budget_tokens,
            "saved_ratio": round(self.saved_ratio, 4),
            "recent_messages": self.recent_messages,
            "selected_old_messages": self.selected_old_messages,
            "memory_items": self.memory_items,
            "compacted_tool_outputs": self.compacted_tool_outputs,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class PreparedContext:
    messages: tuple[ContextMessage, ...]
    memories: tuple[TaskMemoryItem, ...]
    stats: ContextStats


class ContextStrategy(Protocol):
    name: str

    def prepare(
        self,
        messages: Iterable[ContextMessage],
        *,
        current_message: str,
        memories: Iterable[TaskMemoryItem],
        budget: ContextBudget,
        relevance: Callable[[str, str], float] | None = None,
    ) -> PreparedContext: ...


def _terms(text: str) -> set[str]:
    return {m.group(0).casefold() for m in _WORD_RE.finditer(text) if len(m.group(0)) > 1}


def lexical_relevance(query: str, text: str) -> float:
    q = _terms(query)
    if not q:
        return 0.0
    t = _terms(text)
    if not t:
        return 0.0
    overlap = len(q & t)
    return overlap / math.sqrt(max(1, len(q) * len(t)))


class BalancedContextStrategy:
    """Deterministic recent+relevant selection with safe fallback.

    It is intentionally algorithm-neutral. Future TOMC/LCC implementations can
    implement ``ContextStrategy`` and be registered without coupling providers,
    storage, or UI code to one compression algorithm.
    """

    name = "balanced-v1"

    def __init__(self, *, recent_window: int = 8, min_confidence: float = 0.18) -> None:
        self.recent_window = max(2, recent_window)
        self.min_confidence = min(max(min_confidence, 0.0), 1.0)
        self.tool_compactor = ToolOutputCompactor()

    def _score(
        self,
        message: ContextMessage,
        query: str,
        recency: float,
        relevance: Callable[[str, str], float] | None,
    ) -> float:
        if relevance is not None:
            try:
                related = max(0.0, min(1.0, float(relevance(query, message.text))))
            except Exception:
                related = lexical_relevance(query, message.text)
        else:
            related = lexical_relevance(query, message.text)
        importance = 0.15 if _IMPORTANCE_RE.search(message.text) else 0.0
        role_bonus = 0.04 if message.role == "user" else 0.0
        pin_bonus = 2.0 if message.pinned else 0.0
        return pin_bonus + related * 0.68 + recency * 0.22 + importance + role_bonus

    def prepare(
        self,
        messages: Iterable[ContextMessage],
        *,
        current_message: str,
        memories: Iterable[TaskMemoryItem] = (),
        budget: ContextBudget,
        relevance: Callable[[str, str], float] | None = None,
    ) -> PreparedContext:
        source = list(messages)
        memory_source = list(memories)
        raw_tokens = sum(estimate_tokens(m.text) + 4 for m in source)
        dynamic_budget = budget.dynamic_tokens
        if not source or dynamic_budget <= 0:
            stats = ContextStats(
                self.name, raw_tokens, 0, dynamic_budget, 0, 0, 0, 0,
                fallback_used=bool(source), fallback_reason="no_dynamic_budget" if source else "",
                confidence=0.0 if source else 1.0,
            )
            return PreparedContext((), (), stats)

        recent_start = max(0, len(source) - self.recent_window)
        compacted_count = 0
        normalized: list[ContextMessage] = []
        for idx, message in enumerate(source):
            if message.kind == "tool" and idx < recent_start:
                compacted = self.tool_compactor.compact(message.text, raw_ref=message.source_ref or None)
                if compacted.compacted:
                    compacted_count += 1
                normalized.append(ContextMessage(
                    message.role,
                    compacted.text,
                    compacted.raw_ref,
                    message.kind,
                    message.pinned,
                ))
            else:
                normalized.append(message)

        recent = normalized[recent_start:]
        older = normalized[:recent_start]
        selected_recent: list[ContextMessage] = []
        remaining = dynamic_budget

        # Always prefer the newest messages. If the recent window itself exceeds
        # budget, keep as many complete newest messages as fit.
        for item in reversed(recent):
            cost = estimate_tokens(item.text) + 4
            if cost <= remaining or not selected_recent:
                selected_recent.append(item)
                remaining = max(0, remaining - cost)
            else:
                break
        selected_recent.reverse()

        memory_budget = min(remaining, int(dynamic_budget * budget.memory_fraction))
        selected_memories: list[TaskMemoryItem] = []
        memory_ranked = sorted(
            memory_source,
            key=lambda m: (
                1 if m.pinned else 0,
                lexical_relevance(current_message, m.text),
                1 if _IMPORTANCE_RE.search(m.text) else 0,
            ),
            reverse=True,
        )
        for item in memory_ranked:
            cost = estimate_tokens(item.text) + 4
            if cost <= memory_budget:
                selected_memories.append(item)
                memory_budget -= cost
                remaining -= cost

        scored: list[tuple[float, int, ContextMessage]] = []
        for idx, message in enumerate(older):
            recency = (idx + 1) / max(1, len(older))
            scored.append((self._score(message, current_message, recency, relevance), idx, message))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

        selected_old: list[tuple[int, ContextMessage]] = []
        top_relevance = scored[0][0] if scored else 1.0
        for score, idx, message in scored:
            cost = estimate_tokens(message.text) + 4
            if cost <= remaining:
                selected_old.append((idx, message))
                remaining -= cost

        # Confidence is intentionally conservative. A long old history with no
        # topical overlap should expand context instead of pretending selection is
        # certain. Pinned/important messages still contribute a small floor.
        confidence = min(1.0, top_relevance)
        fallback_used = False
        fallback_reason = ""
        if older and confidence < self.min_confidence and remaining > 0:
            fallback_used = True
            fallback_reason = "low_relevance_confidence"
            chosen = {idx for idx, _ in selected_old}
            for idx in range(len(older) - 1, -1, -1):
                if idx in chosen:
                    continue
                message = older[idx]
                cost = estimate_tokens(message.text) + 4
                if cost <= remaining:
                    selected_old.append((idx, message))
                    remaining -= cost

        selected_old.sort(key=lambda item: item[0])
        final_messages = [message for _, message in selected_old] + selected_recent
        selected_tokens = (
            sum(estimate_tokens(m.text) + 4 for m in final_messages)
            + sum(estimate_tokens(m.text) + 4 for m in selected_memories)
        )
        stats = ContextStats(
            strategy=self.name,
            raw_tokens=raw_tokens,
            selected_tokens=selected_tokens,
            budget_tokens=dynamic_budget,
            recent_messages=len(selected_recent),
            selected_old_messages=len(selected_old),
            memory_items=len(selected_memories),
            compacted_tool_outputs=compacted_count,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            confidence=confidence,
        )
        return PreparedContext(tuple(final_messages), tuple(selected_memories), stats)


class ContextEngine:
    """Provider-agnostic registry/facade for model context preparation."""

    def __init__(self) -> None:
        self._strategies: dict[str, ContextStrategy] = {}
        self.register(BalancedContextStrategy())
        self._default = BalancedContextStrategy.name

    def register(self, strategy: ContextStrategy) -> None:
        name = getattr(strategy, "name", "")
        if not isinstance(name, str) or not name:
            raise ValueError("context strategy requires a stable name")
        self._strategies[name] = strategy

    def prepare(self, *args, strategy: str | None = None, **kwargs) -> PreparedContext:
        selected = strategy or self._default
        try:
            implementation = self._strategies[selected]
        except KeyError as exc:
            raise ValueError(f"unknown context strategy: {selected}") from exc
        return implementation.prepare(*args, **kwargs)

    def strategy_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))


INTERNAL_TERSE_INSTRUCTION = (
    "Return only the information the next internal agent needs: decisions, state, "
    "errors, changed artifacts, and next actions. Omit conversational filler."
)


def internal_agent_instruction(*, terse: bool, final_user_response: bool = False) -> str:
    """Caveman/terse mode is allowed only for internal agent-to-agent messages."""
    if final_user_response or not terse:
        return ""
    return INTERNAL_TERSE_INSTRUCTION


def stable_static_prompt(parts: Iterable[str]) -> str:
    """Deterministic static prompt serialization for provider prompt caches."""
    return "\n\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
