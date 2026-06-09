"""
Base classes for Squad architecture.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from agents.base import BaseAgent, extract_json
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)


@dataclass
class SquadMember:
    """A specialist agent that belongs to a squad."""
    name: str
    agent_class: type[BaseAgent]
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class RoutingRule:
    """A routing rule that maps task patterns to a member."""
    keywords: list[str]
    member_name: str
    priority: int = 0


@dataclass
class SquadConfig:
    """Configuration for a squad."""
    name: str
    display_name: str
    description: str
    leader_class: type[SquadLeader]
    members: list[SquadMember]
    routing_rules: list[RoutingRule]
    default_member: str = ""


class SquadLeader(BaseAgent):
    """
    Base class for squad leaders. A leader receives tasks, routes to the
    appropriate squad member, collects results, and manages the squad workflow.

    Key differences from regular agents:
    - `next_agent` routes to SQUAD MEMBERS (not orchestrator)
    - Tracks `context["squad_stage"]` to know workflow progress
    - `context["squad_result"]` accumulates across member executions
    - Returns `next_agent: "END"` only when squad work is complete
    """

    name: str = "squad_leader"
    description: str = "Squad leader base class"
    model = settings.model_fast

    def __init__(self, config: SquadConfig):
        super().__init__()
        self.config = config
        self._members: dict[str, BaseAgent] = {}
        self._routing_rules: list[RoutingRule] = []
        for m in config.members:
            self._members[m.name] = m.agent_class()
        for r in config.routing_rules:
            self._routing_rules.append(r)
        self._routing_rules.sort(key=lambda x: -x.priority)

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """
        Analyze task and context, return which member should handle it.
        Override in subclass for custom routing logic.
        """
        task_lower = task.lower()
        context_lower = json.dumps(context).lower()

        for rule in self._routing_rules:
            if any(kw in task_lower or kw in context_lower for kw in rule.keywords):
                log.info("squad.route", member=rule.member_name, task=task[:60])
                return rule.member_name

        return self.config.default_member

    async def execute(self, state: AgentState) -> dict[str, Any]:
        """
        Main leader execution. Routes to appropriate squad member or
        handles member results and determines next steps.
        """
        task = state["task"]
        context = state.get("context", {})
        squad_stage = context.get("squad_stage", "start")
        previous_result = context.get("squad_result", {})

        log.info("squad.leader_execute", squad=self.config.name, stage=squad_stage, task=task[:60])

        if squad_stage == "start":
            member_name = self.route_task(task, context)
            if not member_name:
                return self.error_result(f"No suitable member found for task: {task[:60]}")

            new_context = dict(context)
            new_context["squad_stage"] = "delegating"
            new_context["squad_member"] = member_name
            new_context["squad_task"] = task
            new_context["squad_result"] = {}

            return {
                "task": task,
                "context": new_context,
                "next_agent": member_name,
            }

        elif squad_stage == "delegating":
            member_name = context.get("squad_member", "")
            if not member_name or member_name not in self._members:
                return self.error_result(f"Unknown squad member: {member_name}")

            member = self._members[member_name]
            member_result = await member(state)

            squad_result = dict(previous_result)
            squad_result[member_name] = member_result.get("result", "")
            if "context" in member_result:
                squad_result[f"{member_name}_context"] = member_result["context"]

            new_context = dict(context)
            new_context["squad_result"] = squad_result
            new_context["squad_member_result"] = member_result

            is_complete = self.is_squad_complete(member_name, member_result, new_context)
            if is_complete:
                final_result = self.compile_squad_result(member_name, squad_result, new_context)
                return {
                    "context": new_context,
                    "result": final_result,
                    "next_agent": "END",
                }
            else:
                next_member = self.get_next_member(member_name, member_result, new_context)
                if next_member:
                    new_context["squad_stage"] = "delegating"
                    new_context["squad_member"] = next_member
                    new_context["squad_task"] = self.get_next_task(member_name, next_member, new_context)
                    return {
                        "context": new_context,
                        "next_agent": next_member,
                    }
                else:
                    final_result = self.compile_squad_result(member_name, squad_result, new_context)
                    return {
                        "context": new_context,
                        "result": final_result,
                        "next_agent": "END",
                    }

        return self.error_result("Invalid squad stage")

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Override in subclass to determine when squad work is done."""
        return False

    def get_next_member(self, last_member: str, member_result: dict, context: dict) -> str | None:
        """Override in subclass to define sequential squad workflow.
        member_result is the return from the last member that ran."""
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Get the task to send to the next member."""
        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Override to compile a nice final result from all member outputs."""
        lines = [f"[{self.config.display_name} Squad Results]\n"]
        for member_name, result in squad_result.items():
            if isinstance(result, str) and not member_name.endswith("_context"):
                lines.append(f"\n--- {member_name.upper()} ---\n{result[:500]}")
        return "\n".join(lines)