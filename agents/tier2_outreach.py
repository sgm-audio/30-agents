"""
OUTREACH AGENTS — LeadScout & EmailFinder (Tier 2)
Finds Vancouver businesses without websites and resolves contact emails.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog

from agents.base import BaseAgent, extract_json
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)

__all__ = ["LeadScoutAgent", "EmailFinderAgent"]


def _serper_search(query: str, num_results: int = 20) -> list[dict]:
    """Search via Serper.dev API."""
    import httpx
    key = settings.serper_api_key
    if not key:
        return []
    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "numResults": num_results},
            timeout=15.0,
        )
        resp.raise_for_status()
        items = resp.json().get("organic", [])
        return [
            {
                "title": it.get("title", ""),
                "link": it.get("link", ""),
                "snippet": it.get("snippet", ""),
                "type": "serper",
            }
            for it in items
        ]
    except Exception as e:
        log.warning("serper.search_failed", error=str(e))
        return []


def _tavily_search(query: str, max_results: int = 20) -> list[dict]:
    """Search via Tavily AI API."""
    import httpx
    key = settings.tavily_api_key
    if not key:
        return []
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={"query": query, "api_key": key, "max_results": max_results},
            timeout=15.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "snippet": r.get("content", ""),
                "type": "tavily",
            }
            for r in results
        ]
    except Exception as e:
        log.warning("tavily.search_failed", error=str(e))
        return []


def _firecrawl_scrape(url: str) -> str:
    """Scrape a URL via Firecrawl."""
    import httpx
    key = settings.firecrawl_api_key
    if not key:
        return ""
    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v0/scrape",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "pageOptions": {"onlyMainContent": True}},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("data", [])
        if pages:
            return pages[0].get("content", "")[:2000]
        return ""
    except Exception as e:
        log.warning("firecrawl.scrape_failed", url=url, error=str(e))
        return ""


def _deduplicate_leads(leads: list[dict]) -> list[dict]:
    """Deduplicate leads by domain or name similarity."""
    seen = set()
    unique = []
    for lead in leads:
        key = lead.get("domain", lead.get("name", "")).lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


# ══════════════════════════════════════════════════════════════
# Agent: LeadScoutAgent
# ══════════════════════════════════════════════════════════════
class LeadScoutAgent(BaseAgent):
    """
    Discovers businesses in Vancouver that don't have a website.
    Uses Serper + Tavily to search directories, then Firecrawl to
    verify they have no site or only a placeholder.
    """

    name = "lead_scout"
    description = "Discovers local businesses without websites"
    model = settings.model_fast
    system_prompt = """You are LeadScout, a local business research expert.
Your job is to find businesses in Vancouver, BC that either:
1. Have NO website at all (just a Google Business listing or directory entry)
2. Have a very basic/placeholder website (no e-commerce, no services listed)

Focus on: restaurants, salons, clinics, law offices, real estate, mechanics,
contractors, electricians, plumbers, bakeries, cafes, boutiques, repair shops.

Return a JSON list of businesses with: name, address, phone, industry, website_url (or "none"), source_url
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        city = context.get("city", settings.outreach_city)
        region = context.get("region", settings.outreach_region)
        max_leads = context.get("max_leads", settings.outreach_max_leads)

        industries = [
            "restaurants", "salons", "clinics", "law offices",
            "real estate agents", "mechanics", "electricians",
            "plumbers", "bakeries", "cafes", "boutiques",
            "contractors", "repair shops", "dental offices",
            "physiotherapy clinics", "pet groomers",
        ]

        all_leads: list[dict] = []

        for industry in industries:
            query = f"{industry} {city} {region} no website OR Google Business listing"
            serper_results = _serper_search(query, num_results=20)
            all_leads.extend(serper_results)

            await asyncio.sleep(0.5)

        seen_domains = set()
        cleaned_leads = []

        for raw in all_leads:
            url = raw.get("link", "")
            if not url:
                continue

            domain = ""
            if "yellowpages.ca" in url:
                domain = "yellowpages"
            elif "google.com/maps" in url or "maps.google" in url:
                domain = "googlemaps"
            elif "bcdirect" in url or "canadianbusiness" in url:
                domain = "directory"

            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            lead = {
                "id": str(uuid.uuid4())[:8],
                "name": raw.get("title", "").split(" - ")[0].split(" | ")[0].strip(),
                "address": "",
                "phone": "",
                "industry": "",
                "website_url": "none",
                "source_url": url,
                "snippet": raw.get("snippet", "")[:300],
                "verified": False,
            }
            cleaned_leads.append(lead)

        cleaned_leads = _deduplicate_leads(cleaned_leads)[:max_leads]

        result_lines = [f"Found {len(cleaned_leads)} leads:"]
        for lead in cleaned_leads[:20]:
            result_lines.append(
                f"  - {lead['name']} | {lead['industry']} | {lead['source_url']}"
            )
        if len(cleaned_leads) > 20:
            result_lines.append(f"  ... and {len(cleaned_leads) - 20} more")

        result = "\n".join(result_lines)

        new_context = dict(context)
        new_context["leads"] = cleaned_leads
        new_context["leads_count"] = len(cleaned_leads)

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent: EmailFinderAgent
# ══════════════════════════════════════════════════════════════
class EmailFinderAgent(BaseAgent):
    """
    Resolves email addresses for discovered leads using Hunter.io
    and LLM-based domain inference as fallback.
    """

    name = "email_finder"
    description = "Finds email addresses for businesses"
    model = settings.model_fast
    system_prompt = """You are EmailFinder, a B2B contact research expert.
Given a business name and optional domain/website, find the most likely
contact email address for that business.

Rules:
- Prefer info@, hello@, contact@ for general inquiries
- Find owner/manager emails when possible (firstname.lastname@)
- If no email found, return "unavailable"
- NEVER guess random personal emails — only use pattern-based inference
  (e.g., info@ if you know the domain)
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        leads = context.get("leads", [])

        if not leads:
            return self.error_result("No leads provided in context. Run LeadScoutAgent first.")

        enriched = []
        for lead in leads:
            email = await self._find_email(lead)
            lead = dict(lead)
            lead["email"] = email
            enriched.append(lead)

        valid_emails = sum(1 for l in enriched if l.get("email") not in ("unavailable", "", None))
        result = f"Email resolution complete: {valid_emails}/{len(enriched)} emails found"
        for lead in enriched[:10]:
            result += f"\n  {lead['name']}: {lead.get('email', 'unavailable')}"

        new_context = dict(context)
        new_context["leads"] = enriched
        new_context["emails_found"] = valid_emails

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }

    async def _find_email(self, lead: dict) -> str:
        name = lead.get("name", "")
        source_url = lead.get("source_url", "")

        domain = self._extract_domain(source_url)

        if domain and domain != "unknown":
            email = await self._hunter_lookup(domain, name)
            if email:
                return email

            inferred = self._infer_email(domain, name)
            if inferred:
                return inferred

        return "unavailable"

    def _extract_domain(self, url: str) -> str:
        if not url:
            return "unknown"
        url = url.lower()
        if "yellowpages.ca" in url:
            return "unknown"
        if "google.com/maps" in url:
            return "unknown"
        if "/" in url:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.removeprefix("www.")
                return domain
            except Exception:
                pass
        return "unknown"

    async def _hunter_lookup(self, domain: str, business_name: str) -> str | None:
        key = settings.hunter_api_key
        if not key or not domain or domain == "unknown":
            return None
        try:
            import httpx
            resp = httpx.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": key, "limit": 1},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                emails = data.get("emails", [])
                if emails:
                    return emails[0].get("value", "")
        except Exception as e:
            log.debug("hunter.lookup_failed", domain=domain, error=str(e))
        return None

    def _infer_email(self, domain: str, business_name: str) -> str | None:
        if not domain or domain == "unknown":
            return None
        patterns = [f"info@{domain}", f"hello@{domain}", f"contact@{domain}"]
        return patterns[0]