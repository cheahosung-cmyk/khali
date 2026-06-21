"""Loop Engine — the central orchestrator for Loop Engineering.

A loop has six components arranged in priority order:
  1. Trigger       — when does an iteration start?
  2. Action        — what does the iteration do?
  3. Stop condition — when does the loop halt? (budget first, observable tests second)
  4. Verifier      — is the output actually correct? (separate from the actor)
  5. Memory        — what was tried and why did it fail?
  6. Observer      — cost/result/stop-reason log + rollback snapshots

The loop only starts after the action has been validated manually ≥5 times, the
trigger and action are wired up, and the budget limit is set before any subjective
stop condition.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .action import Action, ActionResult, ActionStatus
from .memory import LoopMemory
from .observer import LoopObserver
from .stop import StopCondition
from .trigger import Trigger
from .verifier import Verifier


class LoopStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    EXHAUSTED = "exhausted"
    ERROR = "error"


@dataclass
class LoopResult:
    status: LoopStatus
    iterations_run: int
    total_cost: float
    stop_reason: str
    observation_summary: list[dict[str, Any]] = field(default_factory=list)


class LoopEngine:
    """Orchestrates one Loop Engineering loop.

    Usage::

        engine = LoopEngine(
            trigger=ManualTrigger(),
            action=MyAction(),
            stop_condition=CompositeStopCondition(
                BudgetStopCondition(max_cost=1.0),       # hard limit first
                TestPassStopCondition(run_tests),         # observable success second
                MaxIterationsStopCondition(50),           # safety net last
            ),
            verifier=TestSuiteVerifier(evaluate),
        )
        result = engine.run()
    """

    def __init__(
        self,
        trigger: Trigger,
        action: Action,
        stop_condition: StopCondition,
        verifier: Verifier | None = None,
        memory: LoopMemory | None = None,
        observer: LoopObserver | None = None,
        poll_interval_seconds: float = 0.0,
        context: dict[str, Any] | None = None,
    ):
        self.trigger = trigger
        self.action = action
        self.stop_condition = stop_condition
        self.verifier = verifier
        self.memory = memory or LoopMemory()
        self.observer = observer or LoopObserver()
        self._poll_interval = poll_interval_seconds
        self._base_context: dict[str, Any] = context or {}
        self._status = LoopStatus.IDLE

    @property
    def status(self) -> LoopStatus:
        return self._status

    def run(self, max_wall_seconds: float | None = None) -> LoopResult:
        """Run the loop until a stop condition triggers or the wall-clock limit expires."""
        self._status = LoopStatus.RUNNING
        start_wall = time.monotonic()
        stop_reason = "loop not started"

        while True:
            if max_wall_seconds and (time.monotonic() - start_wall) >= max_wall_seconds:
                stop_reason = f"wall clock limit {max_wall_seconds}s reached"
                self._status = LoopStatus.EXHAUSTED
                break

            ctx = self._build_context()

            if not self.trigger.should_fire(ctx):
                if self._poll_interval > 0:
                    time.sleep(self._poll_interval)
                continue

            ctx = self._build_context()
            if self.stop_condition.should_stop(ctx):
                stop_reason = self.stop_condition.reason
                self._status = LoopStatus.STOPPED
                break

            iteration = self.memory.start_iteration()
            action_result: ActionResult = self.action.execute(ctx)

            verification = None
            if self.verifier is not None and action_result.succeeded:
                verification = self.verifier.verify(action_result.output, ctx)
                if not verification.passed:
                    action_result = ActionResult(
                        status=ActionStatus.FAILURE,
                        output=action_result.output,
                        error=f"verifier rejected output: {verification.details}",
                        cost=action_result.cost,
                        duration_seconds=action_result.duration_seconds,
                    )

            ctx_after = self._build_context()
            iter_stop_reason: str | None = None
            if self.stop_condition.should_stop(ctx_after):
                iter_stop_reason = self.stop_condition.reason

            self.memory.complete_iteration(iteration, action_result, verification, iter_stop_reason)
            self.observer.record(iteration, iter_stop_reason)

            if iter_stop_reason:
                stop_reason = iter_stop_reason
                self._status = LoopStatus.STOPPED
                break

            if self._poll_interval > 0:
                time.sleep(self._poll_interval)

        return LoopResult(
            status=self._status,
            iterations_run=self.memory.iteration_count,
            total_cost=self.memory.total_cost,
            stop_reason=stop_reason,
            observation_summary=self.observer.summary(),
        )

    def _build_context(self) -> dict[str, Any]:
        ctx = dict(self._base_context)
        ctx.update(self.memory.to_context())
        return ctx
