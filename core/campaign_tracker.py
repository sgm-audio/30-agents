"""
Campaign tracking: state machine, lead funnel, Resend webhook handler.
Provides CampaignTracker, LeadStateMachine, CampaignStats, and webhook handler.
"""
import time
import uuid
from typing import Any, Optional

import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

VALID_STATES = [
    "new", "scraped", "enriched", "email_generated",
    "email_sent", "opened", "replied", "qualified", "won", "lost",
    "bounced", "complained",
]

VALID_TRANSITIONS: dict[str, set[str]] = {
    "new": {"scraped"},
    "scraped": {"enriched", "lost"},
    "enriched": {"email_generated", "lost"},
    "email_generated": {"email_sent", "lost"},
    "email_sent": {"opened", "bounced", "complained"},
    "opened": {"replied"},
    "replied": {"qualified", "lost"},
    "qualified": {"won", "lost"},
    "bounced": {"lost"},
    "complained": {"lost"},
}


class CampaignTracker:
    """Manages outreach campaigns in Redis."""

    def __init__(self):
        self.redis = get_redis()

    async def create_campaign(
        self, name: str, city: str, max_leads: int = 50
    ) -> str:
        campaign_id = str(uuid.uuid4())
        meta = {
            "id": campaign_id,
            "name": name,
            "city": city,
            "max_leads": str(max_leads),
            "status": "active",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_leads": "0",
            "emails_sent": "0",
            "emails_opened": "0",
            "replies_received": "0",
            "conversions": "0",
        }
        await self.redis.hset(f"campaign:{campaign_id}:meta", meta)
        await self.redis.sadd("campaigns:all", campaign_id)
        log.info("campaign.created", campaign_id=campaign_id, name=name)
        return campaign_id

    async def update_campaign(self, campaign_id: str, **kwargs) -> bool:
        key = f"campaign:{campaign_id}:meta"
        if not await self.redis.exists(key):
            return False
        update = {k: str(v) for k, v in kwargs.items()}
        await self.redis.hset(key, update)
        return True

    async def get_campaign(self, campaign_id: str) -> Optional[dict]:
        return await self.redis.hgetall(f"campaign:{campaign_id}:meta")

    async def list_campaigns(self, status: Optional[str] = None) -> list[dict]:
        ids = await self.redis.smembers("campaigns:all")
        if not ids:
            return []
        campaigns = []
        for cid in ids:
            c = await self.redis.hgetall(f"campaign:{cid}:meta")
            if c and (status is None or c.get("status") == status):
                campaigns.append(c)
        return campaigns


class LeadStateMachine:
    """Tracks individual lead state transitions through the pipeline."""

    def __init__(self):
        self.redis = get_redis()

    async def transition(
        self,
        lead_id: str,
        campaign_id: str,
        new_state: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        if new_state not in VALID_STATES:
            log.warning("lead.invalid_state", state=new_state)
            return False

        current = await self.get_state(lead_id, campaign_id)

        if current and current["state"] not in VALID_TRANSITIONS:
            log.warning("lead.invalid_current", state=current["state"])
            return False
        if current and new_state not in VALID_TRANSITIONS.get(current["state"], set()):
            log.warning("lead.invalid_transition", from_state=current["state"], to_state=new_state)
            return False

        record = {
            "state": new_state,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": metadata or {},
        }
        history_key = f"campaign:{campaign_id}:lead:{lead_id}:history"
        await self.redis.lpush(history_key, record)
        await self.redis.expire(history_key, 90 * 86400)

        if current and current["state"]:
            await self.redis.srem(
                f"campaign:{campaign_id}:state:{current['state']}", lead_id
            )
        await self.redis.sadd(f"campaign:{campaign_id}:state:{new_state}", lead_id)

        count_key = f"campaign:{campaign_id}:meta"
        field_map = {
            "scraped": "total_leads",
            "email_sent": "emails_sent",
            "opened": "emails_opened",
            "replied": "replies_received",
            "won": "conversions",
        }
        if new_state in field_map:
            try:
                current_val = await self.redis.hget(count_key, field_map[new_state])
                new_val = int(current_val or 0) + 1
                await self.redis.hset(count_key, {field_map[new_state]: str(new_val)})
            except Exception:
                pass

        log.debug("lead.transition", lead_id=lead_id, to=new_state)
        return True

    async def get_state(self, lead_id: str, campaign_id: str) -> Optional[dict]:
        key = f"campaign:{campaign_id}:lead:{lead_id}:history"
        length = await self.redis.llen(key)
        if length == 0:
            return None
        latest = await self.redis.lindex(key, 0)
        if latest:
            latest["history_length"] = length
            return latest
        return None

    async def get_leads_by_state(self, campaign_id: str, state: str) -> list[str]:
        members = await self.redis.smembers(f"campaign:{campaign_id}:state:{state}")
        return list(members or [])


class CampaignStats:
    """Computes campaign funnel stats and aggregates."""

    def __init__(self):
        self.redis = get_redis()

    async def get_stats(self, campaign_id: str, use_cache: bool = True) -> dict:
        cache_key = f"campaign:{campaign_id}:stats_cache"
        if use_cache:
            cached = await self.redis.get(cache_key)
            if cached:
                return cached

        meta = await self.redis.hgetall(f"campaign:{campaign_id}:meta")
        if not meta:
            return {}

        scraped = int(meta.get("total_leads", 0))
        enriched = len(await self.redis.smembers(f"campaign:{campaign_id}:state:enriched") or [])
        emailed = int(meta.get("emails_sent", 0))
        opened = int(meta.get("emails_opened", 0))
        replied = int(meta.get("replies_received", 0))
        won = int(meta.get("conversions", 0))

        stats = {
            "campaign_id": campaign_id,
            "name": meta.get("name", ""),
            "status": meta.get("status", ""),
            "funnel": {
                "scraped": scraped,
                "enriched": enriched,
                "emailed": emailed,
                "opened": opened,
                "replied": replied,
                "qualified": len(await self.redis.smembers(f"campaign:{campaign_id}:state:qualified") or []),
                "won": won,
            },
            "rates": {
                "open_rate": round(opened / emailed * 100, 1) if emailed else 0,
                "reply_rate": round(replied / emailed * 100, 1) if emailed else 0,
                "conversion_rate": round(won / emailed * 100, 1) if emailed else 0,
                "bounce_rate": round(len(await self.redis.smembers(f"campaign:{campaign_id}:state:bounced") or []) / emailed * 100, 1) if emailed else 0,
            },
        }
        await self.redis.set(cache_key, stats, ex=300)
        return stats

    async def get_aggregate_stats(self, days: int = 30) -> dict:
        ids = await self.redis.smembers("campaigns:all")
        if not ids:
            return {"campaigns": 0, "aggregate": {}}

        all_stats = []
        for cid in ids:
            s = await self.get_stats(cid)
            if s:
                all_stats.append(s)

        total_scraped = sum(s["funnel"]["scraped"] for s in all_stats)
        total_emailed = sum(s["funnel"]["emailed"] for s in all_stats)
        total_opened = sum(s["funnel"]["opened"] for s in all_stats)
        total_replied = sum(s["funnel"]["replied"] for s in all_stats)
        total_won = sum(s["funnel"]["won"] for s in all_stats)

        return {
            "campaigns": len(all_stats),
            "aggregate": {
                "total_leads_scraped": total_scraped,
                "total_emails_sent": total_emailed,
                "total_opens": total_opened,
                "total_replies": total_replied,
                "total_conversions": total_won,
                "open_rate": round(total_opened / total_emailed * 100, 1) if total_emailed else 0,
                "reply_rate": round(total_replied / total_emailed * 100, 1) if total_emailed else 0,
                "conversion_rate": round(total_won / total_emailed * 100, 1) if total_emailed else 0,
            },
        }


async def handle_resend_webhook(event: dict) -> dict:
    """Process Resend webhook events and update lead state."""
    event_type = event.get("type", "")
    email_data = event.get("data", {})
    to_email = email_data.get("to", [None])[0] if isinstance(email_data.get("to"), list) else email_data.get("to", "")

    if not to_email:
        return {"status": "ignored", "reason": "no recipient email"}

    redis = get_redis()
    campaign_ids = await redis.smembers("campaigns:all")
    if not campaign_ids:
        return {"status": "ignored", "reason": "no campaigns"}

    machine = LeadStateMachine()

    for cid in campaign_ids:
        meta = await redis.hgetall(f"campaign:{cid}:meta")
        if not meta:
            continue
        sent_set = f"campaign:{cid}:state:email_sent"
        sent_leads = await redis.smembers(sent_set)
        if not sent_leads:
            continue

    state_map = {
        "email.sent": "email_sent",
        "email.opened": "opened",
        "email.clicked": "opened",
        "email.bounced": "bounced",
        "email.complained": "complained",
    }

    new_state = state_map.get(event_type)
    if not new_state:
        return {"status": "ignored", "reason": f"unhandled event type: {event_type}"}

    return {"status": "processed", "event": event_type, "state": new_state}


async def get_campaign_tracker() -> CampaignTracker:
    return CampaignTracker()


async def get_lead_state_machine() -> LeadStateMachine:
    return LeadStateMachine()


async def get_campaign_stats() -> CampaignStats:
    return CampaignStats()
