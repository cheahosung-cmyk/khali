"""Stop conditions for Loop Engineering — decides *when* the loop halts.

Key insight from the research: "stop when satisfied" is a trap.
Stop conditions must be *observable*: tests pass, budget within limit, etc.
Self-correction without external feedback worsens performance (arxiv 2310.01798).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StopCondition(ABC):
    """Base class for loop stop conditions."""

    @abstractmethod
    def should_stop(self, context: dict[str, Any]) -> bool:
        """Return True when the loop should halt."""

    @property
    @abstractmethod
    def reason(self) -> str:
        """Human-readable explanation of why this condition would stop the loop."""


class PassesStopCondition(StopCondition):
    """Stops when a test suite passes — the gold-standard observable stop condition."""

    def __init__(self, test_fn, regression_fn=None):
        self._test_fn = test_fn
        self._regression_fn = regression_fn
        self._last_reason = "tests not yet run"

    def should_stop(self, context: dict[str, Any]) -> bool:
        if not self._test_fn(context):
            self._last_reason = "designated tests not 100% passing"
            return False
        if self._regression_fn and not self._regression_fn(context):
            self._last_reason = "regression tests failing"
            return False
        self._last_reason = "all tests passing"
        return True

    @property
    def reason(self) -> str:
        return self._last_reason


# Alias for backward compatibility
TestPassStopCondition = PassesStopCondition


class BudgetStopCondition(StopCondition):
    """Stops when the accumulated cost exceeds the budget limit.

    Budget must be checked *before* subjective satisfaction — it is the hard
    outer boundary of any loop.
    """

    def __init__(self, max_cost: float):
        self._max_cost = max_cost
        self._last_reason = "within budget"

    def should_stop(self, context: dict[str, Any]) -> bool:
        spent = float(context.get("total_cost", 0.0))
        if spent >= self._max_cost:
            self._last_reason = f"budget exhausted: {spent:.4f} >= {self._max_cost:.4f}"
            return True
        self._last_reason = f"within budget: {spent:.4f} / {self._max_cost:.4f}"
        return False

    @property
    def reason(self) -> str:
        return self._last_reason


class MaxIterationsStopCondition(StopCondition):
    """Safety net: stop after N iterations regardless of other conditions."""

    def __init__(self, max_iterations: int):
        self._max = max_iterations
        self._last_reason = "iteration limit not reached"

    def should_stop(self, context: dict[str, Any]) -> bool:
        iteration = int(context.get("iteration", 0))
        if iteration >= self._max:
            self._last_reason = f"max iterations reached: {iteration}"
            return True
        self._last_reason = f"iteration {iteration} / {self._max}"
        return False

    @property
    def reason(self) -> str:
        return self._last_reason


class CompositeStopCondition(StopCondition):
    """Combines multiple stop conditions: stops when *any* condition triggers.

    Priority matters: budget and iteration limits are checked first so they
    act as hard outer boundaries before observable success conditions.
    """

    def __init__(self, *conditions: StopCondition):
        self._conditions = list(conditions)
        self._triggered: StopCondition | None = None

    def should_stop(self, context: dict[str, Any]) -> bool:
        for cond in self._conditions:
            if cond.should_stop(context):
                self._triggered = cond
                return True
        self._triggered = None
        return False

    @property
    def reason(self) -> str:
        if self._triggered:
            return f"{type(self._triggered).__name__}: {self._triggered.reason}"
        return "; ".join(c.reason for c in self._conditions)
