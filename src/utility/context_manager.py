from .media import audio_text
import copy
from dataclasses import dataclass, field
from .strings import count_message_tokens, remove_thinking_blocks

from meo.service.context_engine import (
    ContextBudget,
    ContextEngine,
    ContextMessage,
    estimate_tokens,
)


SUMMARIZE_PROMPT = """Summarize the following conversation messages into a concise paragraph.
Preserve key facts, decisions, tool results, and any information that may be needed for the ongoing conversation.
Only output the summary, no other text.

Messages:
{messages}"""


@dataclass
class TrimResult:
    """Result of a context trim operation plus aggregate diagnostics.

    Diagnostics are safe to expose in UI because they contain counts only, never
    hidden prompt text or private message contents.
    """

    history: list = field(default_factory=list)
    original_tokens: int = 0
    trimmed_tokens: int = 0
    suggested_tokens: int = 0
    max_tokens: int = 0
    strategy: str = "balanced-v1"
    recent_messages: int = 0
    selected_old_messages: int = 0
    memory_items: int = 0
    compacted_tool_outputs: int = 0
    fallback_used: bool = False
    fallback_reason: str = ""
    confidence: float = 1.0

    @property
    def saved_ratio(self) -> float:
        if self.original_tokens <= 0:
            return 0.0
        return max(0.0, 1.0 - self.trimmed_tokens / self.original_tokens)

    def public_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "original_tokens": self.original_tokens,
            "trimmed_tokens": self.trimmed_tokens,
            "suggested_tokens": self.suggested_tokens,
            "max_tokens": self.max_tokens,
            "saved_ratio": round(self.saved_ratio, 4),
            "recent_messages": self.recent_messages,
            "selected_old_messages": self.selected_old_messages,
            "memory_items": self.memory_items,
            "compacted_tool_outputs": self.compacted_tool_outputs,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "confidence": round(self.confidence, 3),
        }


class ContextManager:
    """Compatibility wrapper around the provider-agnostic Meo ContextEngine.

    Newelle still owns the legacy chat-record format. The selection/compression
    policy lives in ``meo.service.context_engine`` so Web/native/remote backends
    can share it without importing GTK or controller code.
    """

    RECENT_WINDOW = 8
    TOKEN_OVERHEAD_PER_MSG = 4

    def __init__(
        self,
        max_tokens: int,
        suggested_tokens: int,
        embedding_handler=None,
        llm_handler=None,
        summarization_enabled: bool = False,
    ):
        self.max_tokens = max_tokens
        self.suggested_tokens = suggested_tokens
        self.embedding_handler = embedding_handler
        self.llm_handler = llm_handler
        self.summarization_enabled = summarization_enabled
        self.engine = ContextEngine()

    def trim(
        self,
        history: list[dict[str, str]],
        prompts_token_count: int,
        current_message: str,
    ) -> TrimResult:
        if not history:
            return TrimResult(
                history=history,
                suggested_tokens=self.suggested_tokens,
                max_tokens=self.max_tokens,
            )

        original_history = copy.deepcopy(history)
        raw_tokens = sum(
            count_message_tokens(audio_text(m.get("Message", ""))) + self.TOKEN_OVERHEAD_PER_MSG
            for m in original_history
        ) + prompts_token_count

        # Fast path preserves the historical behavior and avoids modifying tool
        # output when no compression is needed.
        if raw_tokens <= self.suggested_tokens:
            return TrimResult(
                history=original_history,
                original_tokens=raw_tokens,
                trimmed_tokens=raw_tokens,
                suggested_tokens=self.suggested_tokens,
                max_tokens=self.max_tokens,
                recent_messages=min(len(original_history), self.RECENT_WINDOW),
            )

        messages: list[ContextMessage] = []
        originals: dict[str, dict] = {}
        for index, entry in enumerate(original_history):
            source_ref = f"history:{index}"
            originals[source_ref] = entry
            source_role = entry.get("User", "User")
            role = {
                "User": "user",
                "Assistant": "assistant",
                "Console": "tool",
            }.get(source_role, str(source_role).casefold())
            messages.append(ContextMessage(
                role=role,
                text=audio_text(entry.get("Message", "")),
                source_ref=source_ref,
                kind="tool" if source_role == "Console" else "message",
            ))

        relevance = self._relevance_callback(messages, audio_text(current_message))
        dynamic_budget = max(1, min(self.suggested_tokens, self.max_tokens) - prompts_token_count)
        prepared = self.engine.prepare(
            messages,
            current_message=audio_text(current_message),
            memories=(),
            budget=ContextBudget(total_tokens=dynamic_budget),
            relevance=relevance,
        )

        selected_refs = {message.source_ref for message in prepared.messages}
        dropped = [
            entry for index, entry in enumerate(original_history)
            if f"history:{index}" not in selected_refs
        ]

        result_history: list[dict] = []
        if dropped and self.summarization_enabled and self.llm_handler is not None:
            summary = self._summarize_dropped(dropped)
            if summary:
                result_history.append({
                    "User": "User",
                    "Message": f"[Previous conversation summary]\n{summary}",
                })

        for selected in prepared.messages:
            base = copy.deepcopy(originals.get(selected.source_ref, {}))
            if not base:
                continue
            # Only the model-facing copy is compacted. The controller's raw chat
            # remains unchanged and can still be reopened/retrieved later.
            base["Message"] = selected.text
            if selected.kind == "tool" and selected.source_ref:
                base["MeoRawSourceRef"] = selected.source_ref
            result_history.append(base)

        trimmed_tokens = sum(
            count_message_tokens(audio_text(m.get("Message", ""))) + self.TOKEN_OVERHEAD_PER_MSG
            for m in result_history
        ) + prompts_token_count

        # Summary generation can occasionally exceed the target. Preserve the
        # hard max invariant by dropping the summary first; recent raw turns are
        # more authoritative than a generated summary.
        if trimmed_tokens > self.max_tokens and result_history and str(result_history[0].get("Message", "")).startswith("[Previous conversation summary]"):
            result_history.pop(0)
            trimmed_tokens = sum(
                count_message_tokens(audio_text(m.get("Message", ""))) + self.TOKEN_OVERHEAD_PER_MSG
                for m in result_history
            ) + prompts_token_count

        stats = prepared.stats
        return TrimResult(
            history=result_history,
            original_tokens=raw_tokens,
            trimmed_tokens=trimmed_tokens,
            suggested_tokens=self.suggested_tokens,
            max_tokens=self.max_tokens,
            strategy=stats.strategy,
            recent_messages=stats.recent_messages,
            selected_old_messages=stats.selected_old_messages,
            memory_items=stats.memory_items,
            compacted_tool_outputs=stats.compacted_tool_outputs,
            fallback_used=stats.fallback_used,
            fallback_reason=stats.fallback_reason,
            confidence=stats.confidence,
        )

    def _relevance_callback(self, messages: list[ContextMessage], query: str):
        """Use embeddings in one batch when available; otherwise engine lexical scoring."""
        if self.embedding_handler is None or not query or not messages:
            return None
        try:
            texts = [message.text for message in messages]
            query_emb = self.embedding_handler.get_embedding([query], purpose="query")[0]
            message_embeddings = self.embedding_handler.get_embedding(texts, purpose="document")
            by_text: dict[str, float] = {}
            norm_q = float(sum(a * a for a in query_emb)) ** 0.5
            for text, msg_emb in zip(texts, message_embeddings):
                dot = float(sum(a * b for a, b in zip(query_emb, msg_emb)))
                norm_m = float(sum(a * a for a in msg_emb)) ** 0.5
                by_text[text] = dot / (norm_q * norm_m) if norm_q > 0 and norm_m > 0 else 0.0
            return lambda _query, text: by_text.get(text, 0.0)
        except Exception:
            return None

    def _summarize_dropped(self, messages: list[dict]) -> str:
        try:
            formatted = []
            for msg in messages:
                role = msg.get("User", "User")
                content = audio_text(msg.get("Message", ""))
                if len(content) > 300:
                    content = content[:300] + "..."
                formatted.append(f"{role}: {content}")
            messages_text = "\n".join(formatted)
            if not messages_text.strip():
                return ""
            prompt = SUMMARIZE_PROMPT.format(messages=messages_text)
            summary = self.llm_handler.generate_text(prompt)
            return remove_thinking_blocks(summary).strip()
        except Exception:
            return ""
