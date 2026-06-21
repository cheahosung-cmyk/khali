"""LoopBuilder — 루프를 간결하게 조립하는 빌더."""

from __future__ import annotations

from typing import Any, Callable

from ..budget.tracker import BudgetTracker
from .action import Action, FunctionAction
from .agent_action import AgentAction
from .engine import LoopEngine
from .memory import LoopMemory
from .observer import LoopObserver
from .stop import (
    BudgetStopCondition,
    CompositeStopCondition,
    MaxIterationsStopCondition,
    PassesStopCondition,
    StopCondition,
)
from .trigger import AlwaysTrigger, EventTrigger, ManualTrigger, ScheduleTrigger, Trigger
from .verifier import SuiteVerifier, Verifier


class LoopBuilder:
    """루프 엔지니어링 6요소를 플루언트 API로 조립한다.

    순서 원칙:
      1. 예산 한도 (budget) — 가장 먼저 설정
      2. 트리거 (trigger)
      3. 액션 (action)
      4. 검증자 (verifier) — 액터와 분리
      5. 정지조건 (stop) — 관측 가능해야 함
      6. 안전망 반복 한도 (max_iterations)
    """

    def __init__(self):
        self._trigger: Trigger | None = None
        self._action: Action | None = None
        self._stop_conditions: list[StopCondition] = []
        self._verifier: Verifier | None = None
        self._budget: BudgetTracker | None = None
        self._max_iterations: int = 100
        self._poll: float = 0.0
        self._context: dict[str, Any] = {}

    # ── 예산 ──────────────────────────────────────────────
    def budget(self, max_cost: float) -> "LoopBuilder":
        self._budget = BudgetTracker(limit=max_cost)
        self._stop_conditions.insert(0, BudgetStopCondition(max_cost=max_cost))
        return self

    # ── 트리거 ────────────────────────────────────────────
    def trigger_always(self) -> "LoopBuilder":
        self._trigger = AlwaysTrigger()
        return self

    def trigger_manual(self) -> "LoopBuilder":
        self._trigger = ManualTrigger()
        return self

    def trigger_schedule(self, interval_seconds: float) -> "LoopBuilder":
        self._trigger = ScheduleTrigger(interval_seconds)
        return self

    def trigger_event(self, key: str) -> "LoopBuilder":
        self._trigger = EventTrigger(key)
        return self

    def trigger(self, t: Trigger) -> "LoopBuilder":
        self._trigger = t
        return self

    # ── 액션 ──────────────────────────────────────────────
    def action_fn(self, fn: Callable, name: str = "action", cost_per_run: float = 0.0) -> "LoopBuilder":
        self._action = FunctionAction(name, fn, cost_per_run)
        return self

    def action_agent(self, agent, task: str) -> "LoopBuilder":
        self._action = AgentAction(agent, task)
        return self

    def action(self, a: Action) -> "LoopBuilder":
        self._action = a
        return self

    # ── 정지조건 ──────────────────────────────────────────
    def stop_when_tests_pass(self, test_fn: Callable, regression_fn: Callable | None = None) -> "LoopBuilder":
        self._stop_conditions.append(PassesStopCondition(test_fn, regression_fn))
        return self

    def stop_after(self, iterations: int) -> "LoopBuilder":
        self._max_iterations = iterations
        return self

    def stop(self, condition: StopCondition) -> "LoopBuilder":
        self._stop_conditions.append(condition)
        return self

    # ── 검증자 ────────────────────────────────────────────
    def verify_with(self, test_fn: Callable, threshold: float = 1.0) -> "LoopBuilder":
        self._verifier = SuiteVerifier(test_fn, threshold)
        return self

    def verifier(self, v: Verifier) -> "LoopBuilder":
        self._verifier = v
        return self

    # ── 기타 ──────────────────────────────────────────────
    def poll(self, seconds: float) -> "LoopBuilder":
        self._poll = seconds
        return self

    def context(self, **kwargs: Any) -> "LoopBuilder":
        self._context.update(kwargs)
        return self

    # ── 빌드 ──────────────────────────────────────────────
    def build(self) -> LoopEngine:
        if self._trigger is None:
            raise ValueError("trigger가 설정되지 않았습니다")
        if self._action is None:
            raise ValueError("action이 설정되지 않았습니다")

        all_stops: list[StopCondition] = list(self._stop_conditions)
        all_stops.append(MaxIterationsStopCondition(self._max_iterations))
        stop = CompositeStopCondition(*all_stops)

        return LoopEngine(
            trigger=self._trigger,
            action=self._action,
            stop_condition=stop,
            verifier=self._verifier,
            memory=LoopMemory(),
            observer=LoopObserver(),
            budget=self._budget,
            poll_interval_seconds=self._poll,
            context=self._context,
        )
