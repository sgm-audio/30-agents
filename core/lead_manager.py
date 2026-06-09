"""
Lead management: deduplication, scoring, enrichment pipeline.
Provides LeadDeduplicator, LeadScorer, LeadEnricher, and LeadPipeline.
"""
import difflib
import time
import uuid
from typing import Any, Optional

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

HIGH_VALUE_INDUSTRIES = {
    "restaurant", "cafe", "bakery", "catering", "food", "bar", "pub", "diner",
    "salon", "spa", "barber", "nail", "skincare",
    "clinic", "dentist", "pharmacy", "physiotherapy", "chiropractor",
    "law", "legal", "accounting", "insurance", "real estate",
    "retail", "boutique", "shop", "store", "market",
    "hotel", "motel", "inn", "lodging",
    "plumber", "electrician", "hvac", "roofer", "landscaper", "painter", "cleaner",
    "mechanic", "auto", "tire", "car wash", "body shop",
}

INDUSTRY_CATEGORIES = {
    "Food & Dining": ["restaurant", "cafe", "bakery", "catering", "food truck", "bar", "pub", "diner", "pizzeria", "grill", "bistro", "eatery"],
    "Health & Wellness": ["clinic", "dentist", "pharmacy", "physiotherapy", "massage", "chiropractor", "spa", "yoga", "gym", "fitness", "optometrist", "counseling"],
    "Professional Services": ["lawyer", "accountant", "consultant", "insurance", "real estate", "architect", "engineer", "notary", "financial", "tax"],
    "Retail": ["store", "shop", "boutique", "market", "florist", "hardware", "apparel", "jewelry", "gift", "liquor", "convenience"],
    "Automotive": ["mechanic", "auto repair", "car wash", "tire shop", "body shop", "dealership", "oil change", "transmission"],
    "Home Services": ["plumber", "electrician", "hvac", "roofer", "landscaper", "painter", "cleaner", "handyman", "renovation", "contractor"],
    "Personal Care": ["salon", "barber", "nail", "skincare", "tattoo", "piercing", "hair", "beauty", "esthetics"],
    "Education": ["tutor", "school", "daycare", "preschool", "learning center", "training", "academy"],
    "Entertainment": ["theater", "arcade", "bowling", "escape room", "comedy club", "karaoke", "cinema"],
    "Lodging": ["hotel", "motel", "bed breakfast", "inn", "hostel", "resort"],
}


def _get_domain(url: Optional[str]) -> str:
    if not url:
        return ""
    url = url.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.split("/")[0].strip()


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def _is_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    return difflib.SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio() >= threshold


class LeadDeduplicator:
    """Deduplicates leads by domain, name, and address using Redis sets."""

    def __init__(self):
        self.redis = get_redis()

    async def deduplicate(self, leads: list[dict]) -> list[dict]:
        seen_domains: set[str] = set()
        seen_names: set[str] = set()
        unique: list[dict] = []

        existing_domains_raw = await self.redis.smembers("leads:domains:seen")
        seen_domains.update(existing_domains_raw or [])

        for lead in leads:
            domain = _get_domain(lead.get("website_url") or lead.get("website", ""))
            name = _normalize_name(str(lead.get("name", "")))

            if not name:
                continue

            if domain and domain in seen_domains:
                log.debug("lead.duplicate_domain", name=name, domain=domain)
                continue

            name_dup = False
            for seen in seen_names:
                if _is_similar(name, seen):
                    name_dup = True
                    break
            if name_dup:
                log.debug("lead.duplicate_name", name=name)
                continue

            seen_domains.add(domain) if domain else None
            seen_names.add(name)
            unique.append(lead)

        if unique:
            new_domains = [_get_domain(l.get("website_url") or l.get("website", "")) for l in unique]
            new_domains = [d for d in new_domains if d]
            if new_domains:
                await self.redis.sadd("leads:domains:seen", *new_domains)
            await self.redis.expire("leads:domains:seen", 90 * 86400)

        log.info("lead.dedup_done", input=len(leads), output=len(unique))
        return unique


class LeadScorer:
    """Scores leads 0-100 based on contact info, industry fit, and source quality."""

    def score(self, lead: dict) -> dict:
        score = 0
        breakdown: dict[str, int] = {}

        if lead.get("website_url") or lead.get("website"):
            breakdown["has_website"] = 0
            breakdown["no_website_bonus"] = 30
            score += 30
        else:
            breakdown["has_website"] = 0
            breakdown["no_website_bonus"] = 30
            score += 30

        if lead.get("phone"):
            breakdown["has_phone"] = 20
            score += 20
        else:
            breakdown["has_phone"] = 0

        if lead.get("address"):
            breakdown["has_address"] = 15
            score += 15
        else:
            breakdown["has_address"] = 0

        industry_raw = str(lead.get("industry", "")).lower()
        industry_hit = any(kw in industry_raw for kw in HIGH_VALUE_INDUSTRIES)
        if industry_hit:
            breakdown["industry_fit"] = 25
            score += 25
        else:
            breakdown["industry_fit"] = 10
            score += 10

        source = str(lead.get("source_url", "")).lower()
        if "google" in source or "maps" in source:
            breakdown["source_quality"] = 15
            score += 15
        elif "yellowpages" in source or "yp" in source:
            breakdown["source_quality"] = 10
            score += 10
        else:
            breakdown["source_quality"] = 5
            score += 5

        breakdown["freshness_bonus"] = 10
        score += 10

        lead["score"] = min(score, 100)
        lead["score_breakdown"] = breakdown
        return lead

    def score_all(self, leads: list[dict]) -> list[dict]:
        scored = [self.score(lead) for lead in leads]
        scored.sort(key=lambda l: l.get("score", 0), reverse=True)
        return scored


class LeadEnricher:
    """Enriches leads with industry category, estimated size, and priority."""

    def _classify_industry(self, industry: str) -> tuple[str, str]:
        industry_lower = industry.lower().strip()
        for category, keywords in INDUSTRY_CATEGORIES.items():
            for kw in keywords:
                if kw in industry_lower:
                    return category, kw
        return "Other Services", "general"

    def _estimate_size(self, lead: dict) -> str:
        name = str(lead.get("name", "")).lower()
        industry = str(lead.get("industry", "")).lower()
        large_signals = ["& associates", "group", "corporation", "inc", "ltd", "llp", "hospital", "dealership"]
        medium_signals = ["and", "&", "partners", "clinic", "centre", "center", "agency"]

        if any(s in name for s in large_signals):
            return "medium"
        if any(s in industry for s in ["hospital", "hotel", "dealership", "school"]):
            return "large"
        if any(s in name for s in medium_signals):
            return "medium"
        return "small"

    def enrich(self, lead: dict) -> dict:
        industry_raw = str(lead.get("industry", ""))
        category, subcategory = self._classify_industry(industry_raw)
        lead["industry_category"] = category
        lead["industry_subcategory"] = subcategory

        lead["estimated_size"] = self._estimate_size(lead)

        score = lead.get("score", 50)
        size_multiplier = {"small": 0.8, "medium": 1.0, "large": 1.3}
        priority_raw = score * size_multiplier.get(lead["estimated_size"], 1.0)
        lead["priority"] = round(min(priority_raw, 100), 1)
        lead["last_enriched"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return lead

    def enrich_all(self, leads: list[dict]) -> list[dict]:
        return [self.enrich(lead) for lead in leads]


class LeadPipeline:
    """Chains deduplication -> scoring -> enrichment and persists results."""

    def __init__(self):
        self.deduplicator = LeadDeduplicator()
        self.scorer = LeadScorer()
        self.enricher = LeadEnricher()
        self.redis = get_redis()

    async def process(self, leads: list[dict]) -> list[dict]:
        unique = await self.deduplicator.deduplicate(leads)
        scored = self.scorer.score_all(unique)
        enriched = self.enricher.enrich_all(scored)

        batch_id = str(uuid.uuid4())
        await self.redis.set(
            f"leads:pipeline:{batch_id}",
            enriched,
            ex=7 * 86400,
        )
        await self.redis.sadd("leads:batches", batch_id)
        await self.redis.expire("leads:batches", 90 * 86400)

        log.info("lead.pipeline_done", batch_id=batch_id, count=len(enriched))
        return enriched

    async def get_batch(self, batch_id: str) -> Optional[list[dict]]:
        return await self.redis.get(f"leads:pipeline:{batch_id}")

    async def list_batches(self) -> list[str]:
        batches = await self.redis.smembers("leads:batches")
        return list(batches or [])


async def get_lead_pipeline() -> LeadPipeline:
    return LeadPipeline()
