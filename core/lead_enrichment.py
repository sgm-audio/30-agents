"""
Lead enrichment: social media, reviews, business info, industry classification.
Provides DataEnricher, LeadValidator, IndustryClassifier, and EnrichmentPipeline.
"""
import time
from typing import Any, Optional

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

INDUSTRY_CATEGORIES = {
    "Food & Dining": ["restaurant", "cafe", "bakery", "catering", "food truck", "bar", "pub", "diner", "pizzeria", "grill", "bistro", "eatery", "sushi", "pho", "ramen", "curry"],
    "Health & Wellness": ["clinic", "dentist", "pharmacy", "physiotherapy", "massage", "chiropractor", "spa", "yoga", "gym", "fitness", "optometrist", "counseling", "acupuncture", "naturopath"],
    "Professional Services": ["lawyer", "accountant", "consultant", "insurance", "real estate", "architect", "engineer", "notary", "financial", "tax", "bookkeeping", "paralegal"],
    "Retail": ["store", "shop", "boutique", "market", "florist", "hardware", "apparel", "jewelry", "gift", "liquor", "convenience", "thrift", "antique", "bookstore"],
    "Automotive": ["mechanic", "auto repair", "car wash", "tire shop", "body shop", "dealership", "oil change", "transmission", "detailing", "muffler"],
    "Home Services": ["plumber", "electrician", "hvac", "roofer", "landscaper", "painter", "cleaner", "handyman", "renovation", "contractor", "carpenter", "mover", "exterminator"],
    "Personal Care": ["salon", "barber", "nail", "skincare", "tattoo", "piercing", "hair", "beauty", "esthetics", "waxing", "lash"],
    "Education": ["tutor", "school", "daycare", "preschool", "learning center", "training", "academy", "music lesson", "driving school"],
    "Entertainment": ["theater", "arcade", "bowling", "escape room", "comedy club", "karaoke", "cinema", "pool hall"],
    "Lodging": ["hotel", "motel", "bed breakfast", "inn", "hostel", "resort", "b&b"],
    "Pet Services": ["vet", "veterinary", "groomer", "pet store", "dog walking", "pet sitting", "kennel"],
}


class DataEnricher:
    """Enriches leads with social media, reviews, and business info."""

    def __init__(self):
        self.redis = get_redis()

    def enrich_social_media(self, lead: dict) -> dict:
        name = str(lead.get("name", "")).lower().replace(" ", "")
        city = str(lead.get("city") or lead.get("address", "")).lower()
        social = {
            "facebook": f"https://facebook.com/search/?q={name}+{city}",
            "instagram": f"https://instagram.com/{name}",
            "linkedin": f"https://linkedin.com/company/{name}",
            "_found": False,
            "_note": "URLs are search suggestions — not verified",
        }
        lead["social_media"] = social
        return lead

    def enrich_reviews(self, lead: dict) -> dict:
        reviews = {
            "google_rating": None,
            "google_review_count": None,
            "yelp_rating": None,
            "_found": False,
            "_note": "Review data requires API enrichment — placeholders set",
        }
        lead["reviews"] = reviews
        return lead

    def enrich_business_info(self, lead: dict) -> dict:
        info = {
            "years_in_business": None,
            "business_hours": None,
            "service_area": str(lead.get("city", settings.outreach_city)),
            "_note": "Business details require external API — placeholders set",
        }
        lead["business_info"] = info
        return lead

    def enrich_contact_info(self, lead: dict) -> dict:
        contacts = []
        if lead.get("phone"):
            contacts.append({"type": "phone", "value": lead["phone"], "source": "lead_data"})
        if lead.get("email"):
            contacts.append({"type": "email", "value": lead["email"], "source": "lead_data"})
        lead["contacts"] = contacts
        return lead


class LeadValidator:
    """Validates lead quality."""

    def validate(self, lead: dict) -> dict:
        issues = []
        confidence = 100.0

        name = str(lead.get("name", "")).strip()
        if not name or len(name) < 2:
            issues.append("missing_or_short_name")
            confidence -= 40

        chain_keywords = ["walmart", "mcdonald", "starbucks", "subway", "7-eleven", "tim horton", "costco", "shoppers drug"]
        if any(kw in name.lower() for kw in chain_keywords):
            issues.append("likely_chain_business")
            confidence -= 30

        address = str(lead.get("address", "")).strip()
        if not address or len(address) < 5:
            issues.append("missing_address")
            confidence -= 20

        has_website = bool(lead.get("website_url") or lead.get("website"))
        if has_website:
            confidence -= 10

        valid = confidence >= 40
        return {
            "valid": valid,
            "confidence": max(0.0, confidence),
            "issues": issues,
            "lead_id": lead.get("id", ""),
        }

    def filter_valid(self, leads: list[dict]) -> list[dict]:
        return [l for l in leads if self.validate(l)["valid"]]

    def get_validation_stats(self, leads: list[dict]) -> dict:
        results = [self.validate(l) for l in leads]
        valid_count = sum(1 for r in results if r["valid"])
        reject_reasons: dict[str, int] = {}
        for r in results:
            for issue in r["issues"]:
                reject_reasons[issue] = reject_reasons.get(issue, 0) + 1
        return {
            "total": len(leads),
            "valid": valid_count,
            "invalid": len(leads) - valid_count,
            "valid_rate": round(valid_count / len(leads) * 100, 1) if leads else 0,
            "reject_reasons": reject_reasons,
        }


class IndustryClassifier:
    """Classifies leads into standardized industry categories."""

    def classify(self, lead: dict) -> dict:
        industry_raw = str(lead.get("industry", "")).lower().strip()
        name_raw = str(lead.get("name", "")).lower().strip()

        for category, keywords in INDUSTRY_CATEGORIES.items():
            for kw in keywords:
                if kw in industry_raw or kw in name_raw:
                    lead["industry_category"] = category
                    lead["industry_subcategory"] = kw
                    lead["classification_confidence"] = 0.9 if kw in industry_raw else 0.6
                    return lead

        lead["industry_category"] = "Other Services"
        lead["industry_subcategory"] = "general"
        lead["classification_confidence"] = 0.3
        return lead

    def classify_batch(self, leads: list[dict]) -> list[dict]:
        return [self.classify(lead) for lead in leads]

    @staticmethod
    def get_categories() -> dict:
        return INDUSTRY_CATEGORIES


class EnrichmentPipeline:
    """Runs all enrichment stages on leads."""

    def __init__(self):
        self.redis = get_redis()
        self.classifier = IndustryClassifier()
        self.validator = LeadValidator()
        self.enricher = DataEnricher()

    async def enrich(
        self, lead: dict, stages: Optional[list[str]] = None
    ) -> dict:
        if stages is None:
            stages = ["classify", "validate", "social", "reviews", "business", "contacts"]

        lead["_enrichment_stages"] = []

        for stage in stages:
            try:
                if stage == "classify":
                    self.classifier.classify(lead)
                elif stage == "validate":
                    lead["validation"] = self.validator.validate(lead)
                elif stage == "social":
                    self.enricher.enrich_social_media(lead)
                elif stage == "reviews":
                    self.enricher.enrich_reviews(lead)
                elif stage == "business":
                    self.enricher.enrich_business_info(lead)
                elif stage == "contacts":
                    self.enricher.enrich_contact_info(lead)
                lead["_enrichment_stages"].append(stage)
            except Exception as e:
                log.warning("enrich.stage_failed", stage=stage, error=str(e))

        lead["last_enriched"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return lead

    async def enrich_batch(
        self, leads: list[dict], stages: Optional[list[str]] = None
    ) -> list[dict]:
        enriched = []
        for lead in leads:
            enriched.append(await self.enrich(lead, stages))

        for lead in enriched:
            lead_id = lead.get("id", "")
            if lead_id:
                await self.redis.set(f"leads:enriched:{lead_id}", lead, ex=30 * 86400)

        log.info("enrich.batch_complete", count=len(enriched))
        return enriched

    async def get_enriched(self, lead_id: str) -> Optional[dict]:
        return await self.redis.get(f"leads:enriched:{lead_id}")
