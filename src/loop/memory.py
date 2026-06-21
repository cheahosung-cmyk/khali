"""State and memory for Loop Engineering — tracks what was tried and why it failed.

Each iteration runs with a fresh context window, so the loop must persist its own
history of attempts and failures. Without this, the agent repeats the same mistakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .action import ActionResult, ActionStatus
from .verifier import VerificationResult


@dataclass
class LoopIteration:
    index: int
    started_at: datetime
    finished_at: datetime | None = None
    action_result: ActionResult | None = None
    verification: VerificationResult | None = None
    stop_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return (
            self.action_result is not None
            and self.action_result.status == ActionStatus.SUCCESS
            and (self.verification is None or self.verification.passed)
        )

    @property
    def cost(self) -> float:
        return self.action_result.cost if self.action_result else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "succeeded": self.succeeded,
            "cost": self.cost,
            "action_status": self.action_result.status.value if self.action_result else None,
            "action_error": self.action_result.error if self.action_result else None,
            "verification_passed": self.verification.passed if self.verification else None,
            "verification_score": self.verification.score if self.verification else None,
            "stop_reason": self.stop_reason,
        }


class LoopMemory:
    """Persists iteration history so each new iteration can learn from prior failures."""

    def __init__(self):
        self._iterations: list[LoopIteration] = []
        self._total_cost: float = 0.0

    @property
    def iterations(self) -> list[LoopIteration]:
        return list(self._iterations)

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def iteration_count(self) -> int:
        return len(self._iterations)

    def start_iteration(self) -> LoopIteration:
        iteration = LoopIteration(
            index=len(self._iterations),
            started_at=datetime.now(timezone.utc),
        )
        self._iterations.append(iteration)
        return iteration

    def complete_iteration(
        self,
        iteration: LoopIteration,
        action_result: ActionResult,
        verification: VerificationResult | None = None,
        stop_reason: str | None = None,
    ) -> None:
        iteration.finished_at = datetime.now(timezone.utc)
        iteration.action_result = action_result
        iteration.verification = verification
        iteration.stop_reason = stop_reason
        self._total_cost += action_result.cost

    def failed_attempts(self) -> list[LoopIteration]:
        return [it for it in self._iterations if it.action_result is not None and not it.succeeded]

    def failure_summary(self) -> str:
        failures = self.failed_attempts()
        if not failures:
            return "no failures recorded"
        lines = [f"iteration {f.index}: {f.action_result.error or 'unknown error'}" for f in failures]
        return "\n".join(lines)

    def to_context(self) -> dict[str, Any]:
        """Serialize memory into the context dict passed to each new iteration."""
        return {
            "iteration": self.iteration_count,
            "total_cost": self._total_cost,
            "failure_summary": self.failure_summary(),
            "last_iteration": self._iterations[-1].to_dict() if self._iterations else None,
        }
