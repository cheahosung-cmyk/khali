"""Base agent interface.

Agents are the *actors* inside loop actions. They must be kept separate from
verifiers — the same model cannot reliably evaluate its own output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    task: str
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_history_entry(self, role: str, content: str) -> "AgentContext":
        new_history = self.history + [{"role": role, "content": content}]
        return AgentContext(task=self.task, history=new_history, metadata=dict(self.metadata))


@dataclass
class AgentResponse:
    content: str
    cost: float = 0.0
    tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """Base class for all agents in the loop."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def run(self, context: AgentContext) -> AgentResponse:
        """Execute a single step and return the response."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
