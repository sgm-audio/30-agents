"""
Squad Architecture for the 30-Agent System

A Squad is a group of specialist agents led by a leader agent that routes
work to members based on task type. This enables addressing a squad as a
unit (@OutreachSquad) rather than individual agents.

Squad Leader responsibilities:
1. Receive task with squad context
2. Analyze task and determine which member should handle it
3. Delegate to member, passing relevant context
4. Collect result from member and route to next member or finalize
5. Compile final result for the squad

Routing Logic:
- Each member returns to leader (not orchestrator) via `next_agent: "<squad_leader>"`
- Leader tracks `context["squad_stage"]` to know which member ran
- Leader decides next member or returns END

Usage:
    # Via API
    POST /api/squads/outreach/run  →  {"task": "Find leads in Vancouver"}

    # Via CLI
    python main.py squad run outreach --city Vancouver

    # Via chat (orchestrator routes to squad)
    "run the outreach pipeline" → orchestrator → @OutreachSquad leader
"""
from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

from squads.outreach import OutreachSquadLeader, OUTREACH_SQUAD
from squads.seo import SEOSquadLeader, SEO_SQUAD
from squads.analytics import AnalyticsSquadLeader, ANALYTICS_SQUAD
from squads.content import ContentSquadLeader, CONTENT_SQUAD
from squads.code import CodeSquadLeader, CODE_SQUAD
from squads.vision import VisionSquadLeader, VISION_SQUAD

ALL_SQUADS = {
    "outreach": OUTREACH_SQUAD,
    "seo": SEO_SQUAD,
    "analytics": ANALYTICS_SQUAD,
    "content": CONTENT_SQUAD,
    "code": CODE_SQUAD,
    "vision": VISION_SQUAD,
}

__all__ = [
    "SquadLeader",
    "SquadConfig",
    "SquadMember",
    "RoutingRule",
    "OutreachSquadLeader",
    "SEOSquadLeader",
    "AnalyticsSquadLeader",
    "ContentSquadLeader",
    "CodeSquadLeader",
    "VisionSquadLeader",
    "OUTREACH_SQUAD",
    "SEO_SQUAD",
    "ANALYTICS_SQUAD",
    "CONTENT_SQUAD",
    "CODE_SQUAD",
    "VISION_SQUAD",
    "ALL_SQUADS",
]