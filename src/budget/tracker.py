"""Budget tracker — enforces cost limits across loop iterations.

Budget is the *first* hard boundary checked before any subjective stop condition.
This prevents runaway loops from incurring unbounded cost.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(Exception):
    """Raised when a loop iteration would exceed the configured budget."""

    def __init__(self, spent: float, limit: float):
        self.spent = spent
        self.limit = limit
        super().__init__(f"Budget exceeded: {spent:.4f} >= {limit:.4f}")


@dataclass
class BudgetSnapshot:
    spent: float
    limit: float
    remaining: float
    utilization: float


class BudgetTracker:
    """Tracks cumulative cost and enforces a hard spending limit."""

    def __init__(self, limit: float):
        if limit <= 0:
            raise ValueError("Budget limit must be positive")
        self._limit = limit
        self._spent: float = 0.0
        self._entries: list[tuple[int, float]] = []

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float:
        return max(0.0, self._limit - self._spent)

    @property
    def is_exhausted(self) -> bool:
        return self._spent >= self._limit

    def record(self, iteration_index: int, cost: float) -> None:
        """Record a cost charge. Raises BudgetExceeded if the limit is breached."""
        self._entries.append((iteration_index, cost))
        self._spent += cost
        if self._spent >= self._limit:
            raise BudgetExceeded(self._spent, self._limit)

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            spent=self._spent,
            limit=self._limit,
            remaining=self.remaining,
            utilization=self._spent / self._limit if self._limit > 0 else 0.0,
        )

    def to_context(self) -> dict:
        return {
            "total_cost": self._spent,
            "budget_limit": self._limit,
            "budget_remaining": self.remaining,
        }
