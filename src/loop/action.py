"""Action component for Loop Engineering."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class ActionResult:
    status: ActionStatus
    output: Any = None
    error: str | None = None
    cost: float = 0.0
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == ActionStatus.SUCCESS


class Action(ABC):
    """Base class for loop actions."""

    def __init__(self, name: str):
        self.name = name

    def execute(self, context: dict[str, Any] | None = None) -> ActionResult:
        start = time.monotonic()
        try:
            result = self._run(context or {})
            result.duration_seconds = time.monotonic() - start
            return result
        except Exception as exc:
            return ActionResult(
                status=ActionStatus.FAILURE,
                error=str(exc),
                duration_seconds=time.monotonic() - start,
            )

    @abstractmethod
    def _run(self, context: dict[str, Any]) -> ActionResult:
        """Implement the actual action logic here."""


class FunctionAction(Action):
    """Wraps a plain callable as a loop action."""

    def __init__(self, name: str, fn, cost_per_run: float = 0.0):
        super().__init__(name)
        self._fn = fn
        self._cost_per_run = cost_per_run

    def _run(self, context: dict[str, Any]) -> ActionResult:
        output = self._fn(context)
        if isinstance(output, ActionResult):
            return output
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=output,
            cost=self._cost_per_run,
        )
