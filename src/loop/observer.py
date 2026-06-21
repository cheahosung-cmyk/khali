"""Observer and rollback for Loop Engineering.

Logs cost, result, and stop reason for every iteration.
Supports rollback by storing snapshots keyed by iteration index.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .memory import LoopIteration


@dataclass
class IterationLog:
    iteration_index: int
    cost: float
    duration_seconds: float
    succeeded: bool
    stop_reason: str | None
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration_index": self.iteration_index,
            "cost": self.cost,
            "duration_seconds": self.duration_seconds,
            "succeeded": self.succeeded,
            "stop_reason": self.stop_reason,
        }


class LoopObserver:
    """Records every iteration and keeps snapshots for potential rollback."""

    def __init__(self, snapshot_fn=None):
        self._logs: list[IterationLog] = []
        self._snapshots: dict[int, dict[str, Any]] = {}
        self._snapshot_fn = snapshot_fn

    def record(self, iteration: LoopIteration, stop_reason: str | None = None) -> None:
        duration = 0.0
        if iteration.finished_at and iteration.started_at:
            duration = (iteration.finished_at - iteration.started_at).total_seconds()

        snapshot: dict[str, Any] = {}
        if self._snapshot_fn:
            snapshot = self._snapshot_fn(iteration.index) or {}
        self._snapshots[iteration.index] = snapshot

        log = IterationLog(
            iteration_index=iteration.index,
            cost=iteration.cost,
            duration_seconds=duration,
            succeeded=iteration.succeeded,
            stop_reason=stop_reason,
            snapshot=snapshot,
        )
        self._logs.append(log)

    def rollback_to(self, iteration_index: int) -> dict[str, Any] | None:
        """Return the snapshot taken at the given iteration for manual rollback."""
        return self._snapshots.get(iteration_index)

    def last_successful_snapshot(self) -> dict[str, Any] | None:
        for log in reversed(self._logs):
            if log.succeeded and log.snapshot:
                return log.snapshot
        return None

    def summary(self) -> list[dict[str, Any]]:
        return [log.to_dict() for log in self._logs]

    def total_cost(self) -> float:
        return sum(log.cost for log in self._logs)

    def print_summary(self) -> None:
        print(f"\n{'='*50}")
        print(f"Loop Observation Summary — {len(self._logs)} iterations")
        print(f"Total cost: {self.total_cost():.4f}")
        print(f"{'='*50}")
        for log in self._logs:
            status = "OK" if log.succeeded else "FAIL"
            print(
                f"  [{status}] iter={log.iteration_index} "
                f"cost={log.cost:.4f} dur={log.duration_seconds:.2f}s "
                f"stop={log.stop_reason or '-'}"
            )
        print(f"{'='*50}\n")
