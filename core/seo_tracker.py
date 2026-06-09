"""
SEO tracking: audit history, change detection, competitor monitoring, and report generation.
"""
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)


def _extract_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc or parsed.path.split("/")[0]


class SEOAuditStore:
    """Stores and retrieves SEO audit snapshots."""

    def __init__(self):
        self.redis = get_redis()

    async def save_audit(self, url: str, audit_data: dict) -> str:
        audit_id = str(uuid.uuid4())
        domain = _extract_domain(url)
        record = {
            "id": audit_id,
            "url": url,
            "domain": domain,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": audit_data,
        }
        await self.redis.set(f"seo:audit:{audit_id}", record, ex=90 * 86400)
        score = await self.redis.zadd(
            f"seo:audits:{domain}",
            {audit_id: time.time()},
        )
        await self.redis.expire(f"seo:audits:{domain}", 90 * 86400)
        overall = self._extract_score(audit_data)
        await self.redis.zadd(
            f"seo:scores:{domain}",
            {f"{audit_id}:{overall}": time.time()},
        )
        await self.redis.expire(f"seo:scores:{domain}", 90 * 86400)
        log.info("seo.audit_saved", audit_id=audit_id, domain=domain)
        return audit_id

    def _extract_score(self, audit_data: dict) -> float:
        scores = []
        for key in ("on_page", "technical", "content"):
            section = audit_data.get(key, {})
            s = section.get("score") or section.get("overall_score") or 0
            if isinstance(s, (int, float)):
                scores.append(float(s))
        if not scores:
            return 50.0
        return sum(scores) / len(scores)

    async def get_audit(self, audit_id: str) -> Optional[dict]:
        return await self.redis.get(f"seo:audit:{audit_id}")

    async def get_latest(self, domain: str) -> Optional[dict]:
        results = await self.redis.zrevrange(f"seo:audits:{domain}", 0, 0)
        if not results:
            return None
        return await self.redis.get(f"seo:audit:{results[0]}")

    async def list_audits(self, domain: str, limit: int = 10) -> list[dict]:
        results = await self.redis.zrevrange(f"seo:audits:{domain}", 0, limit - 1)
        if not results:
            return []
        audits = []
        for aid in results:
            a = await self.redis.get(f"seo:audit:{aid}")
            if a:
                audits.append(a)
        return audits


class SEOChangeTracker:
    """Compares SEO audits to detect changes and trends."""

    def __init__(self):
        self.redis = get_redis()
        self.store = SEOAuditStore()

    async def compare(self, domain: str, audit_id_1: str, audit_id_2: str) -> dict:
        a1 = await self.redis.get(f"seo:audit:{audit_id_1}")
        a2 = await self.redis.get(f"seo:audit:{audit_id_2}")
        if not a1 or not a2:
            return {"error": "one or both audits not found"}

        s1 = self.store._extract_score(a1["data"])
        s2 = self.store._extract_score(a2["data"])
        score_delta = round(s2 - s1, 1)

        trend = "stable"
        if score_delta > 2:
            trend = "improving"
        elif score_delta < -2:
            trend = "declining"

        return {
            "domain": domain,
            "audit_1": {"id": audit_id_1, "timestamp": a1.get("timestamp"), "score": s1},
            "audit_2": {"id": audit_id_2, "timestamp": a2.get("timestamp"), "score": s2},
            "score_delta": score_delta,
            "trend": trend,
        }

    async def get_score_trend(self, domain: str, days: int = 90) -> dict:
        cutoff = time.time() - days * 86400
        raw = await self.redis.zrangebyscore(f"seo:scores:{domain}", cutoff, float("inf"), withscores=True)
        if not raw:
            return {"domain": domain, "data_points": [], "trend": "no_data"}
        points = []
        for member, score_val in raw:
            aid, _, score_str = member.partition(":")
            points.append({
                "audit_id": aid,
                "score": float(score_str) if score_str else score_val,
                "timestamp": score_val,
            })
        scores = [p["score"] for p in points]
        trend = "stable"
        if len(scores) >= 2:
            if scores[-1] > scores[0] + 2:
                trend = "improving"
            elif scores[-1] < scores[0] - 2:
                trend = "declining"
        return {
            "domain": domain,
            "data_points": points,
            "current_score": scores[-1] if scores else 0,
            "trend": trend,
            "first_score": scores[0] if scores else 0,
            "score_delta": round(scores[-1] - scores[0], 1) if len(scores) >= 2 else 0,
        }


class CompetitorMonitor:
    """Tracks and compares competitors."""

    def __init__(self):
        self.redis = get_redis()

    async def add_competitor(self, domain: str, competitor_url: str, label: Optional[str] = None):
        comp_domain = _extract_domain(competitor_url)
        entry = {"url": competitor_url, "domain": comp_domain, "label": label or comp_domain}
        await self.redis.set(
            f"seo:competitor:{domain}:{comp_domain}",
            entry,
            ex=365 * 86400,
        )
        await self.redis.sadd(f"seo:competitors:{domain}", comp_domain)
        log.info("seo.competitor_added", domain=domain, competitor=comp_domain)

    async def get_competitors(self, domain: str) -> list[dict]:
        comp_domains = await self.redis.smembers(f"seo:competitors:{domain}")
        if not comp_domains:
            return []
        result = []
        for cd in comp_domains:
            entry = await self.redis.get(f"seo:competitor:{domain}:{cd}")
            if entry:
                result.append(entry)
        return result

    async def compare_competitors(self, domain: str) -> dict:
        my_latest = await SEOAuditStore().get_latest(domain)
        my_score = SEOAuditStore()._extract_score(my_latest["data"]) if my_latest else 0

        competitors = await self.get_competitors(domain)
        comp_scores = []
        for comp in competitors:
            comp_latest = await SEOAuditStore().get_latest(comp["domain"])
            if comp_latest:
                comp_scores.append({
                    "domain": comp["domain"],
                    "label": comp.get("label", comp["domain"]),
                    "score": SEOAuditStore()._extract_score(comp_latest["data"]),
                })

        comp_scores.sort(key=lambda c: c["score"], reverse=True)
        rank = sum(1 for c in comp_scores if c["score"] > my_score) + 1

        return {
            "domain": domain,
            "your_score": my_score,
            "rank": rank,
            "total_compared": len(comp_scores),
            "competitors": comp_scores,
            "ahead_by": round(comp_scores[0]["score"] - my_score, 1) if comp_scores and my_score > 0 else 0,
        }


class SEOReportGenerator:
    """Generates weekly and monthly SEO summary reports."""

    def __init__(self):
        self.redis = get_redis()
        self.store = SEOAuditStore()
        self.tracker = SEOChangeTracker()

    async def generate_weekly(self, domains: Optional[list[str]] = None) -> dict:
        if not domains:
            domains = await self._discover_domains()

        summary = []
        for domain in domains:
            trend_data = await self.tracker.get_score_trend(domain, days=7)
            latest = await self.store.get_latest(domain)
            score = self.store._extract_score(latest["data"]) if latest else 0
            summary.append({
                "domain": domain,
                "current_score": round(score, 1),
                "trend": trend_data.get("trend", "unknown"),
                "audits_this_week": len(trend_data.get("data_points", [])),
            })

        report = {
            "type": "weekly",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "domains_tracked": len(summary),
            "average_score": round(sum(d["current_score"] for d in summary) / len(summary), 1) if summary else 0,
            "improving": sum(1 for d in summary if d["trend"] == "improving"),
            "declining": sum(1 for d in summary if d["trend"] == "declining"),
            "stable": sum(1 for d in summary if d["trend"] == "stable"),
            "domains": summary,
        }
        await self.redis.set(
            f"reports:seo:weekly:{time.strftime('%Y-%m-%d', time.gmtime())}",
            report,
            ex=30 * 86400,
        )
        return report

    async def generate_monthly(self, domains: Optional[list[str]] = None) -> dict:
        if not domains:
            domains = await self._discover_domains()

        summary = []
        for domain in domains:
            trend_data = await self.tracker.get_score_trend(domain, days=30)
            latest = await self.store.get_latest(domain)
            score = self.store._extract_score(latest["data"]) if latest else 0
            summary.append({
                "domain": domain,
                "current_score": round(score, 1),
                "score_delta": trend_data.get("score_delta", 0),
                "trend": trend_data.get("trend", "unknown"),
            })

        report = {
            "type": "monthly",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "domains_tracked": len(summary),
            "average_score": round(sum(d["current_score"] for d in summary) / len(summary), 1) if summary else 0,
            "average_delta": round(sum(d["score_delta"] for d in summary) / len(summary), 1) if summary else 0,
            "improving": sum(1 for d in summary if d["trend"] == "improving"),
            "declining": sum(1 for d in summary if d["trend"] == "declining"),
            "stable": sum(1 for d in summary if d["trend"] == "stable"),
            "domains": summary,
        }
        await self.redis.set(
            f"reports:seo:monthly:{time.strftime('%Y-%m', time.gmtime())}",
            report,
            ex=90 * 86400,
        )
        return report

    async def _discover_domains(self) -> list[str]:
        domains = set()
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match="seo:audits:*", count=100)
            for key in keys:
                parts = key.split(":")
                if len(parts) == 3:
                    domains.add(parts[2])
            if cursor == 0:
                break
        return list(domains)
