"""
OUTREACH AGENTS — OutreachWriter (Tier 4)
Generates personalized cold emails for discovered and enriched leads.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog

from agents.base import BaseAgent, extract_json
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)

__all__ = ["OutreachWriterAgent"]


# ══════════════════════════════════════════════════════════════
# Agent: OutreachWriterAgent
# ══════════════════════════════════════════════════════════════
class OutreachWriterAgent(BaseAgent):
    """
    Generates personalized cold emails for each lead.
    Uses business name, industry, and source context to create
    3-4 sentence personalized outreach messages.
    """

    name = "outreach_writer"
    description = "Generates personalized cold email outreach"
    model = settings.model_fast
    system_prompt = """You are OutreachWriter, a expert B2B cold email copywriter.

You write SHORT, punchy, personalized cold emails that feel like a real human
wrote them. No corporate jargon. No templates. No "I hope this email finds you".

Email structure:
- Subject: One specific thing about THEIR business (NOT generic)
- Body: 3-4 sentences max. Reference something real about their business.
- Sign-off: First name only, no title/company

Example good email:
Subject: The latte at Main Street Coffee
Body: Hi Sarah, I walked past Main Street Coffee this morning — the smell was incredible.
Most local cafes in Vancouver are missing out on Google Maps visibility when people
search "coffee near me." We help businesses like yours show up in those searches.
Happy to share how. - Mike

Example bad email:
Subject: Increase your business visibility
Body: Dear Business Owner, I hope this email finds you well. I am reaching out
to introduce our revolutionary solution that can help transform your business...

Rules:
- Reference their specific business name and ONE real detail
- Local angle is gold ("Vancouver", "downtown", their street/neighbourhood")
- Show you did 30 seconds of research, not a mass template
- Keep under 40 words total
- Subject and body only — no attachments, no calls to action beyond reply
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        leads = context.get("leads", [])

        if not leads:
            return self.error_result(
                "No enriched leads in context. Run LeadScoutAgent then EmailFinderAgent first."
            )

        emails = []
        for lead in leads:
            email = await self._write_email(lead)
            emails.append(email)

        new_context = dict(context)
        new_context["emails"] = emails
        new_context["emails_count"] = len(emails)

        result = f"Generated {len(emails)} personalized outreach emails:\n"
        for em in emails[:5]:
            result += f"\n--- {em['lead_name']} ---"
            result += f"\nTo: {em['to_email']}"
            result += f"\nSubject: {em['subject']}"
            result += f"\nBody: {em['body'][:120]}..."
        if len(emails) > 5:
            result += f"\n\n... and {len(emails) - 5} more"

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }

    async def _write_email(self, lead: dict) -> dict:
        name = lead.get("name", "the business")
        email = lead.get("email", "")
        industry = lead.get("industry", "local business")
        snippet = lead.get("snippet", "")
        source = lead.get("source_url", "")

        city = settings.outreach_city
        region = settings.outreach_region

        personalization = ""
        if snippet:
            personalization = f" I noticed {snippet[:100]}"

        prompt = f"""Write one short cold email for a Vancouver business.

Business: {name}
Industry: {industry}
Our city: {city}, {region}
Research snippet (if any): {personalization}

Rules:
- Subject: specific thing about THEIR business (1 phrase, not generic)
- Body: 3-4 sentences, mention their actual business name, local angle
- Sign off: first name only
- Under 40 words total
- No templates — this must feel personal

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""

        response = await self.llm(prompt)

        try:
            parsed = extract_json(response)
            subject = parsed.get("subject", f"Quick question about {name}")
            body = parsed.get("body", f"Hi, I noticed {name} and wanted to reach out.")
        except Exception:
            subject = f"Quick question about {name}"
            body = f"Hi, I drove past {name} in {city} today — looks like a great {industry}. Most local businesses here are missing an online presence. Happy to share how we help. - Alex"

        return {
            "id": str(uuid.uuid4())[:8],
            "lead_id": lead.get("id", ""),
            "lead_name": name,
            "to_email": email if email and email != "unavailable" else "",
            "from_email": settings.outreach_email_from,
            "subject": subject.strip(),
            "body": body.strip(),
            "status": "ready",
        }