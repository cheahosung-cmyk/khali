"""Agent을 Loop Action으로 감싸는 어댑터."""

from __future__ import annotations

from typing import Any

from ..agent.base import Agent, AgentContext
from .action import Action, ActionResult, ActionStatus


class AgentAction(Action):
    """Agent 호출을 Loop Action으로 변환한다."""

    def __init__(self, agent: Agent, task: str, cost_key: str = "cost"):
        super().__init__(agent.name)
        self._agent = agent
        self._task = task
        self._cost_key = cost_key

    def _run(self, context: dict[str, Any]) -> ActionResult:
        agent_ctx = AgentContext(
            task=self._task,
            history=context.get("history", []),
            metadata=context,
        )
        response = self._agent.run(agent_ctx)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=response.content,
            cost=response.cost,
            metadata={"tokens": response.tokens_used},
        )
