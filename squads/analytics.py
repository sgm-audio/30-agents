"""
ANALYTICS SQUAD — Data analysis and decision-making pipeline

Squad: @AnalyticsSquad
Pipeline: data_analyst → planner → critic → decision_engine

Leader: AnalyticsSquadLeader
Members:
  - data_analyst: Analyzes data, identifies patterns, generates insights
  - planner: Creates execution plans based on analysis
  - critic: Reviews plans for flaws, risks, edge cases
  - decision_engine: Makes final recommendations and decisions

Routing Logic:
  data_analyst → planner → critic → decision_engine → END
  Loop back to planner if critic finds significant issues (max 2 iterations)
"""
from typing import Any

import structlog

from agents.tier5 import DataAnalystAgent, LogicEngineAgent, PlannerAgent, CriticAgent, DecisionEngineAgent
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


ANALYTICS_MEMBERS = [
    SquadMember(
        name="data_analyst",
        agent_class=DataAnalystAgent,
        description="Analyzes data and generates statistical insights",
        keywords=["analyze", "data", "insight", "pattern", "trend", "statistics", "visualization"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="planner",
        agent_class=PlannerAgent,
        description="Creates detailed execution plans",
        keywords=["plan", "strategy", "roadmap", "execute", "步骤", "方案"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="critic",
        agent_class=CriticAgent,
        description="Reviews plans for flaws, risks, and edge cases",
        keywords=["review", "critique", "risk", "flaw", "issue", "problem", "weakness"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="decision_engine",
        agent_class=DecisionEngineAgent,
        description="Makes final recommendations and decisions",
        keywords=["decide", "recommend", "choice", "option", "decision", " verdict"],
        model=settings.model_reason,
    ),
]


ANALYTICS_ROUTING = [
    RoutingRule(
        keywords=["analyze", "data", "insight", "statistics", "pattern", "trend"],
        member_name="data_analyst",
        priority=10,
    ),
    RoutingRule(
        keywords=["plan", "strategy", "roadmap", "步骤", "方案"],
        member_name="planner",
        priority=8,
    ),
    RoutingRule(
        keywords=["critique", "review", "risk", "flaw", "weakness", "issue"],
        member_name="critic",
        priority=6,
    ),
    RoutingRule(
        keywords=["decide", "recommend", "choice", "decision", "verdict"],
        member_name="decision_engine",
        priority=5,
    ),
]


ANALYTICS_SQUAD = SquadConfig(
    name="analytics",
    display_name="Analytics",
    description="Data analysis and decision-making: analyze → plan → critique → decide",
    leader_class=None,
    members=ANALYTICS_MEMBERS,
    routing_rules=ANALYTICS_ROUTING,
    default_member="data_analyst",
)


class AnalyticsSquadLeader(SquadLeader):
    """
    Leader for the Analytics squad. Manages analysis → planning → critique → decision workflow.

    Workflow:
    1. data_analyst runs first to understand the data/task
    2. planner creates an execution plan based on findings
    3. critic reviews the plan for issues
    4. If critic finds problems (iteration < 2), route back to planner
    5. Once critique passes, decision_engine makes final recommendation
    """

    name = "analytics_squad"
    description = "Analytics and decision-making squad leader"
    model = settings.model_reason
    system_prompt = """You are the Analytics Squad Leader. You coordinate four specialists:

1. data_analyst: Analyzes datasets and identifies patterns
2. planner: Creates execution plans based on analysis
3. critic: Reviews plans for flaws, risks, edge cases
4. decision_engine: Makes final recommendations

Pipeline: data_analyst → planner → critic → [if issues found → planner] → decision_engine → END

You track iteration count via context["plan_iteration"] to limit review loops to 2."""

    WORKFLOW_ORDER = ["data_analyst", "planner", "critic", "decision_engine"]
    MAX_PLAN_ITERATIONS = 2

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Always start with data_analyst."""
        return "data_analyst"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Complete after decision_engine runs."""
        return last_member == "decision_engine"

    def get_next_member(self, last_member: str, member_result: dict, context: dict) -> str | None:
        """Route based on workflow with critique loop."""
        iteration = context.get("plan_iteration", 0)

        if last_member == "critic":
            critique_result = member_result.get("result", "").lower() if member_result else ""
            has_issues = any(word in critique_result for word in ["issue", "problem", "risk", "flaw", "weakness", "concern"])

            if has_issues and iteration < self.MAX_PLAN_ITERATIONS:
                return "planner"
            return "decision_engine"

        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Update iteration counter and pass appropriate task."""
        if last_member == "critic" and next_member == "planner":
            new_context = dict(context)
            new_context["plan_iteration"] = context.get("plan_iteration", 0) + 1
            critique = context.get("squad_result", {}).get("critic", "")
            return f"Revise your plan based on this critique: {critique[:500]}"

        if last_member == "data_analyst" and next_member == "planner":
            analysis = context.get("squad_result", {}).get("data_analyst", "")
            return f"Create an execution plan based on this analysis: {analysis[:500]}"

        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile analytics findings and final decision."""
        lines = ["[ANALYTICS SQUAD Complete]", ""]

        if "data_analyst" in squad_result:
            lines.append("--- DATA ANALYSIS ---")
            lines.append(squad_result["data_analyst"][:400])
            lines.append("")

        if "planner" in squad_result:
            lines.append("--- EXECUTION PLAN ---")
            lines.append(squad_result["planner"][:400])
            lines.append("")

        if "critic" in squad_result:
            lines.append("--- CRITIQUE ---")
            lines.append(squad_result["critic"][:400])
            lines.append("")

        if "decision_engine" in squad_result:
            lines.append("--- FINAL DECISION ---")
            lines.append(squad_result["decision_engine"][:600])
            lines.append("")

        return "\n".join(lines)


ANALYTICS_SQUAD.leader_class = AnalyticsSquadLeader