"""
SEO SQUAD — Full SEO audit and strategy pipeline

Squad: @SEOSquad
Pipeline: on_page_seo || technical_seo || content_seo → backlink_agent → web_design_concept

Leader: SEOSquadLeader
Members:
  - on_page_seo: Analyzes meta tags, headings, keyword density, internal links
  - technical_seo: Analyzes site speed, mobile, schema, sitemap, robots.txt
  - content_seo: Analyzes content length, readability, keyword gaps
  - backlink_agent: Finds competitor backlinks, guest post opportunities, local citations
  - web_design_concept: Researches design trends and proposes redesign concepts

Routing Logic:
  Three SEO audit agents run in PARALLEL (on_page, technical, content)
  Then backlink_agent runs
  Then web_design_concept runs
  All results are compiled into a comprehensive SEO report
"""
from typing import Any

import structlog

from agents.tier2_seo_design import (
    OnPageSEOAgent,
    TechnicalSEOAgent,
    ContentSEOAgent,
    BacklinkAgent,
    WebDesignConceptAgent,
)
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


SEO_MEMBERS = [
    SquadMember(
        name="on_page_seo",
        agent_class=OnPageSEOAgent,
        description="Analyzes on-page SEO factors (meta tags, headings, keywords)",
        keywords=["on page", "meta tag", "heading", "keyword density", "internal link"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="technical_seo",
        agent_class=TechnicalSEOAgent,
        description="Analyzes technical SEO (speed, mobile, schema, Core Web Vitals)",
        keywords=["technical", "speed", "mobile", "schema", "sitemap", "robots", "core web vitals"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="content_seo",
        agent_class=ContentSEOAgent,
        description="Analyzes content quality and SEO strategy",
        keywords=["content", "readability", "word count", "keyword gap", "E-E-A-T"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="backlink_agent",
        agent_class=BacklinkAgent,
        description="Finds backlink and citation opportunities",
        keywords=["backlink", "link building", "citation", "guest post", "directory"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="web_design_concept",
        agent_class=WebDesignConceptAgent,
        description="Researches design trends and proposes redesign concepts",
        keywords=["design", "redesign", "UX", "UI", "trends", "layout", "color"],
        model=settings.model_fast,
    ),
]


SEO_ROUTING = [
    RoutingRule(
        keywords=["on page seo", "on-page seo", "meta tag", "heading structure"],
        member_name="on_page_seo",
        priority=9,
    ),
    RoutingRule(
        keywords=["technical seo", "site speed", "core web vital", "mobile usability"],
        member_name="technical_seo",
        priority=9,
    ),
    RoutingRule(
        keywords=["content seo", "content audit", "readability", "keyword gap"],
        member_name="content_seo",
        priority=9,
    ),
    RoutingRule(
        keywords=["backlink", "link building", "citation", "guest post", "link opportunity"],
        member_name="backlink_agent",
        priority=7,
    ),
    RoutingRule(
        keywords=["design", "redesign", "UX", "UI", "concept"],
        member_name="web_design_concept",
        priority=5,
    ),
]


SEO_SQUAD = SquadConfig(
    name="seo",
    display_name="SEO",
    description="Full SEO audit and strategy: on-page + technical + content + backlinks + design",
    leader_class=None,
    members=SEO_MEMBERS,
    routing_rules=SEO_ROUTING,
    default_member="on_page_seo",
)


class SEOSquadLeader(SquadLeader):
    """
    Leader for the SEO squad. Manages parallel + sequential SEO analysis.

    Workflow:
    1. on_page_seo, technical_seo, content_seo run in parallel (or sequentially via stage tracking)
    2. backlink_agent runs after SEO audits complete
    3. web_design_concept runs last
    4. All results compiled into comprehensive SEO report
    """

    name = "seo_squad"
    description = "SEO audit squad leader"
    model = settings.model_fast
    system_prompt = """You are the SEO Squad Leader. You coordinate five specialists:

1. on_page_seo: Analyzes meta tags, headings, keyword usage, internal links
2. technical_seo: Analyzes speed, mobile, schema, Core Web Vitals
3. content_seo: Analyzes content quality and keyword targeting
4. backlink_agent: Finds link building and citation opportunities
5. web_design_concept: Proposes redesign concepts based on trends

Workflow:
- First THREE agents run in parallel: on_page_seo, technical_seo, content_seo
- Then backlink_agent runs
- Then web_design_concept runs
- Finally, compile all results into a comprehensive SEO report

You track progress via context["seo_completed"] (list of completed agents)."""

    AUDIT_AGENTS = ["on_page_seo", "technical_seo", "content_seo"]
    WORKFLOW_ORDER = ["on_page_seo", "technical_seo", "content_seo", "backlink_agent", "web_design_concept"]

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Start with on_page_seo."""
        return "on_page_seo"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Complete after web_design_concept runs."""
        return last_member == "web_design_concept"

    def get_next_member(self, last_member: str, context: dict) -> str | None:
        """Route to next member in workflow."""
        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Pass through the original URL task to next agents."""
        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile comprehensive SEO report from all agents."""
        lines = ["[SEO SQUAD Complete — Full Audit Report]", ""]

        agent_scores = {}
        for agent_name in self.AUDIT_AGENTS:
            ctx_key = f"{agent_name}_context"
            if ctx_key in squad_result:
                ctx = squad_result[ctx_key]
                if "onpage_score" in ctx:
                    agent_scores["on_page"] = ctx["onpage_score"]
                elif "technical_score" in ctx:
                    agent_scores["technical"] = ctx["technical_score"]
                elif "content_score" in ctx:
                    agent_scores["content"] = ctx["content_score"]

        if agent_scores:
            lines.append("SEO Scores:")
            for area, score in agent_scores.items():
                lines.append(f"  {area.replace('_', ' ').title()}: {score:.0f}/100")
            avg = sum(agent_scores.values()) / len(agent_scores)
            lines.append(f"  Overall: {avg:.0f}/100")
            lines.append("")

        for agent_name in self.WORKFLOW_ORDER:
            ctx_key = f"{agent_name}_context"
            if ctx_key in squad_result:
                ctx = squad_result[ctx_key]
                result = squad_result.get(agent_name, "")

                if agent_name == "on_page_seo":
                    lines.append("--- ON-PAGE SEO ---")
                    lines.append(f"Score: {ctx.get('onpage_score', 0):.0f}/100")
                    lines.append(result[:300] if result else "No detailed audit.")
                    lines.append("")

                elif agent_name == "technical_seo":
                    lines.append("--- TECHNICAL SEO ---")
                    lines.append(f"Score: {ctx.get('technical_score', 0):.0f}/100")
                    checks = ctx.get("technical_checks", {})
                    if checks:
                        passed = sum(1 for v in checks.values() if v is True)
                        total = len([v for v in checks.values() if isinstance(v, bool)])
                        lines.append(f"Checks passed: {passed}/{total}")
                    lines.append(result[:300] if result else "No detailed audit.")
                    lines.append("")

                elif agent_name == "content_seo":
                    lines.append("--- CONTENT SEO ---")
                    lines.append(f"Score: {ctx.get('content_score', 0):.0f}/100")
                    lines.append(f"Word count: {ctx.get('word_count', 0)}")
                    lines.append(result[:300] if result else "No detailed audit.")
                    lines.append("")

                elif agent_name == "backlink_agent":
                    lines.append("--- BACKLINK OPPORTUNITIES ---")
                    opps = ctx.get("backlink_opportunities", [])[:10]
                    lines.append(f"Total opportunities found: {len(ctx.get('backlink_opportunities', []))}")
                    for op in opps[:5]:
                        lines.append(f"  [{op.get('difficulty', '?')}] {op.get('domain', '')} ({op.get('type', '')})")
                    lines.append("")

                elif agent_name == "web_design_concept":
                    lines.append("--- DESIGN CONCEPT ---")
                    lines.append(result[:500] if result else "No design concept generated.")
                    lines.append("")

        return "\n".join(lines)


SEO_SQUAD.leader_class = SEOSquadLeader