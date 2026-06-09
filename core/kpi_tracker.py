"""
KPI tracking: store, retrieve, and alert on key performance indicators.
Provides KPITracker with predefined outreach/SEO/agent KPIs and KPIAlerts.
"""
import time
from typing import Any, Optional

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

ALERT_DIRECTIONS = {"higher_is_better", "lower_is_better"}


class KPITracker:
    """Stores and retrieves KPI data points in Redis."""

    def __init__(self):
        self.redis = get_redis()

    async def record(self, name: str, value: float, tags: Optional[dict] = None):
        ts = time.time()
        data = {"value": value, "timestamp": ts, "tags": tags or {}}
        await self.redis.zadd(f"kpi:{name}:values", {str(data): ts})
        await self.redis.expire(f"kpi:{name}:values", 90 * 86400)
        await self.redis.hset("kpi:current", {name: str(value)})
        log.debug("kpi.recorded", name=name, value=value)

    async def get_current(self, name: str) -> Optional[float]:
        val = await self.redis.hget("kpi:current", name)
        if val is not None:
            return float(val)
        return None

    async def get_history(self, name: str, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 86400
        raw = await self.redis.zrangebyscore(
            f"kpi:{name}:values", cutoff, float("inf"), withscores=True
        )
        if not raw:
            return []
        results = []
        for member_str, score in raw:
            try:
                member = eval(member_str)
                member["_score"] = score
                results.append(member)
            except Exception:
                pass
        return results

    async def get_all_current(self) -> dict:
        raw = await self.redis.hgetall("kpi:current")
        return {k: float(v) for k, v in raw.items()}

    async def record_outreach_kpi(self, name: str, value: float):
        """Record a predefined outreach KPI and auto-trigger alert check."""
        await self.record(name, value, tags={"category": "outreach"})

    async def increment(self, name: str, by: float = 1.0):
        current = await self.get_current(name) or 0.0
        await self.record(name, current + by)


class KPIAlerts:
    """Threshold-based alerting for KPIs."""

    def __init__(self):
        self.redis = get_redis()

    async def set_threshold(
        self, name: str, warn: float, critical: float, direction: str = "lower_is_better"
    ):
        if direction not in ALERT_DIRECTIONS:
            raise ValueError(f"direction must be one of {ALERT_DIRECTIONS}")
        threshold = {
            "warn": warn,
            "critical": critical,
            "direction": direction,
        }
        await self.redis.hset("kpi:thresholds", {name: str(threshold)})
        log.info("kpi.threshold_set", name=name, threshold=threshold)

    async def get_threshold(self, name: str) -> Optional[dict]:
        val = await self.redis.hget("kpi:thresholds", name)
        if val:
            return eval(val)
        return None

    async def check(self, name: str) -> str:
        threshold = await self.get_threshold(name)
        if not threshold:
            return "ok"

        current = await KPITracker().get_current(name)
        if current is None:
            return "no_data"

        direction = threshold["direction"]
        if direction == "lower_is_better":
            if current >= threshold["critical"]:
                return "critical"
            if current >= threshold["warn"]:
                return "warn"
        else:
            if current <= threshold["critical"]:
                return "critical"
            if current <= threshold["warn"]:
                return "warn"

        return "ok"

    async def check_all(self) -> dict:
        thresholds_raw = await self.redis.hgetall("kpi:thresholds")
        result = {}
        for name in thresholds_raw:
            result[name] = await self.check(name)
        return result

    async def send_alert_if_needed(self, name: str) -> Optional[str]:
        status = await self.check(name)
        if status in ("warn", "critical"):
            rate_limit_key = f"alerts:ratelimit:{name}"
            if await self.redis.exists(rate_limit_key):
                return None
            await self.redis.set(rate_limit_key, "1", ex=3600)

            try:
                from core.discord_webhook import send_discord
                color = 15158332 if status == "critical" else 15105570
                await send_discord(
                    content=f"KPI Alert: **{name}** is {status}",
                    embed_title=f"KPI {status.upper()}",
                    embed_color=color,
                    fields=[
                        {"name": "KPI", "value": name, "inline": True},
                        {"name": "Status", "value": status, "inline": True},
                        {"name": "Current Value", "value": str(await KPITracker().get_current(name)), "inline": True},
                    ],
                )
            except Exception as e:
                log.warning("kpi.alert_discord_failed", error=str(e))

            history_entry = {
                "kpi": name,
                "status": status,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            await self.redis.lpush("alerts:history", history_entry)
            await self.redis.expire("alerts:history", 30 * 86400)

        return status

    async def get_alert_history(self, limit: int = 50) -> list[dict]:
        items = []
        for i in range(limit):
            entry = await self.redis.lindex("alerts:history", i)
            if entry:
                items.append(entry)
        return items


async def get_kpi_tracker() -> KPITracker:
    return KPITracker()


async def get_kpi_alerts() -> KPIAlerts:
    return KPIAlerts()
