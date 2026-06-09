"""
OUTREACH SQUAD — Lead generation and cold email pipeline

Squad: @OutreachSquad
Pipeline: lead_scout → email_finder → outreach_writer

Leader: OutreachSquadLeader
Members:
  - lead_scout: Discovers businesses without websites
  - email_finder: Resolves email addresses for leads
  - outreach_writer: Generates personalized cold emails

Routing Logic:
  Stage "start": Analyze task, route to lead_scout first
  Stage "delegating" → lead_scout done: Route to email_finder
  Stage "delegating" → email_finder done: Route to outreach_writer
  Stage "delegating" → outreach_writer done: Compile results, END
"""
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.tier2_outreach import LeadScoutAgent, EmailFinderAgent
from agents.tier4_outreach import OutreachWriterAgent
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


OUTREACH_MEMBERS = [
    SquadMember(
        name="lead_scout",
        agent_class=LeadScoutAgent,
        description="Discovers local businesses without websites",
        keywords=["find leads", "discover businesses", "no website", "lead scout", "find businesses"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="email_finder",
        agent_class=EmailFinderAgent,
        description="Finds email addresses for businesses",
        keywords=["find email", "enrich leads", "resolve emails", "email lookup"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="outreach_writer",
        agent_class=OutreachWriterAgent,
        description="Generates personalized cold emails",
        keywords=["cold email", "outreach", "write email", "generate email", "email copy"],
        model=settings.model_fast,
    ),
]


OUTREACH_ROUTING = [
    RoutingRule(
        keywords=["lead", "scout", "discover", "find business", "no website", "vancouver"],
        member_name="lead_scout",
        priority=10,
    ),
    RoutingRule(
        keywords=["email", "enrich", "resolve", "contact"],
        member_name="email_finder",
        priority=8,
    ),
    RoutingRule(
        keywords=["email", "outreach", "cold email", "write", "generate", "send"],
        member_name="outreach_writer",
        priority=6,
    ),
]


OUTREACH_SQUAD = SquadConfig(
    name="outreach",
    display_name="Outreach",
    description="Lead generation and cold email pipeline: discover businesses → find emails → write outreach",
    leader_class=None,
    members=OUTREACH_MEMBERS,
    routing_rules=OUTREACH_ROUTING,
    default_member="lead_scout",
)


class OutreachSquadLeader(SquadLeader):
    """
    Leader for the Outreach squad. Manages the lead_scout → email_finder → outreach_writer pipeline.

    Routing logic:
    1. Always starts with lead_scout to discover leads
    2. After lead_scout, routes to email_finder to enrich leads
    3. After email_finder, routes to outreach_writer to generate emails
    4. After outreach_writer, compiles results and returns END
    """

    name = "outreach_squad"
    description = "Lead generation and cold email squad leader"
    model = settings.model_fast
    system_prompt = """You are the Outreach Squad Leader. You coordinate three specialists:

1. lead_scout: Discovers businesses without websites in Vancouver
2. email_finder: Finds email addresses for discovered leads
3. outreach_writer: Generates personalized cold emails

Your workflow is ALWAYS sequential:
lead_scout → email_finder → outreach_writer → END

You route based on squad_stage stored in context:
- squad_stage: "start" → route to lead_scout
- After lead_scout completes → route to email_finder
- After email_finder completes → route to outreach_writer
- After outreach_writer completes → compile results and END

Respond with JSON for routing decisions: {"next_member": "...", "reasoning": "..."}
"""

    WORKFLOW_ORDER = ["lead_scout", "email_finder", "outreach_writer"]

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Always start with lead_scout since pipeline must run in order."""
        return "lead_scout"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Squad is complete after outreach_writer runs."""
        return last_member == "outreach_writer"

    def get_next_member(self, last_member: str, context: dict) -> str | None:
        """Return the next member in the workflow, or None if done."""
        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Generate the task for the next member based on previous results."""
        if next_member == "email_finder":
            leads = context.get("squad_result", {}).get("lead_scout_context", {}).get("leads", [])
            return f"Find email addresses for these {len(leads)} leads"

        if next_member == "outreach_writer":
            enriched = context.get("squad_result", {}).get("email_finder_context", {}).get("leads", [])
            valid = [l for l in enriched if l.get("email") and l.get("email") != "unavailable"]
            return f"Generate cold outreach emails for {len(valid)} enriched leads"

        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile final outreach pipeline results."""
        leads_count = 0
        emails_count = 0
        emails_found = 0

        if "lead_scout_context" in squad_result:
            leads_count = len(squad_result["lead_scout_context"].get("leads", []))

        if "email_finder_context" in squad_result:
            leads = squad_result["email_finder_context"].get("leads", [])
            emails_found = sum(1 for l in leads if l.get("email") and l.get("email") != "unavailable")

        if "outreach_writer_context" in squad_result:
            emails_count = len(squad_result["outreach_writer_context"].get("emails", []))

        lines = [
            "[OUTREACH SQUAD Complete]",
            f"",
            f"Pipeline summary:",
            f"  Businesses found: {leads_count}",
            f"  Emails resolved: {emails_found}",
            f"  Cold emails generated: {emails_count}",
            f"",
        ]

        if "outreach_writer" in squad_result and "outreach_writer_context" in squad_result:
            emails = squad_result["outreach_writer_context"].get("emails", [])
            if emails:
                lines.append("Sample emails:")
                for em in emails[:3]:
                    lines.append(f"  --- {em.get('lead_name', 'Unknown')} ---")
                    lines.append(f"  To: {em.get('to_email', 'N/A')}")
                    lines.append(f"  Subject: {em.get('subject', '')}")
                    lines.append(f"  Body: {em.get('body', '')[:80]}...")
                    lines.append("")

        return "\n".join(lines)


OUTREACH_SQUAD.leader_class = OutreachSquadLeader