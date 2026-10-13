from __future__ import annotations

from dataclasses import dataclass
import re
import threading
from typing import Iterable

from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo
from meo.service.conversation_digest import ConversationDigestGenerator
from meo.service.coordinator import LocalSubagentCoordinator
from meo.service.model_roles import ModelRoleRegistry
from meo.service.verification import JudgeVerifier


_CODING_TERMS = (
    "bug", "fix", "debug", "code", "coding", "compile", "compiler", "build", "test",
    "cpp", "c++", "python", "rust", "java", "javascript", "typescript", "qml", "qt",
    "repo", "repository", "git", "linux", "backend", "frontend", "api", "sql",
    "修复", "代码", "编译", "测试", "仓库", "项目", "前端", "后端", "报错",
)
_EXECUTION_TERMS = (
    "fix", "debug", "edit", "update", "delete", "run", "execute", "install", "configure",
    "modify", "commit", "merge", "deploy", "apply patch", "patch", "implement",
    "open settings", "open bluetooth", "open wi-fi", "open wifi",
    "修复", "调试", "修改", "更新", "删除", "运行", "执行", "安装", "配置", "提交", "合并",
    "部署", "实现", "应用补丁", "打开设置", "打开蓝牙", "打开无线网络",
)
_CODE_CREATION_TERMS = (
    "write", "create", "generate", "implement", "build", "make",
    "写", "生成", "创建", "实现",
)
_REASONING_TERMS = (
    "analyze", "analyse", "compare", "evaluate", "reason", "plan", "strategy", "architecture",
    "why", "tradeoff", "trade-off", "investigate", "review", "design", "explain", "summarize",
    "summary", "分析", "比较", "评估", "为什么", "计划", "架构", "权衡", "调查", "审查", "设计",
    "解释", "总结", "概括",
)
_SIMPLE_CHAT_PREFIXES = (
    "hi", "hello", "hey", "thanks", "thank you", "你好", "嗨", "谢谢",
)


@dataclass(frozen=True)
class RouteDecision:
    role_id: str
    model_id: str
    intent: str
    needs_tools: bool
    needs_reasoning: bool
    needs_vision: bool
    complexity: str
    fallback_used: bool

    def public_dict(self) -> dict:
        return {
            "role_id": self.role_id,
            "model_id": self.model_id,
            "intent": self.intent,
            "needs_tools": self.needs_tools,
            "needs_reasoning": self.needs_reasoning,
            "needs_vision": self.needs_vision,
            "complexity": self.complexity,
            "fallback_used": self.fallback_used,
        }


class _DeferredExecutionHandle:
    """Stable AgentService handle while routed startup happens in a worker.

    High-complexity execution may spend several provider calls in Coordinator
    before the legacy backend can return its real execution handle. Returning
    this proxy immediately lets AgentService open its callback gate, so progress
    cards are visible while planning is still running. Tool choices and cancel
    requests remain safe if they race the eventual legacy handle.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._delegate: object | None = None
        self._cancel_requested = False
        self._pending_options: list[int] = []
        self.worker: threading.Thread | None = None

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    def bind(self, delegate: object) -> tuple[bool, tuple[int, ...]]:
        with self._lock:
            self._delegate = delegate
            if self._cancel_requested:
                self._pending_options.clear()
                return True, ()
            pending = tuple(self._pending_options)
            self._pending_options.clear()
            return False, pending

    def request_cancel(self) -> object | None:
        with self._lock:
            self._cancel_requested = True
            self._pending_options.clear()
            return self._delegate

    def queue_option(self, legacy_option_index: int) -> object | None:
        with self._lock:
            if self._cancel_requested:
                raise ValueError("request is cancelling")
            if self._delegate is None:
                self._pending_options.append(legacy_option_index)
                return None
            return self._delegate


class DeterministicModelRouter:
    """Small, inspectable request router.

    Deterministic rules handle ordinary routing first. Complex execution may
    receive bounded read-only subagent context and a model-assisted Judge.
    """

    @staticmethod
    def _term_matches(text: str, term: str) -> bool:
        lowered = text.casefold()
        token = term.casefold()
        # CJK has no reliable ASCII-style word boundaries; multi-character
        # intent phrases are intentionally explicit enough for substring use.
        if any("\u3400" <= char <= "\u9fff" for char in token):
            return token in lowered
        # English technical tokens must be bounded. This prevents terms such as
        # "open"/"api" from accidentally matching OpenAI or unrelated words.
        return re.search(
            rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])",
            lowered,
        ) is not None

    @classmethod
    def _contains_any(cls, text: str, terms: Iterable[str]) -> bool:
        return any(cls._term_matches(text, term) for term in terms)

    def classify(self, text: str, resources: tuple[InputResource, ...] = ()) -> dict:
        normalized = " ".join(text.split())
        lowered = normalized.casefold()
        needs_vision = any(
            resource.kind == "image"
            or resource.mime_type.split(";", 1)[0].strip().casefold().startswith("image/")
            for resource in resources
        )
        coding = self._contains_any(normalized, _CODING_TERMS)
        execution_action = self._contains_any(normalized, _EXECUTION_TERMS)
        code_creation = coding and self._contains_any(normalized, _CODE_CREATION_TERMS)
        reasoning = self._contains_any(normalized, _REASONING_TERMS)
        long_prompt = len(normalized) >= 700 or text.count("\n") >= 8
        complex_prompt = len(normalized) >= 1500 or len(
            re.findall(r"\b(?:and|then|also|同时|然后|以及)\b", lowered)
        ) >= 4
        simple_chat = len(normalized) <= 160 and any(
            lowered.startswith(prefix) for prefix in _SIMPLE_CHAT_PREFIXES
        )

        if needs_vision:
            role_id = "vision"
            intent = "vision"
        elif coding and (execution_action or code_creation):
            role_id = "execution"
            intent = "coding"
        elif execution_action:
            role_id = "execution"
            intent = "action"
        elif coding:
            role_id = "reasoning"
            intent = "coding_analysis"
        elif reasoning or long_prompt:
            role_id = "reasoning"
            intent = "reasoning"
        else:
            role_id = "chat"
            intent = "chat"

        # Execution model selection is not the same thing as tool authority.
        # Pure code generation can benefit from the execution model/Judge while
        # still requiring no shell/filesystem action.
        needs_tools = execution_action
        needs_reasoning = role_id in {"reasoning", "execution"} or (
            needs_vision and (reasoning or long_prompt)
        )
        if complex_prompt or (coding and reasoning) or (execution_action and long_prompt):
            complexity = "high"
        elif reasoning or long_prompt or coding or needs_vision or execution_action:
            complexity = "medium"
        elif simple_chat:
            complexity = "low"
        else:
            complexity = "low"
        return {
            "role_id": role_id,
            "intent": intent,
            "needs_tools": needs_tools,
            "needs_reasoning": needs_reasoning,
            "needs_vision": needs_vision,
            "complexity": complexity,
        }

    def decide(
        self,
        text: str,
        resources: tuple[InputResource, ...],
        models: Iterable[ModelInfo],
        roles: ModelRoleRegistry,
    ) -> RouteDecision:
        catalog = list(models)
        features = self.classify(text, resources)
        eligible = catalog
        if features["needs_vision"]:
            eligible = [item for item in catalog if item.supports_vision]
            if not eligible:
                raise ValueError("no vision-capable model is available for this image request")
        model_id, fallback_used = roles.resolve_model(features["role_id"], eligible)
        return RouteDecision(
            model_id=model_id,
            fallback_used=fallback_used,
            **features,
        )


class RoutedBackend:
    """Request routing, bounded coordination, and execution verification.

    Legacy Newelle model selection mutates profile settings. A lease therefore
    spans the entire request, including auxiliary subagent, Judge, digest, and
    repair calls, so parallel requests cannot silently switch each other's model.
    """

    def __init__(
        self,
        backend,
        roles: ModelRoleRegistry,
        router: DeterministicModelRouter | None = None,
    ) -> None:
        self._backend = backend
        self._roles = roles
        self._router = router or DeterministicModelRouter()
        self._coordinator = LocalSubagentCoordinator(backend, roles, max_subagents=3)
        self._verifier = JudgeVerifier(backend, roles, max_repairs=1)
        self._digest = ConversationDigestGenerator(backend, roles)
        self._route_lock = threading.Lock()

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def list_models(self):
        return [
            ModelInfo(
                item.model_id,
                item.label,
                item.provider,
                selection_scope="request",
                selected=item.selected,
                supports_vision=item.supports_vision,
            )
            for item in self._backend.list_models()
        ]

    @staticmethod
    def _selected_model(models: Iterable[ModelInfo]) -> str:
        return next((item.model_id for item in models if item.selected), "")

    @staticmethod
    def _enrich_meta(
        event: dict,
        decision: RouteDecision,
        verification: dict | None = None,
        coordination: dict | None = None,
        conversation_digest: dict | None = None,
    ) -> dict:
        enriched = dict(event)
        enriched["type"] = "response_meta"
        enriched["routing"] = decision.public_dict()
        activity = dict(enriched.get("activity")) if isinstance(enriched.get("activity"), dict) else {}
        if decision.needs_vision:
            activity["vision"] = {"used": True}
        if decision.intent == "coding":
            activity["code"] = {"used": True}
        if coordination is not None:
            enriched["coordination"] = coordination
            activity["coordination"] = {
                "used": coordination.get("status") in {"completed", "failed"},
                "status": str(coordination.get("status", "")),
                "task_count": len(coordination.get("tasks", [])) if isinstance(coordination.get("tasks"), list) else 0,
            }
        if verification is not None:
            enriched["verification"] = verification
            activity["verification"] = {
                "used": True,
                "status": str(verification.get("status", "")),
            }
        if conversation_digest is not None:
            enriched["conversation_digest"] = conversation_digest
            activity["title_summary"] = {
                "used": conversation_digest.get("status") == "completed",
                "status": str(conversation_digest.get("status", "")),
            }
        enriched["activity"] = activity
        return enriched

    def _send(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ):
        self._route_lock.acquire()
        released = False
        models = list(self._backend.list_models())
        original_model = self._selected_model(models)
        try:
            decision = self._router.decide(text, resources, models, self._roles)
        except Exception:
            self._route_lock.release()
            raise

        coordination: dict | None = None
        backend_text = text
        if decision.role_id == "execution" and decision.complexity == "high" and self._coordinator.available:
            try:
                outcome = self._coordinator.prepare(text, models, emit=callbacks.on_tool_event)
                coordination = outcome.metadata
                if outcome.context:
                    backend_text = outcome.context + text
            except Exception as exc:
                # Coordination is an optimization. A planner/provider/UI bug must
                # never strand the request lock or block the real execution path.
                coordination = {
                    "status": "failed",
                    "reason": str(exc),
                    "tasks": [],
                }

        should_verify = decision.role_id == "execution" and self._verifier.available
        buffered_text: list[str] = []
        visible_text: list[str] = []
        pending_meta: list[dict] = []

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            try:
                if original_model and original_model != decision.model_id:
                    self._backend.set_model(conversation_id, original_model)
            finally:
                self._route_lock.release()

        def generate_digest(final_text: str) -> dict:
            if not final_text.strip():
                return {"status": "skipped", "reason": "empty_response"}
            try:
                return self._digest.maybe_generate(conversation_id, text, final_text, models).metadata
            except Exception as exc:
                # Titles and summaries are convenience metadata. They must never
                # turn a successful chat request into an error.
                return {"status": "failed", "reason": str(exc)}

        def publish_final_meta(verification: dict | None, digest: dict) -> None:
            meta = pending_meta[0] if pending_meta else {"type": "response_meta", "activity": {}}
            callbacks.on_tool_event(
                self._enrich_meta(
                    meta,
                    decision,
                    verification=verification,
                    coordination=coordination,
                    conversation_digest=digest,
                )
            )

        def on_text_delta(delta: str) -> None:
            if should_verify:
                buffered_text.append(delta)
            else:
                visible_text.append(delta)
                callbacks.on_text_delta(delta)

        def on_tool_event(event: dict) -> None:
            if event.get("type") == "response_meta":
                pending_meta[:] = [dict(event)]
                return
            callbacks.on_tool_event(event)

        def on_done() -> None:
            if not should_verify:
                digest = generate_digest("".join(visible_text))
                publish_final_meta(None, digest)
                release()
                callbacks.on_done()
                return

            candidate = "".join(buffered_text)
            outcome = self._verifier.verify(text, candidate, models, decision.model_id)
            final_text = outcome.text or candidate
            if final_text:
                callbacks.on_text_delta(final_text)
            digest = generate_digest(final_text)
            publish_final_meta(outcome.metadata, digest)
            release()
            callbacks.on_done()

        def on_error(error: str) -> None:
            if should_verify and buffered_text:
                callbacks.on_text_delta("".join(buffered_text))
            release()
            callbacks.on_error(error)

        wrapped = BackendCallbacks(
            on_text_delta=on_text_delta,
            on_tool_event=on_tool_event,
            on_done=on_done,
            on_error=on_error,
        )
        try:
            if decision.model_id and decision.model_id != original_model:
                self._backend.set_model(conversation_id, decision.model_id)
            if resources:
                method = getattr(self._backend, "send_message_with_resources", None)
                if not callable(method):
                    raise ValueError("selected backend does not support resource inputs")
                return method(conversation_id, backend_text, resources, wrapped)
            return self._backend.send_message(conversation_id, backend_text, wrapped)
        except Exception:
            release()
            raise

    def _should_defer_startup(self, text: str, resources: tuple[InputResource, ...]) -> bool:
        if not self._coordinator.available:
            return False
        try:
            features = self._router.classify(text, resources)
        except Exception:
            return False
        return features.get("role_id") == "execution" and features.get("complexity") == "high"

    def _send_deferred(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ) -> _DeferredExecutionHandle:
        proxy = _DeferredExecutionHandle()

        def run() -> None:
            if proxy.cancel_requested:
                callbacks.on_done()
                return
            try:
                delegate = self._send(conversation_id, text, resources, callbacks)
            except Exception as exc:
                callbacks.on_error(str(exc))
                return

            cancel_requested, pending_options = proxy.bind(delegate)
            if cancel_requested:
                try:
                    self._backend.cancel(delegate)
                except Exception as exc:
                    callbacks.on_error(str(exc))
                return
            for option_index in pending_options:
                try:
                    self._backend.choose_tool_option(delegate, option_index)
                except Exception as exc:
                    callbacks.on_error(str(exc))
                    return

        worker = threading.Thread(
            target=run,
            name="meo-routed-startup",
            daemon=True,
        )
        proxy.worker = worker
        worker.start()
        return proxy

    def choose_tool_option(self, execution_handle: object, legacy_option_index: int) -> None:
        if isinstance(execution_handle, _DeferredExecutionHandle):
            delegate = execution_handle.queue_option(legacy_option_index)
            if delegate is None:
                return
            self._backend.choose_tool_option(delegate, legacy_option_index)
            return
        self._backend.choose_tool_option(execution_handle, legacy_option_index)

    def cancel(self, execution_handle: object) -> None:
        if isinstance(execution_handle, _DeferredExecutionHandle):
            delegate = execution_handle.request_cancel()
            if delegate is not None:
                self._backend.cancel(delegate)
            return
        self._backend.cancel(execution_handle)

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        if self._should_defer_startup(text, ()):
            return self._send_deferred(conversation_id, text, (), callbacks)
        return self._send(conversation_id, text, (), callbacks)

    def send_message_with_resources(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ):
        if self._should_defer_startup(text, resources):
            return self._send_deferred(conversation_id, text, resources, callbacks)
        return self._send(conversation_id, text, resources, callbacks)