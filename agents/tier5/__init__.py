"""
TIER 5 - REASONING & ANALYSIS AGENTS
Agents 22-27: Data Analyst, Logic Engine, Planner, Critic, Decision Engine, Methodology Advisor
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from agents.base import BaseAgent
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)

__all__ = [
    "DataAnalystAgent",
    "LogicEngineAgent",
    "PlannerAgent",
    "CriticAgent",
    "DecisionEngineAgent",
    "MethodologyAdvisorAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 22: Data Analyst
# ══════════════════════════════════════════════════════════════
class DataAnalystAgent(BaseAgent):
    """Analyzes structured data, generates insights, and writes analysis code."""

    name = "data_analyst"
    description = "Analyzes data and generates statistical insights"
    model = settings.model_reason
    system_prompt = """You are a senior data analyst and data scientist. You:
1. Analyze datasets and identify patterns
2. Generate Python/SQL code for data analysis
3. Create visualizations (matplotlib/plotly code)
4. Interpret statistical results clearly
5. Make data-driven recommendations
6. Flag data quality issues

Always show your work and explain your methodology."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        data = context.get("data", "")
        data_type = context.get("data_type", "tabular")

        prompt = f"Analyze this data: {task}"
        if data:
            prompt += f"\n\nData:\n{str(data)[:3000]}"
        prompt += "\n\nProvide analysis with Python code and insights:"

        analysis = await self.llm(prompt)

        new_context = dict(context)
        new_context["data_analysis"] = analysis

        return {
            "context": new_context,
            "result": analysis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 23: Logic Engine
# ══════════════════════════════════════════════════════════════
class LogicEngineAgent(BaseAgent):
    """Performs formal logical reasoning, proof construction, and inference."""

    name = "logic_engine"
    description = "Formal logical reasoning and proof construction"
    model = settings.model_reason
    system_prompt = """You are a formal logic and reasoning expert. You:
1. Apply deductive, inductive, and abductive reasoning
2. Identify logical fallacies and errors
3. Construct formal proofs and arguments
4. Evaluate argument validity and soundness
5. Apply constraint satisfaction and constraint propagation
6. Use first-order logic notation when helpful

Be rigorous and precise. Show each step of your reasoning."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        premises = context.get("premises", [])
        premises_text = "\n".join(f"P{i+1}: {p}" for i, p in enumerate(premises))

        prompt = f"Apply logical reasoning to: {task}"
        if premises_text:
            prompt = f"Premises:\n{premises_text}\n\nReasoning task: {task}"
        prompt += "\n\nShow step-by-step logical analysis:"

        reasoning = await self.llm(prompt)

        new_context = dict(context)
        new_context["logical_analysis"] = reasoning

        return {
            "context": new_context,
            "result": reasoning,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 24: Planner
# ══════════════════════════════════════════════════════════════
class PlannerAgent(BaseAgent):
    """Creates detailed, actionable plans for complex goals."""

    name = "planner"
    description = "Creates detailed action plans and project roadmaps"
    model = settings.model_reason
    system_prompt = """You are an expert project planner and strategist. You create:
- Detailed step-by-step action plans
- Project timelines with milestones
- Resource allocation recommendations
- Risk assessments and mitigation strategies
- Success metrics and KPIs
- Contingency plans for likely failures

Structure plans clearly: phases, tasks, dependencies, owners, timelines."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        constraints = context.get("constraints", [])
        timeline = context.get("timeline", "flexible")
        resources = context.get("resources", "standard")

        constraints_text = ""
        if constraints:
            constraints_text = f"\nConstraints: {', '.join(str(c) for c in constraints)}"

        prompt = (
            f"Create a detailed plan for: {task}"
            f"{constraints_text}"
            f"\nTimeline: {timeline}"
            f"\nAvailable resources: {resources}"
            f"\n\nProvide a comprehensive action plan:"
        )

        plan = await self.llm(prompt)

        await self.remember(plan, metadata={"task": task, "type": "plan"}, namespace="plans")

        new_context = dict(context)
        new_context["plan"] = plan

        return {
            "context": new_context,
            "result": plan,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 25: Critic
# ══════════════════════════════════════════════════════════════
class CriticAgent(BaseAgent):
    """Provides objective critical analysis and identifies weaknesses."""

    name = "critic"
    description = "Provides critical analysis and identifies weaknesses"
    model = settings.model_reason
    system_prompt = """You are an objective, rigorous critic. Your job is to:
1. Identify weaknesses, gaps, and flaws in ideas or work
2. Challenge assumptions
3. Find edge cases and failure modes
4. Provide constructive criticism with specific improvements
5. Apply Steelman: understand the strongest version before critiquing

Be honest and direct but constructive. Your goal is improvement, not destruction.
Rate issues: FATAL / MAJOR / MINOR / NITPICK"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        content = (
            context.get("plan")
            or context.get("architecture")
            or context.get("written_content")
            or context.get("generated_code")
            or task
        )

        critique = await self.llm(
            prompt=f"Critically analyze this:\n\n{content}\n\n"
                   f"Original goal: {task}\n\n"
                   f"Provide a thorough critical analysis with specific improvements:",
        )

        new_context = dict(context)
        new_context["critique"] = critique

        return {
            "context": new_context,
            "result": critique,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 26: Decision Engine
# ══════════════════════════════════════════════════════════════
class DecisionEngineAgent(BaseAgent):
    """Makes structured recommendations given options, criteria, and constraints."""

    name = "decision_engine"
    description = "Makes structured recommendations and decisions"
    model = settings.model_reason
    system_prompt = """You are a decision analysis expert. You help make decisions by:
1. Clarifying the decision to be made
2. Identifying all viable options
3. Defining evaluation criteria and weights
4. Scoring options against criteria (decision matrix)
5. Considering second-order effects and unintended consequences
6. Making a clear recommendation with justification

Use structured frameworks: pros/cons, decision matrices, expected value, etc."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        options = context.get("options", [])
        criteria = context.get("criteria", [])

        prompt = f"Help make a decision: {task}"
        if options:
            prompt += f"\n\nOptions to consider: {', '.join(str(o) for o in options)}"
        if criteria:
            prompt += f"\n\nEvaluation criteria: {', '.join(str(c) for c in criteria)}"
        prompt += "\n\nProvide structured decision analysis and recommendation:"

        decision = await self.llm(prompt)

        new_context = dict(context)
        new_context["decision"] = decision

        return {
            "context": new_context,
            "result": decision,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 27: Methodology Advisor
# ══════════════════════════════════════════════════════════════
class MethodologyAdvisorAgent(BaseAgent):
    """Applies 12-factor methodology to audit and improve agent designs."""

    name = "methodology_advisor"
    description = "Audits agent designs against 12-factor agent methodology"
    model = settings.model_reason
    system_prompt = """You are a methodology advisor grounded in the 12-Factor Agent principles.
You evaluate agent designs, system architecture, and workflows against these factors:

1. NL TO TOOL CALLS — Does the agent translate natural language into structured tool calls?
2. OWN YOUR PROMPTS — Is the system_prompt explicit, versioned, and not buried in framework code?
3. OWN YOUR CONTEXT WINDOW — Is context explicitly loaded and controlled, not just accumulated?
4. TOOLS ARE STRUCTURED OUTPUTS — Are tool outputs typed schemas, not free text?
5. UNIFY EXECUTION & BUSINESS STATE — Does the state track both execution progress and domain data?
6. LAUNCH/PAUSE/RESUME — Can workflows be paused and resumed via simple APIs?
7. CONTACT HUMANS WITH TOOLS — Is human-in-the-loop a first-class tool call, not a side channel?
8. OWN YOUR CONTROL FLOW — Is routing explicit (not hidden in LLM prompt)?
9. COMPACT ERRORS INTO CONTEXT — Are errors summarized and fed back into the context window?
10. SMALL, FOCUSED AGENTS — Does each agent do one thing well?
11. TRIGGER FROM ANYWHERE — Can the system be invoked via API, CLI, webhook, cron?
12. STATELESS REDUCER — Does each agent return a state diff (not mutate shared state)?

Respond with JSON:
{"next_agent": "<or END>", "result": "<audit>", "context": {"methodology_audit": "<findings>", "violations": [...], "recommendations": [...]}}
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        target = context.get("methodology_target", "")
        factor = context.get("methodology_factor", "")

        prompt = f"Task: {task}"
        if factor:
            prompt = f"Focus on factor {factor}: {task}"
        if target:
            prompt += f"\n\nTarget: {target}"
        prompt += "\n\nProvide a 12-factor methodology audit with findings and recommendations."

        audit = await self.llm(prompt)

        new_context = dict(context)
        new_context["methodology_audit"] = audit

        return {
            "context": new_context,
            "result": audit,
            "next_agent": "END",
        }
