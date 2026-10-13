from __future__ import annotations

from dataclasses import dataclass
import re
import threading
from typing import Iterable

from meo.service.backend_adapter import BackendCallbacks, InputResource, ModelInfo
from meo.service.coordinator import LocalSubagentCoordinator
from meo.service.model_roles import ModelRoleRegistry
from meo.service.verification import JudgeVerifier


_CODING_TERMS = (
    "bug", "fix", "debug", "code", "coding", "compile", "compiler", "build", "test",
    "cpp", "c++", "python", "rust", "java", "javascript", "typescript", "qml", "qt",
    "repo", "repository", "git", "linux", "backend", "frontend", "api", "sql",
    "修复", "代码", "编译", "测试", "仓库", "项目", "前端", "后端", "报错",
)
_ACTION_TERMS = (
    "fix", "debug", "change", "edit", "update", "create", "delete", "run", "execute",
    "install", "configure", "modify", "commit", "merge", "deploy", "open", "write", "apply",
    "implement", "修复", "修改", "更新", "创建", "删除", "运行", "执行", "安装", "配置",
    "提交", "合并", "部署", "实现", "做",
)
_REASONING_TERMS = (
    "analyze", "analyse", "compare", "evaluate", "reason", "plan", "strategy", "architecture",
    "why", "tradeoff", "trade-off", "investigate", "review", "design", "分析", "比较", "评估",
    "为什么", "计划", "架构", "权衡", "调查", "审查", "设计",
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


class DeterministicModelRouter:
    """Small, inspectable request router.

    Deterministic rules handle ordinary routing first. Complex execution may
    receive bounded read-only subagent context and a model-assisted Judge.
    """

    @staticmethod
    def _contains_any(text: str, terms: Iterable[str]) -> bool:
        lowered = text.casefold()
        return any(term.casefold() in lowered for term in terms)

    def classify(self, text: str, resources: tuple[InputResource, ...] = ()) -> dict:
        normalized = " ".join(text.split())
        lowered = normalized.casefold()
        needs_vision = any(
            resource.kind == "image"
            or resource.mime_type.split(";", 1)[0].strip().casefold().startswith("image/")
            for resource in resources
        )
        coding = self._contains_any(normalized, _CODING_TERMS)
        action = self._contains_any(normalized, _ACTION_TERMS)
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
        elif coding and action:
            role_id = "execution"
            intent = "coding"
        elif action:
            role_id = "execution"
            intent = "action"
        elif reasoning or long_prompt:
            role_id = "reasoning"
            intent = "reasoning"
        else:
            role_id = "chat"
            intent = "chat"

        needs_tools = role_id == "execution"
        needs_reasoning = role_id in {"reasoning", "execution"} or (
            needs_vision and (reasoning or long_prompt)
        )
        if complex_prompt or (coding and reasoning) or (action and long_prompt):
            complexity = "high"
        elif reasoning or long_prompt or coding or needs_vision:
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
    spans the entire request, including auxiliary subagent, Judge, and repair
    calls, so parallel requests cannot silently switch each other's model.
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
            outcome = self._coordinator.prepare(text, models, emit=callbacks.on_tool_event)
            coordination = outcome.metadata
            if outcome.context:
                backend_text = outcome.context + text

        should_verify = decision.role_id == "execution" and self._verifier.available
        buffered_text: list[str] = []
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

        def on_text_delta(delta: str) -> None:
            if should_verify:
                buffered_text.append(delta)
            else:
                callbacks.on_text_delta(delta)

        def on_tool_event(event: dict) -> None:
            if event.get("type") == "response_meta":
                enriched = self._enrich_meta(event, decision, coordination=coordination)
                if should_verify:
                    pending_meta[:] = [enriched]
                    return
                callbacks.on_tool_event(enriched)
                return
            callbacks.on_tool_event(event)

        def on_done() -> None:
            if not should_verify:
                release()
                callbacks.on_done()
                return

            candidate = "".join(buffered_text)
            outcome = self._verifier.verify(text, candidate, models, decision.model_id)
            if outcome.text:
                callbacks.on_text_delta(outcome.text)
            meta = pending_meta[0] if pending_meta else {"type": "response_meta", "activity": {}}
            callbacks.on_tool_event(
                self._enrich_meta(meta, decision, outcome.metadata, coordination=coordination)
            )
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

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        return self._send(conversation_id, text, (), callbacks)

    def send_message_with_resources(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ):
        return self._send(conversation_id, text, resources, callbacks)
