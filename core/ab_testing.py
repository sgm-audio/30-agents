"""
A/B testing framework for email subject lines and body templates.
Provides ABTest, VariantAssigner, ResultsTracker, and ABAnalyzer.
"""
import hashlib
import math
import random
import time
import uuid
from typing import Any, Optional

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

MIN_SENDS_PER_VARIANT = 30


class ABTest:
    """Creates and manages A/B test configurations."""

    def __init__(self):
        self.redis = get_redis()

    async def create_test(
        self, name: str, campaign_id: str, variants: list[dict]
    ) -> str:
        test_id = str(uuid.uuid4())
        config = {
            "id": test_id,
            "name": name,
            "campaign_id": campaign_id,
            "status": "active",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "variants": variants,
        }
        await self.redis.set(f"abtest:{test_id}:config", config)
        await self.redis.sadd("abtests:all", test_id)
        await self.redis.sadd(f"abtest:campaign:{campaign_id}", test_id)
        log.info("abtest.created", test_id=test_id, name=name)
        return test_id

    async def get_test(self, test_id: str) -> Optional[dict]:
        return await self.redis.get(f"abtest:{test_id}:config")

    async def list_tests(self, campaign_id: Optional[str] = None) -> list[dict]:
        if campaign_id:
            ids = await self.redis.smembers(f"abtest:campaign:{campaign_id}")
        else:
            ids = await self.redis.smembers("abtests:all")
        if not ids:
            return []
        results = []
        for tid in ids:
            cfg = await self.redis.get(f"abtest:{tid}:config")
            if cfg:
                results.append(cfg)
        return results


class VariantAssigner:
    """Assigns leads to test variants deterministically."""

    def __init__(self):
        self.redis = get_redis()

    def assign(self, lead_id: str, test_id: str, variants: list[str], weights: Optional[list[float]] = None) -> str:
        assignment_key = f"abtest:{test_id}:assignments"
        hash_val = int(hashlib.md5(f"{test_id}:{lead_id}".encode()).hexdigest(), 16)

        if not weights:
            weights = [1.0 / len(variants)] * len(variants)

        total = sum(weights)
        normalized = [w / total for w in weights]

        roll = (hash_val % 10000) / 10000.0
        cumulative = 0.0
        for i, prob in enumerate(normalized):
            cumulative += prob
            if roll <= cumulative:
                return variants[i]

        return variants[-1]

    async def assign_and_store(self, lead_id: str, test_id: str, variants: list[str], weights: Optional[list[float]] = None) -> str:
        variant = self.assign(lead_id, test_id, variants, weights)
        await self.redis.hset(f"abtest:{test_id}:assignments", {lead_id: variant})
        await self.redis.expire(f"abtest:{test_id}:assignments", 90 * 86400)
        return variant

    async def get_assignment(self, lead_id: str, test_id: str) -> Optional[str]:
        return await self.redis.hget(f"abtest:{test_id}:assignments", lead_id)


class ResultsTracker:
    """Records A/B test events (send, open, reply, bounce)."""

    def __init__(self):
        self.redis = get_redis()

    async def record_send(self, lead_id: str, test_id: str, variant: Optional[str] = None):
        if not variant:
            variant = await self.redis.hget(f"abtest:{test_id}:assignments", lead_id) or "unknown"
        stats_key = f"abtest:{test_id}:stats:{variant}"
        await self.redis.hincrby(stats_key, "sends", 1)
        await self.redis.expire(stats_key, 90 * 86400)
        log.debug("abtest.record_send", test_id=test_id, variant=variant)

    async def record_open(self, lead_id: str, test_id: str):
        variant = await self.redis.hget(f"abtest:{test_id}:assignments", lead_id)
        if not variant:
            return
        stats_key = f"abtest:{test_id}:stats:{variant}"
        await self.redis.hincrby(stats_key, "opens", 1)
        await self.redis.expire(stats_key, 90 * 86400)

    async def record_reply(self, lead_id: str, test_id: str):
        variant = await self.redis.hget(f"abtest:{test_id}:assignments", lead_id)
        if not variant:
            return
        stats_key = f"abtest:{test_id}:stats:{variant}"
        await self.redis.hincrby(stats_key, "replies", 1)
        await self.redis.expire(stats_key, 90 * 86400)

    async def record_bounce(self, lead_id: str, test_id: str):
        variant = await self.redis.hget(f"abtest:{test_id}:assignments", lead_id)
        if not variant:
            return
        stats_key = f"abtest:{test_id}:stats:{variant}"
        await self.redis.hincrby(stats_key, "bounces", 1)
        await self.redis.expire(stats_key, 90 * 86400)


class ABAnalyzer:
    """Analyzes A/B test results with statistical significance."""

    def __init__(self):
        self.redis = get_redis()

    def _chi_squared_pvalue(self, observed: list[list[float]]) -> float:
        """Simple chi-squared test for independence. Returns approximate p-value."""
        rows = len(observed)
        cols = len(observed[0])
        row_totals = [sum(row) for row in observed]
        col_totals = [sum(observed[r][c] for r in range(rows)) for c in range(cols)]
        total = sum(row_totals)

        chi2 = 0.0
        for r in range(rows):
            for c in range(cols):
                expected = row_totals[r] * col_totals[c] / total if total else 1
                diff = observed[r][c] - expected
                chi2 += (diff * diff) / expected if expected else 0

        df = (rows - 1) * (cols - 1)
        if df < 1:
            return 1.0

        m = chi2 / 2.0
        term = 1.0
        s = term
        for i in range(1, 100):
            term *= m / i
            s += term
            if term < 1e-10:
                break
        p = 1.0 - math.exp(-m) * s
        return max(0.0, min(1.0, p))

    async def get_results(self, test_id: str) -> dict:
        config = await self.redis.get(f"abtest:{test_id}:config")
        if not config:
            return {"error": "test not found"}

        variants = config.get("variants", [])
        results = {}
        for v in variants:
            vname = v.get("name", "unknown")
            stats = await self.redis.hgetall(f"abtest:{test_id}:stats:{vname}") or {}
            sends = int(stats.get("sends", 0))
            opens = int(stats.get("opens", 0))
            replies = int(stats.get("replies", 0))
            bounces = int(stats.get("bounces", 0))
            results[vname] = {
                "sends": sends,
                "opens": opens,
                "replies": replies,
                "bounces": bounces,
                "open_rate": round(opens / sends * 100, 1) if sends else 0,
                "reply_rate": round(replies / sends * 100, 1) if sends else 0,
                "bounce_rate": round(bounces / sends * 100, 1) if sends else 0,
            }

        sufficient_data = all(r["sends"] >= MIN_SENDS_PER_VARIANT for r in results.values())

        return {
            "test_id": test_id,
            "name": config.get("name"),
            "status": config.get("status"),
            "sufficient_data": sufficient_data,
            "min_sends_required": MIN_SENDS_PER_VARIANT,
            "variants": results,
        }

    async def get_winner(self, test_id: str) -> dict:
        results_data = await self.get_results(test_id)
        if "error" in results_data:
            return results_data

        variants = results_data.get("variants", {})
        if not variants:
            return {"error": "no variant data"}

        best_variant = None
        best_rate = -1.0
        for name, data in variants.items():
            rate = data.get("reply_rate", 0)
            if rate > best_rate:
                best_rate = rate
                best_variant = name

        if not results_data.get("sufficient_data"):
            return {
                "test_id": test_id,
                "status": "insufficient_data",
                "message": f"Need at least {MIN_SENDS_PER_VARIANT} sends per variant",
                "current_leader": best_variant,
                "variants": variants,
            }

        variant_names = list(variants.keys())
        if len(variant_names) >= 2:
            v1_data = variants[variant_names[0]]
            v2_data = variants[variant_names[1]]
            observed = [
                [v1_data["replies"], v1_data["sends"] - v1_data["replies"]],
                [v2_data["replies"], v2_data["sends"] - v2_data["replies"]],
            ]
            p_value = self._chi_squared_pvalue(observed)
            significant = p_value < 0.05
        else:
            p_value = 1.0
            significant = False

        return {
            "test_id": test_id,
            "winner": best_variant,
            "confidence": round((1.0 - p_value) * 100, 1),
            "statistically_significant": significant,
            "variants": variants,
        }

    async def is_significant(self, test_id: str) -> bool:
        winner = await self.get_winner(test_id)
        return winner.get("statistically_significant", False)
