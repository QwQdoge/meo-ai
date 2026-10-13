from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Iterable

from .backend_adapter import ModelInfo
from .model_roles import ModelRoleRegistry


@dataclass(frozen=True)
class VerificationOutcome:
    text: str
    metadata: dict


def _extract_json_object(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            raise ValueError("judge did not return JSON")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("judge response must be a JSON object")
    return payload


class JudgeVerifier:
    """Bounded verifier/repair loop for execution answers.

    The backend must expose `generate_auxiliary(model_id, prompt, system_prompt)`.
    Auxiliary calls do not enter the visible conversation history, which keeps
    verification and repair prompts out of the user's chat transcript.
    """

    def __init__(self, backend, roles: ModelRoleRegistry, max_repairs: int = 1) -> None:
        self._backend = backend
        self._roles = roles
        self._max_repairs = max(0, int(max_repairs))

    @property
    def available(self) -> bool:
        return callable(getattr(self._backend, "generate_auxiliary", None))

    @staticmethod
    def _judge_prompt(request_text: str, candidate: str) -> str:
        return (
            "Evaluate the candidate answer against the user's request. Check factual/internal consistency, "
            "whether requested implementation work is actually completed, and whether any claimed result is unsupported. "
            "Do not rewrite the answer. Return JSON only with exactly these keys: "
            '{"verdict":"ACCEPT|REVISE","issues":["..."],"confidence":0.0}.\n\n'
            f"USER REQUEST:\n{request_text}\n\nCANDIDATE ANSWER:\n{candidate}"
        )

    @staticmethod
    def _repair_prompt(request_text: str, candidate: str, issues: list[str]) -> str:
        issue_text = "\n".join(f"- {item}" for item in issues) or "- Address the verifier's rejection."
        return (
            "Produce a corrected final answer for the user. Preserve correct useful material from the candidate, "
            "fix every verifier issue, and do not mention this verification process. Return only the revised answer.\n\n"
            f"USER REQUEST:\n{request_text}\n\nCANDIDATE ANSWER:\n{candidate}\n\nISSUES TO FIX:\n{issue_text}"
        )

    @staticmethod
    def _parse_judgement(text: str) -> tuple[str, list[str], float | None]:
        payload = _extract_json_object(text)
        verdict = str(payload.get("verdict", "")).strip().upper()
        if verdict not in {"ACCEPT", "REVISE"}:
            raise ValueError("judge verdict must be ACCEPT or REVISE")
        raw_issues = payload.get("issues", [])
        issues = [str(item).strip() for item in raw_issues if str(item).strip()] if isinstance(raw_issues, list) else []
        raw_confidence = payload.get("confidence")
        confidence: float | None = None
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        return verdict, issues, confidence

    @staticmethod
    def _metadata(status: str, *, checked: bool, verified: bool, **extra) -> dict:
        return {
            "status": status,
            "checked": checked,
            "verified": verified,
            **extra,
        }

    def verify(
        self,
        request_text: str,
        candidate: str,
        models: Iterable[ModelInfo],
        execution_model_id: str,
    ) -> VerificationOutcome:
        if not candidate.strip():
            return VerificationOutcome(
                candidate,
                self._metadata("skipped", checked=False, verified=False, reason="empty_candidate"),
            )
        generate = getattr(self._backend, "generate_auxiliary", None)
        if not callable(generate):
            return VerificationOutcome(
                candidate,
                self._metadata(
                    "unavailable",
                    checked=False,
                    verified=False,
                    reason="backend_no_auxiliary_generation",
                ),
            )

        catalog = list(models)
        try:
            judge_model_id, judge_fallback = self._roles.resolve_model("judge", catalog)
        except Exception as exc:
            return VerificationOutcome(
                candidate,
                self._metadata("unavailable", checked=False, verified=False, reason=str(exc)),
            )

        current = candidate
        attempts: list[dict] = []
        for repair_index in range(self._max_repairs + 1):
            try:
                judgement_text = generate(
                    judge_model_id,
                    self._judge_prompt(request_text, current),
                    [
                        "You are Meo AI's verifier. Be strict but practical. "
                        "Never claim tools ran unless the candidate provides evidence. Output valid JSON only."
                    ],
                )
                verdict, issues, confidence = self._parse_judgement(judgement_text)
            except Exception as exc:
                return VerificationOutcome(
                    current,
                    self._metadata(
                        "unavailable",
                        checked=False,
                        verified=False,
                        reason=str(exc),
                        judge_model_id=judge_model_id,
                        attempts=attempts,
                    ),
                )

            attempts.append(
                {
                    "verdict": verdict,
                    "issues": issues,
                    "confidence": confidence,
                }
            )
            if verdict == "ACCEPT":
                return VerificationOutcome(
                    current,
                    self._metadata(
                        "accepted" if repair_index == 0 else "accepted_after_repair",
                        checked=True,
                        verified=True,
                        judge_model_id=judge_model_id,
                        judge_fallback_used=judge_fallback,
                        repair_count=repair_index,
                        attempts=attempts,
                    ),
                )

            if repair_index >= self._max_repairs:
                break
            try:
                current = generate(
                    execution_model_id,
                    self._repair_prompt(request_text, current, issues),
                    [
                        "You are the execution model repairing a candidate answer after verification. "
                        "Return only the corrected user-facing answer."
                    ],
                ).strip()
            except Exception as exc:
                return VerificationOutcome(
                    candidate,
                    self._metadata(
                        "repair_failed",
                        checked=True,
                        verified=False,
                        reason=str(exc),
                        judge_model_id=judge_model_id,
                        attempts=attempts,
                    ),
                )
            if not current:
                return VerificationOutcome(
                    candidate,
                    self._metadata(
                        "repair_failed",
                        checked=True,
                        verified=False,
                        reason="repair model returned an empty answer",
                        judge_model_id=judge_model_id,
                        attempts=attempts,
                    ),
                )

        return VerificationOutcome(
            current,
            self._metadata(
                "rejected_after_repair",
                checked=True,
                verified=False,
                judge_model_id=judge_model_id,
                judge_fallback_used=judge_fallback,
                repair_count=self._max_repairs,
                attempts=attempts,
            ),
        )