"""
OUTREACH AGENTS — Web Design Concept, SEO Team, Backlink (Tier 2)
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

import structlog

from agents.base import BaseAgent, extract_json
from core.config import settings
from core.graph import AgentState
from core.validation import validate_public_http_url

log = structlog.get_logger(__name__)

__all__ = [
    "WebDesignConceptAgent",
    "OnPageSEOAgent",
    "TechnicalSEOAgent",
    "ContentSEOAgent",
    "BacklinkAgent",
]


# ══════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════
def _serper_search(query: str, num_results: int = 10) -> list[dict]:
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
        return resp.json().get("organic", [])
    except Exception as e:
        log.warning("serper.search_failed", error=str(e))
        return []


def _tavily_search(query: str, max_results: int = 10) -> list[dict]:
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
        return resp.json().get("results", [])
    except Exception as e:
        log.warning("tavily.search_failed", error=str(e))
        return []


def _firecrawl_scrape(url: str, extract_links: bool = False) -> dict:
    import httpx
    key = settings.firecrawl_api_key
    if not key:
        return {}
    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v0/scrape",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "url": url,
                "pageOptions": {"onlyMainContent": True, "extractLinks": extract_links},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("data", [{}])[0] if resp.json().get("data") else {}
    except Exception as e:
        log.warning("firecrawl.scrape_failed", url=url, error=str(e))
        return {}


def _pagespeed_insights(url: str) -> dict:
    import httpx
    key = settings.serper_api_key
    if not key:
        return {}
    try:
        resp = httpx.get(
            f"https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeedReport?url={url}&strategy=mobile&key={key}",
            timeout=20.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "score": data.get("loadingExperience", {}).get("overall_category", "UNKNOWN"),
                "lcp": data.get("audits", {}).get("largest-contentful-paint", {}).get("numericValue", 0),
                "cls": data.get("audits", {}).get("cumulative-layout-shift", {}).get("numericValue", 0),
                "tbt": data.get("audits", {}).get("total-blocking-time", {}).get("numericValue", 0),
            }
    except Exception as e:
        log.debug("pagespeed.failed", url=url, error=str(e))
    return {}


# ══════════════════════════════════════════════════════════════
# Agent: WebDesignConceptAgent
# ══════════════════════════════════════════════════════════════
class WebDesignConceptAgent(BaseAgent):
    """
    Researches current web design trends and analyzes a target website
    to propose a modern redesign concept. Scrapes Dribbble, Behance,
    Awwwards, Designspiration, and the target site itself.
    """

    name = "web_design_concept"
    description = "Researches design trends and proposes redesign concepts"
    model = settings.model_fast
    system_prompt = """You are WebDesignConcept, an expert UX/UI designer and web design researcher.
You research what's currently "hitting" in web design and produce actionable redesign concepts.

Your research covers:
- Layout patterns (hero, masonry, split-screen, editorial, etc.)
- Color palettes and gradients currently trending
- Typography trends (font pairings, sizes, weights)
- Micro-interactions and animation trends
- Common UI component patterns (sticky navs, floating CTAs, etc.)
- Industry-specific design conventions

You produce a concrete, specific design concept document with:
1. A 2-3 sentence redesign concept statement
2. 5 specific "hit" design elements to incorporate (with URLs referencing real examples)
3. Recommended color palette (hex codes)
4. Typography pairing suggestion
5. 3 priority implementation steps

Be specific — reference actual sites, actual hex codes, actual fonts.
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        target_url = context.get("url", "")
        industry = context.get("industry", "")
        city = context.get("city", settings.outreach_city)

        trend_queries = [
            f"best web design trends 2025 {industry}",
            f"award winning website design {city} {industry}",
            f"modern small business website design inspiration 2025",
        ]

        trend_results = []
        for q in trend_queries:
            r = _tavily_search(q, max_results=8)
            trend_results.extend(r)
            await asyncio.sleep(0.3)

        target_analysis = {}
        if target_url and target_url not in ("none", ""):
            scraped = _firecrawl_scrape(target_url)
            if scraped:
                target_analysis = {
                    "title": scraped.get("title", ""),
                    "meta_desc": scraped.get("description", ""),
                    "h1s": scraped.get("h1", []),
                    "h2s": scraped.get("h2", [])[:10],
                    "content_preview": scraped.get("content", "")[:500],
                    "links": len(scraped.get("links", [])),
                }

        inspiration_sites = [
            ("Dribbble", "https://dribbble.com/search/projects?q="),
            ("Awwwards", "https://www.awwwards.com/websites/"),
            ("Designspiration", "https://www.designspiration.com/"),
        ]

        prompt_parts = [
            f"Design trend research for: {industry} websites in {city}",
            f"\nFound {len(trend_results)} trend articles:\n",
        ]
        for r in trend_results[:5]:
            prompt_parts.append(f"- {r.get('title', '')}: {r.get('url', '')}")

        if target_analysis:
            prompt_parts.append(f"\nTarget site analysis:\n{json.dumps(target_analysis, indent=2)}")

        prompt_parts.append(f"\n\nProduce a design concept document for this type of {industry} business.")

        design_concept = await self.llm(
            prompt="\n".join(prompt_parts),
            system=self.system_prompt,
        )

        result = f"Design Concept Research:\n\nFound {len(trend_results)} trend sources\n\n"
        result += design_concept

        new_context = dict(context)
        new_context["design_concept"] = design_concept
        new_context["trend_sources"] = [
            {"title": r.get("title", ""), "url": r.get("url", "")} for r in trend_results[:10]
        ]

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent: OnPageSEOAgent
# ══════════════════════════════════════════════════════════════
class OnPageSEOAgent(BaseAgent):
    """
    Analyzes on-page SEO factors for a given URL:
    meta tags, title, headings hierarchy, keyword usage, internal links,
    image alt text, and content structure.
    """

    name = "on_page_seo"
    description = "Analyzes on-page SEO factors for a URL"
    model = settings.model_fast
    system_prompt = """You are OnPageSEO, a technical SEO analyst.
Given scraped page data and search context, audit the on-page SEO and score each factor.

Scoring: EXCELLENT / GOOD / NEEDS_WORK / MISSING

Factors to audit:
1. Title tag (50-60 chars, primary keyword, unique)
2. Meta description (120-160 chars, call to action, keyword)
3. H1 (exactly one, contains primary keyword)
4. H2/H3 hierarchy (logical, contains secondary keywords)
5. URL structure (clean, readable, keyword in slug)
6. Image alt text (descriptive, not "image1")
7. Internal/external links (presence and quality)
8. Keyword density (primary keyword appears 1-3% naturally)
9. Content length (minimum 300 words for service pages)
10. Schema/structured data (local business, service, etc.)

Return a scored audit with specific line-by-line recommendations.
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        target_url = context.get("url", "") or state["task"].split(" ")[-1]
        keyword = context.get("keyword", "")

        if not target_url or target_url == "none":
            return self.error_result("No URL provided. Pass url in context.")

        scraped = _firecrawl_scrape(target_url, extract_links=True)
        links = scraped.get("links", []) or []

        content = scraped.get("content", "") or ""
        title = scraped.get("title", "")
        meta_desc = scraped.get("description", "")
        h1s = scraped.get("h1", [])
        h2s = scraped.get("h2", [])[:10]
        h3s = scraped.get("h3", [])[:10]

        word_count = len(content.split())
        title_len = len(title)
        meta_len = len(meta_desc)
        keyword_lower = keyword.lower()
        content_lower = content.lower()
        keyword_count = content_lower.count(keyword_lower)
        keyword_density = (keyword_count / max(word_count, 1)) * 100 if keyword else 0

        internal_links = sum(1 for l in links if l.get("ref", "").startswith("/") or target_url in l.get("ref", ""))
        external_links = len(links) - internal_links

        prompt = f"""On-Page SEO Audit for: {target_url}

Title: "{title}" ({title_len} chars - ideal 50-60)
Meta: "{meta_desc[:120]}" ({meta_len} chars - ideal 120-160)
H1: {h1s}
H2s: {h2s}
H3s: {h3s}
Content: {content[:800]}... ({word_count} words)
Keyword: "{keyword}"
Keyword density: {keyword_density:.1f}%
Internal links: {internal_links}
External links: {external_links}

{self.system_prompt}

Provide a scored audit (EXCELLENT/GOOD/NEEDS_WORK/MISSING) for each factor with specific recommendations."""
        audit = await self.llm(prompt)

        score_map = {"EXCELLENT": 100, "GOOD": 75, "NEEDS_WORK": 40, "MISSING": 0}
        score = sum(score_map.get(tag, 50) for tag in audit.split()) / max(audit.count("/"), 1) * 10

        new_context = dict(context)
        new_context["onpage_audit"] = audit
        new_context["onpage_score"] = min(100, max(0, score))

        return {
            "context": new_context,
            "result": f"On-Page SEO Audit: {target_url}\n\nScore: {new_context['onpage_score']:.0f}/100\n\n{audit}",
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent: TechnicalSEOAgent
# ══════════════════════════════════════════════════════════════
class TechnicalSEOAgent(BaseAgent):
    """
    Analyzes technical SEO: site speed (proxy via Pagespeed),
    mobile usability, schema markup, XML sitemap, robots.txt,
    Core Web Vitals signals, HTTPS, and crawlability.
    """

    name = "technical_seo"
    description = "Analyzes technical SEO factors"
    model = settings.model_reason
    system_prompt = """You are TechnicalSEO, a technical SEO expert.
Analyze the technical health of a website and identify blockers.

Check and score:
1. HTTPS (must be present)
2. XML sitemap (present and non-empty)
3. Robots.txt (not blocking important pages)
4. Mobile responsiveness (or AMP fallback)
5. Core Web Vitals: LCP < 2.5s, CLS < 0.1, TBT < 200ms
6. Schema/structured data (local business, FAQ, service)
7. Canonical URL correctness
8. Image compression / next-gen formats (WebP)
9. Render-blocking resources
10. Hreflang for multilingual sites

Return: score out of 100 + specific prioritized fixes
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        target_url = context.get("url", "") or state["task"].split(" ")[-1]

        if not target_url or target_url == "none":
            return self.error_result("No URL provided.")

        checks = {}

        checks["https"] = target_url.startswith("https")

        sitemap_url = target_url.rstrip("/") + "/sitemap.xml"
        robots_url = target_url.rstrip("/") + "/robots.txt"
        for check_url, key in [(sitemap_url, "sitemap"), (robots_url, "robots_txt")]:
            try:
                import httpx
                safe_check_url = validate_public_http_url(check_url)
                r = httpx.get(safe_check_url, timeout=8.0, follow_redirects=True)
                checks[key] = r.status_code == 200 and len(r.text) > 10
            except Exception:
                checks[key] = False

        pagespeed = _pagespeed_insights(target_url)
        checks["pagespeed_score"] = pagespeed.get("score", "UNKNOWN")
        checks["lcp_ms"] = pagespeed.get("lcp", 0)
        checks["cls"] = pagespeed.get("cls", 0)
        checks["tbt_ms"] = pagespeed.get("tbt", 0)

        schema_url = target_url.rstrip("/") + "/schema.json"
        try:
            import httpx
            safe_schema_url = validate_public_http_url(schema_url)
            r = httpx.get(safe_schema_url, timeout=5.0)
            checks["schema_json"] = r.status_code == 200
        except Exception:
            checks["schema_json"] = False

        try:
            import httpx
            scraped = _firecrawl_scrape(target_url)
            content = scraped.get("content", "")[:2000]
            has_schema = bool(re.search(r'"@type"', content) or re.search(r"application/ld\+json", content))
            checks["schema_markup"] = has_schema
            checks["has_favicon"] = "icon" in content.lower() or "favicon" in content.lower()
        except Exception:
            checks["schema_markup"] = False
            checks["has_favicon"] = False

        score = 0
        score += 15 if checks.get("https") else 0
        score += 10 if checks.get("sitemap") else 0
        score += 10 if checks.get("robots_txt") else 0
        ps = str(checks.get("pagespeed_score", "UNKNOWN"))
        if ps != "UNKNOWN":
            score += min(25, int(ps.replace("FAST", "90").replace("AVERAGE", "60").replace("SLOW", "30"), 20))
        score += 15 if checks.get("schema_markup") else 0
        score += 10 if checks.get("has_favicon") else 0
        score += 15 if checks.get("lcp_ms", 9999) < 2500 else 5

        prompt = f"""Technical SEO Audit for: {target_url}

Checks:
{json.dumps(checks, indent=2)}

{self.system_prompt}

Provide a detailed technical SEO report with score out of 100 and prioritized fix list.
Score interpretation: 90+ EXCELLENT, 70-89 GOOD, 50-69 NEEDS_WORK, <50 CRITICAL
"""
        audit = await self.llm(prompt)

        new_context = dict(context)
        new_context["technical_audit"] = audit
        new_context["technical_score"] = min(100, score)
        new_context["technical_checks"] = checks

        return {
            "context": new_context,
            "result": f"Technical SEO Audit: {target_url}\n\nScore: {min(100, score):.0f}/100\n\n{audit}",
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent: ContentSEOAgent
# ══════════════════════════════════════════════════════════════
class ContentSEOAgent(BaseAgent):
    """
    Analyzes content quality for SEO: word count vs competitors,
    readability score, keyword targeting, content freshness,
    and content gap vs competitors.
    """

    name = "content_seo"
    description = "Analyzes content SEO quality and keyword targeting"
    model = settings.model_fast
    system_prompt = """You are ContentSEO, a content marketing and SEO writer.
Audit the content quality of a web page for SEO purposes.

Evaluate:
1. Content length (service pages: 500-1500 words ideal; homepage: 300-800)
2. Readability (Flesch-Kincaid grade 6-8 for consumer, 10-12 for B2B)
3. Primary keyword presence in first 100 words
4. LSI keywords / semantic variations present
5. Content freshness (are dates/years referenced?)
6. CTA present (what should the reader do next?)
7. Competitor content gap (what do top-ranking pages have that this doesn't?)
8. E-E-A-T signals (Experience, Expertise, Authority, Trust)

Return specific recommendations organized by priority.
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        target_url = context.get("url", "") or state["task"].split(" ")[-1]
        keyword = context.get("keyword", "web design Vancouver")

        if not target_url or target_url == "none":
            return self.error_result("No URL provided.")

        scraped = _firecrawl_scrape(target_url)
        content = scraped.get("content", "") or ""

        content_words = len(content.split())
        title = scraped.get("title", "") or ""
        meta_desc = scraped.get("description", "") or ""

        first_100 = " ".join(content.split()[:100]) if content else ""

        competitor_query = f"top ranking pages for {keyword} -site:{target_url.replace('https://', '').replace('http://', '')}"
        competitors = _serper_search(competitor_query, num_results=5)

        prompt = f"""Content SEO Audit for: {target_url}
Keyword target: "{keyword}"

Page title: "{title}"
Meta description: "{meta_desc}"
Content: {content[:2000]}...
First 100 words: {first_100}
Word count: {content_words}

Competitor titles found:
{chr(10).join(f"- {c.get('title','')}: {c.get('link','')}" for c in competitors[:5])}

{self.system_prompt}

Provide a content SEO audit with:
- Content score out of 100
- Readability assessment
- Keyword gap analysis vs competitors
- 5 specific content improvement recommendations
"""
        audit = await self.llm(prompt)

        content_score = 70
        if content_words < 300:
            content_score -= 20
        elif content_words > 500:
            content_score += 10
        if keyword.lower() in first_100.lower():
            content_score += 15
        if competitors:
            content_score += 5

        new_context = dict(context)
        new_context["content_audit"] = audit
        new_context["content_score"] = min(100, max(0, content_score))
        new_context["word_count"] = content_words

        return {
            "context": new_context,
            "result": f"Content SEO Audit: {target_url}\n\nWord count: {content_words}\nScore: {min(100, max(0, content_score)):.0f}/100\n\n{audit}",
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent: BacklinkAgent
# ══════════════════════════════════════════════════════════════
class BacklinkAgent(BaseAgent):
    """
    Finds backlink acquisition opportunities for a target website.
    - Scrapes competitor backlinks via Serper
    - Finds "write for us" / guest post opportunities
    - Finds local citations (Vancouver/BC directories)
    - Identifies broken link building targets
    - Ranks opportunities by difficulty and potential value
    """

    name = "backlink_agent"
    description = "Finds backlink and citation opportunities"
    model = settings.model_fast
    system_prompt = """You are BacklinkAgent, a link building strategist.
Find backlink opportunities for a local Vancouver business website.

Strategy areas:
1. COMPETITOR BACKLINKS: Find who links to competitor sites (search "link:[competitor-url]")
2. GUEST POST: Find "write for us" / "contribute" pages in the industry
3. LOCAL CITATIONS: Vancouver/BC directories, Yelp, Houzz, Google Business, YellowPages, etc.
4. BROKEN LINK BUILDING: Find resource pages in the industry with dead links
5. RESOURCE PAGES: Pages that curate helpful links in this industry

For each opportunity provide:
- Domain name and URL
- Type (citation/guest_post/competitor/broken_link/resource)
- Domain Authority estimate (HIGH/MEDIUM/LOW)
- "Link difficulty" (EASY/MEDIUM/HARD)
- What anchor text to use
- Specific contact or submission form URL if available

Focus on Vancouver/BC local opportunities for maximum local SEO impact.
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        context = state.get("context", {})
        target_url = context.get("url", "") or state["task"].split(" ")[-1]
        keyword = context.get("keyword", "web design Vancouver")
        city = context.get("city", settings.outreach_city)
        region = context.get("region", settings.outreach_region)
        industry = context.get("industry", "")

        opportunities = []

        if target_url and target_url not in ("none", ""):
            comp_searches = [
                f"link:{target_url}",
                f"\"{target_url}\" backlinks",
            ]
            for q in comp_searches:
                results = _serper_search(q, num_results=10)
                for r in results:
                    opportunities.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "competitor_backlink",
                        "domain": _extract_domain(r.get("link", "")),
                        "url": r.get("link", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                        "da": _estimate_da(r.get("link", "")),
                        "difficulty": "MEDIUM",
                        "anchor_text": keyword,
                        "notes": "Competitor backlink — offer similar or better content",
                    })
                await asyncio.sleep(0.3)

        guest_queries = [
            f'"{industry}" "write for us"',
            f'"{industry}" "contribute" "guest post"',
            f'"{city}" "{industry}" "submit article"',
            f'"{industry}" "resource page" "submit"',
        ]
        for q in guest_queries:
            results = _serper_search(q, num_results=8)
            for r in results:
                opportunities.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "guest_post",
                    "domain": _extract_domain(r.get("link", "")),
                    "url": r.get("link", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "da": _estimate_da(r.get("link", "")),
                    "difficulty": "MEDIUM",
                    "anchor_text": keyword,
                    "notes": "Guest post / contributor opportunity",
                })
            await asyncio.sleep(0.3)

        local_queries = [
            f"{city} {industry} directory",
            f"{city} {industry} Yelp",
            f"Vancouver BC {industry} YellowPages",
            f"{industry} {region} business listing",
        ]
        for q in local_queries:
            results = _serper_search(q, num_results=8)
            for r in results:
                domain = _extract_domain(r.get("link", ""))
                opportunities.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "local_citation",
                    "domain": domain,
                    "url": r.get("link", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "da": _estimate_da(r.get("link", "")),
                    "difficulty": "EASY",
                    "anchor_text": f"{city} {industry}",
                    "notes": "Local citation — NAP consistency is critical",
                })
            await asyncio.sleep(0.3)

        seen = set()
        unique = []
        for op in opportunities:
            key = (op["type"], op["domain"])
            if key not in seen and op["domain"]:
                seen.add(key)
                unique.append(op)

        unique.sort(key=lambda x: {"EASY": 0, "MEDIUM": 1, "HARD": 2}.get(x["difficulty"], 1))

        summary = {
            "total_opportunities": len(unique),
            "by_type": {},
            "easy_wins": [op for op in unique if op["difficulty"] == "EASY"],
            "medium_priority": [op for op in unique if op["difficulty"] == "MEDIUM"],
        }
        for op in unique:
            t = op["type"]
            summary["by_type"][t] = summary["by_type"].get(t, 0) + 1

        result_lines = [f"Found {len(unique)} unique backlink opportunities:\n"]
        result_lines.append(f"By type: {summary['by_type']}")
        result_lines.append(f"\nEASY wins ({len(summary['easy_wins'])}):")
        for op in summary["easy_wins"][:5]:
            result_lines.append(f"  [{op['type']}] {op['domain']} - {op['url']}")
        result_lines.append(f"\nMEDIUM priority ({len(summary['medium_priority'])}):")
        for op in summary["medium_priority"][:5]:
            result_lines.append(f"  [{op['type']}] {op['domain']} - DA: {op['da']}")

        new_context = dict(context)
        new_context["backlink_opportunities"] = unique
        new_context["backlink_summary"] = summary

        return {
            "context": new_context,
            "result": "\n".join(result_lines),
            "next_agent": "END",
        }


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


def _estimate_da(url: str) -> str:
    domain = _extract_domain(url).lower()
    high_da_domains = {"wikipedia.org", "yelp.com", "yellowpages.ca", "houzz.com", "google.com", "linkedin.com", "facebook.com", "bbb.org", "houzz.ca", "tripadvisor.com"}
    medium_da_domains = {"blogspot.com", "wordpress.com", "medium.com", "quora.com", "reddit.com", "facebook.com", "instagram.com"}
    if any(d in domain for d in high_da_domains):
        return "HIGH"
    if any(d in domain for d in medium_da_domains):
        return "MEDIUM"
    return "MEDIUM"