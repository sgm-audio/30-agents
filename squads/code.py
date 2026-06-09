"""
CODE SQUAD — Software development lifecycle pipeline

Squad: @CodeSquad
Pipeline: code_writer → code_reviewer → [bug_hunter] → architect → tester

Leader: CodeSquadLeader
Members:
  - code_writer: Generates code from natural language descriptions
  - code_reviewer: Reviews code for quality, style, best practices
  - bug_hunter: Identifies bugs, security issues, edge cases
  - system_architect: Designs system architecture and patterns
  - test_engineer: Writes unit tests, integration tests

Routing Logic:
  code_writer → code_reviewer → bug_hunter → architect → test_engineer → END
  Loop: code_reviewer → code_writer (if major issues found, max 2 rewrites)
"""
from typing import Any

import structlog

from agents.tier3 import CodeWriterAgent, CodeReviewerAgent, BugHunterAgent, SystemArchitectAgent, TestEngineerAgent
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


CODE_MEMBERS = [
    SquadMember(
        name="code_writer",
        agent_class=CodeWriterAgent,
        description="Generates code from natural language descriptions",
        keywords=["write code", "implement", "code", "function", "class", "algorithm"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="code_reviewer",
        agent_class=CodeReviewerAgent,
        description="Reviews code for quality, style, and best practices",
        keywords=["review", "refactor", "style", "quality", "best practice"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="bug_hunter",
        agent_class=BugHunterAgent,
        description="Identifies bugs, security issues, and edge cases",
        keywords=["bug", "debug", "security", "edge case", "vulnerability", "fix"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="system_architect",
        agent_class=SystemArchitectAgent,
        description="Designs system architecture and patterns",
        keywords=["architect", "architecture", "design pattern", "system design", "structure"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="test_engineer",
        agent_class=TestEngineerAgent,
        description="Writes unit tests and integration tests",
        keywords=["test", "unit test", "integration test", "pytest", "testing"],
        model=settings.model_fast,
    ),
]


CODE_ROUTING = [
    RoutingRule(
        keywords=["write code", "implement", "code", "function", "class"],
        member_name="code_writer",
        priority=10,
    ),
    RoutingRule(
        keywords=["review", "refactor", "code review"],
        member_name="code_reviewer",
        priority=8,
    ),
    RoutingRule(
        keywords=["bug", "debug", "security", "vulnerability", "edge case"],
        member_name="bug_hunter",
        priority=7,
    ),
    RoutingRule(
        keywords=["architect", "architecture", "design pattern", "system design"],
        member_name="system_architect",
        priority=6,
    ),
    RoutingRule(
        keywords=["test", "unit test", "integration test", "pytest"],
        member_name="test_engineer",
        priority=5,
    ),
]


CODE_SQUAD = SquadConfig(
    name="code",
    display_name="Code",
    description="Software development lifecycle: write → review → bug hunt → architect → test",
    leader_class=None,
    members=CODE_MEMBERS,
    routing_rules=CODE_ROUTING,
    default_member="code_writer",
)


class CodeSquadLeader(SquadLeader):
    """Leader for the Code squad. Manages full software development lifecycle."""

    name = "code_squad"
    description = "Software development squad leader"
    model = settings.model_reason
    system_prompt = """You are the Code Squad Leader. You coordinate five specialists:

1. code_writer: Generates code from requirements
2. code_reviewer: Reviews code for quality and best practices
3. bug_hunter: Finds bugs and security issues
4. system_architect: Designs system architecture
5. test_engineer: Writes tests

Pipeline: code_writer → code_reviewer → [if issues → code_writer (max 2)] → bug_hunter → architect → test_engineer → END

Track rewrite iterations in context["rewrite_count"]."""

    WORKFLOW_ORDER = ["code_writer", "code_reviewer", "bug_hunter", "system_architect", "test_engineer"]
    MAX_REWRITE_COUNT = 2

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Always start with code_writer."""
        return "code_writer"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Complete after test_engineer runs."""
        return last_member == "test_engineer"

    def get_next_member(self, last_member: str, member_result: dict, context: dict) -> str | None:
        """Handle rewrite loop between code_reviewer and code_writer."""
        rewrite_count = context.get("rewrite_count", 0)

        if last_member == "code_reviewer":
            review_result = member_result.get("result", "").lower() if member_result else ""
            needs_rewrite = any(word in review_result for word in ["rewrite", "fix", "issue", "problem", "error", "bug", "wrong"])

            if needs_rewrite and rewrite_count < self.MAX_REWRITE_COUNT:
                return "code_writer"

            return "bug_hunter"

        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Build task for next member."""
        if last_member == "code_reviewer" and next_member == "code_writer":
            review = context.get("squad_result", {}).get("code_reviewer", "")
            rewrite_count = context.get("rewrite_count", 0) + 1
            context["rewrite_count"] = rewrite_count
            return f"Rewrite the code addressing these review issues (iteration {rewrite_count}): {review[:400]}"

        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile complete SDLC report."""
        lines = ["[CODE SQUAD Complete — Full SDLC Report]", ""]

        if "code_writer" in squad_result:
            lines.append("--- CODE WRITTEN ---")
            lines.append(squad_result["code_writer"][:500])
            lines.append("")

        if "code_reviewer" in squad_result:
            lines.append("--- CODE REVIEW ---")
            lines.append(squad_result["code_reviewer"][:400])
            lines.append("")

        if "bug_hunter" in squad_result:
            lines.append("--- BUG HUNT ---")
            lines.append(squad_result["bug_hunter"][:400])
            lines.append("")

        if "system_architect" in squad_result:
            lines.append("--- ARCHITECTURE ---")
            lines.append(squad_result["system_architect"][:400])
            lines.append("")

        if "test_engineer" in squad_result:
            lines.append("--- TESTS ---")
            lines.append(squad_result["test_engineer"][:400])
            lines.append("")

        return "\n".join(lines)


CODE_SQUAD.leader_class = CodeSquadLeader