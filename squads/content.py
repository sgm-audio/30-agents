"""
CONTENT SQUAD — Content creation and refinement pipeline

Squad: @ContentSquad
Pipeline: writer → editor → [summarizer | translator] → content_strategist

Leader: ContentSquadLeader
Members:
  - writer: Generates long-form written content (essays, reports, articles)
  - editor: Revises and polishes content for clarity, tone, structure
  - summarizer: Creates concise summaries of longer content
  - translator: Translates content between languages
  - content_strategist: Evaluates content for SEO, engagement, brand alignment

Routing Logic:
  writer → editor → [summarizer if summary requested | translator if translation requested] → content_strategist
"""
from typing import Any

import structlog

from agents.tier4 import WriterAgent, SummarizerAgent, TranslatorAgent, EditorAgent, ContentStrategistAgent
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


CONTENT_MEMBERS = [
    SquadMember(
        name="writer",
        agent_class=WriterAgent,
        description="Generates long-form written content",
        keywords=["write", "create content", "essay", "article", "report", "draft"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="editor",
        agent_class=EditorAgent,
        description="Revises and polishes content",
        keywords=["edit", "revise", "polish", "rewrite", "improve", "fix"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="summarizer",
        agent_class=SummarizerAgent,
        description="Creates concise summaries of content",
        keywords=["summarize", "summary", "brief", "condense", "shorten", "tl;dr"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="translator",
        agent_class=TranslatorAgent,
        description="Translates content between languages",
        keywords=["translate", "translation", "french", "spanish", "chinese", "language"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="content_strategist",
        agent_class=ContentStrategistAgent,
        description="Evaluates content for SEO, engagement, and strategy",
        keywords=["strategy", "SEO", "engagement", "audience", "content strategy"],
        model=settings.model_reason,
    ),
]


CONTENT_ROUTING = [
    RoutingRule(
        keywords=["translate", "translation", "french", "spanish", "language"],
        member_name="translator",
        priority=8,
    ),
    RoutingRule(
        keywords=["summarize", "summary", "brief", "condense", "tl;dr"],
        member_name="summarizer",
        priority=7,
    ),
    RoutingRule(
        keywords=["write", "create", "draft", "generate content"],
        member_name="writer",
        priority=9,
    ),
    RoutingRule(
        keywords=["edit", "revise", "polish", "improve", "rewrite"],
        member_name="editor",
        priority=6,
    ),
    RoutingRule(
        keywords=["strategy", "SEO", "engagement", "audience"],
        member_name="content_strategist",
        priority=5,
    ),
]


CONTENT_SQUAD = SquadConfig(
    name="content",
    display_name="Content",
    description="Content creation and refinement: write → edit → [summarize|translate] → strategize",
    leader_class=None,
    members=CONTENT_MEMBERS,
    routing_rules=CONTENT_ROUTING,
    default_member="writer",
)


class ContentSquadLeader(SquadLeader):
    """
    Leader for the Content squad. Manages the content creation pipeline.

    Workflow:
    1. writer creates initial draft (always first)
    2. editor revises and polishes
    3. summarizer or translator if requested (conditional)
    4. content_strategist evaluates final content

    The squad detects translation/summary requests and routes accordingly.
    """

    name = "content_squad"
    description = "Content creation and refinement squad leader"
    model = settings.model_reason
    system_prompt = """You are the Content Squad Leader. You coordinate five specialists:

1. writer: Creates long-form content (essays, articles, reports)
2. editor: Revises and polishes content
3. summarizer: Creates concise summaries
4. translator: Translates between languages
5. content_strategist: Evaluates content for SEO and engagement

Pipeline: writer → editor → [summarizer|translator] → content_strategist → END

Detect translation/summary requests from the task to conditionally route."""

    WORKFLOW_ORDER = ["writer", "editor", "content_strategist"]
    CONDITIONAL_MEMBERS = {"summarizer", "translator"}

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Start with writer for content creation."""
        return "writer"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Complete after content_strategist runs."""
        return last_member == "content_strategist"

    def get_next_member(self, last_member: str, context: dict) -> str | None:
        """Determine next member based on workflow and conditional routing."""
        task_lower = context.get("squad_task", "").lower()
        needs_summary = any(kw in task_lower for kw in ["summarize", "summary", "brief", "condense", "tl;dr"])
        needs_translate = any(kw in task_lower for kw in ["translate", "translation", "french", "spanish", "language"])

        if last_member == "editor":
            if needs_translate:
                return "translator"
            elif needs_summary:
                return "summarizer"
            return "content_strategist"

        if last_member in self.CONDITIONAL_MEMBERS:
            return "content_strategist"

        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Build task for next member based on previous output."""
        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile final content with strategy assessment."""
        lines = ["[CONTENT SQUAD Complete]", ""]

        for member_name in ["writer", "editor", "summarizer", "translator", "content_strategist"]:
            if member_name in squad_result:
                lines.append(f"--- {member_name.upper()} ---")
                lines.append(squad_result[member_name][:500])
                lines.append("")

        return "\n".join(lines)


CONTENT_SQUAD.leader_class = ContentSquadLeader