"""Trigger component for Loop Engineering — decides *when* the loop fires."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class Trigger(ABC):
    """Base class for loop triggers."""

    @abstractmethod
    def should_fire(self, context: dict[str, Any]) -> bool:
        """Return True when this trigger wants the loop to start an iteration."""


class ManualTrigger(Trigger):
    """Fires once per arm() call — arming N times causes N fires."""

    def __init__(self):
        self._fire_count = 0

    def arm(self) -> None:
        self._fire_count += 1

    def should_fire(self, context: dict[str, Any]) -> bool:
        if self._fire_count > 0:
            self._fire_count -= 1
            return True
        return False


class ScheduleTrigger(Trigger):
    """Fires on a fixed interval (in seconds)."""

    def __init__(self, interval_seconds: float):
        self._interval = interval_seconds
        self._last_fire: float = 0.0

    def should_fire(self, context: dict[str, Any]) -> bool:
        now = time.monotonic()
        if now - self._last_fire >= self._interval:
            self._last_fire = now
            return True
        return False


class EventTrigger(Trigger):
    """Fires when a named event is present in the context."""

    def __init__(self, event_key: str):
        self._key = event_key

    def should_fire(self, context: dict[str, Any]) -> bool:
        return bool(context.get(self._key))


class AlwaysTrigger(Trigger):
    """Fires on every poll — useful for tight loops controlled only by stop condition."""

    def should_fire(self, context: dict[str, Any]) -> bool:
        return True
