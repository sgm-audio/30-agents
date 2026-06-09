"""
Discord webhook notification system for agent task completion/failure.
Sends formatted embed messages to Discord via incoming webhooks.
"""
import json
import time
from pathlib import Path
from typing import Optional

import httpx
import structlog

log = structlog.get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "discord_webhook.json"
GREEN = 3066993
RED = 15158332
ORANGE = 15105570


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"webhook_url": None, "enabled": False, "notify_on": ["complete", "error"]}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_webhook_url() -> Optional[str]:
    url = _load_config().get("webhook_url")
    if not url or "PASTE_YOUR" in str(url) or url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        return None
    return url


def is_enabled() -> bool:
    return _load_config().get("enabled", False)


def get_notify_on() -> list[str]:
    return _load_config().get("notify_on", ["complete", "error"])


async def send_discord(
    content: str,
    embed_title: str,
    embed_color: int,
    fields: list[dict],
    webhook_url: Optional[str] = None,
) -> bool:
    if not is_enabled() and not webhook_url:
        log.debug("discord.webhook_disabled")
        return False

    url = webhook_url or get_webhook_url()
    if not url:
        log.debug("discord.webhook_not_configured")
        return False

    payload = {
        "content": content,
        "embeds": [
            {
                "title": embed_title,
                "color": embed_color,
                "fields": [{"name": f["name"], "value": str(f["value"]), "inline": f.get("inline", False)} for f in fields],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 204):
                log.info("discord.notification_sent", title=embed_title)
                return True
            else:
                log.warning("discord.send_failed", status=resp.status_code, body=resp.text[:200])
                return False
    except Exception as e:
        log.error("discord.send_error", error=str(e))
        return False


async def notify_agent_complete(
    agent_name: str,
    task_summary: str,
    duration: str,
    result_summary: str,
    webhook_url: Optional[str] = None,
) -> bool:
    if "complete" not in get_notify_on():
        return False

    return await send_discord(
        content=f"Agent **{agent_name}** completed task: {task_summary}",
        embed_title="Task Complete",
        embed_color=GREEN,
        fields=[
            {"name": "Agent", "value": agent_name, "inline": True},
            {"name": "Task", "value": task_summary, "inline": False},
            {"name": "Duration", "value": duration, "inline": True},
            {"name": "Result", "value": result_summary, "inline": False},
        ],
        webhook_url=webhook_url,
    )


async def notify_agent_error(
    agent_name: str,
    task_summary: str,
    duration: str,
    error_message: str,
    webhook_url: Optional[str] = None,
) -> bool:
    if "error" not in get_notify_on():
        return False

    return await send_discord(
        content=f"Agent **{agent_name}** failed: {error_message[:100]}",
        embed_title="Task Failed",
        embed_color=RED,
        fields=[
            {"name": "Agent", "value": agent_name, "inline": True},
            {"name": "Task", "value": task_summary, "inline": False},
            {"name": "Duration", "value": duration, "inline": True},
            {"name": "Error", "value": error_message[:500], "inline": False},
        ],
        webhook_url=webhook_url,
    )


async def notify_pipeline_complete(
    pipeline_name: str,
    duration: str,
    stats: dict,
    webhook_url: Optional[str] = None,
) -> bool:
    if "complete" not in get_notify_on():
        return False

    fields = [{"name": k, "value": str(v), "inline": True} for k, v in stats.items()]
    return await send_discord(
        content=f"Pipeline **{pipeline_name}** completed",
        embed_title="Pipeline Complete",
        embed_color=GREEN,
        fields=[{"name": "Pipeline", "value": pipeline_name, "inline": True}, {"name": "Duration", "value": duration, "inline": True}] + fields,
        webhook_url=webhook_url,
    )


async def test_webhook(webhook_url: str) -> dict:
    success = await send_discord(
        content="Test message from 30-Agent System",
        embed_title="Webhook Test",
        embed_color=ORANGE,
        fields=[{"name": "Status", "value": "Configuration successful!", "inline": False}],
        webhook_url=webhook_url,
    )
    return {"success": success, "webhook_url": webhook_url}


def update_webhook_url(url: str):
    cfg = _load_config()
    cfg["webhook_url"] = url
    cfg["enabled"] = bool(url)
    _save_config(cfg)
    log.info("discord.webhook_updated", url=url[:30] + "..." if len(url) > 30 else url)


def set_notify_on(events: list[str]):
    cfg = _load_config()
    cfg["notify_on"] = [e for e in events if e in ("complete", "error")]
    _save_config(cfg)


def get_config() -> dict:
    cfg = _load_config()
    return {
        "webhook_url": cfg.get("webhook_url"),
        "enabled": cfg.get("enabled", False),
        "notify_on": cfg.get("notify_on", ["complete", "error"]),
        "daily_summary_time": cfg.get("daily_summary_time", "09:00"),
        "daily_summary_enabled": cfg.get("daily_summary_enabled", False),
        "alert_thresholds": cfg.get("alert_thresholds", {}),
        "health_check_interval_hours": cfg.get("health_check_interval_hours", 6),
        "config_path": str(CONFIG_PATH),
    }


# ── Daily / Weekly Summaries ──

async def send_daily_summary(webhook_url: Optional[str] = None) -> bool:
    """Send a daily summary embed with outreach, agent, and SEO stats."""
    url = webhook_url or get_webhook_url()
    if not url:
        return False

    try:
        from core.kpi_tracker import KPITracker
        kpi = KPITracker()
        leads = await kpi.get_current("leads_scraped_daily") or 0
        emails = await kpi.get_current("emails_sent_daily") or 0
        opens = await kpi.get_current("open_rate") or 0
        replies = await kpi.get_current("reply_rate") or 0
        agents = await kpi.get_current("agent_executions_daily") or 0
        errors = await kpi.get_current("agent_errors_rate") or 0
    except Exception:
        leads, emails, opens, replies, agents, errors = 0, 0, 0, 0, 0, 0

    return await send_discord(
        content="Daily Summary",
        embed_title="30-Agent Daily Summary",
        embed_color=3447003,
        fields=[
            {"name": "Outreach", "value": f"Leads: {leads} | Emails: {emails} | Open Rate: {opens}% | Reply Rate: {replies}%", "inline": False},
            {"name": "Agents", "value": f"Executions: {agents} | Error Rate: {errors}%", "inline": False},
            {"name": "Status", "value": "System operational", "inline": True},
        ],
        webhook_url=url,
    )


async def send_weekly_summary(webhook_url: Optional[str] = None) -> bool:
    """Send a weekly summary with trend arrows."""
    try:
        from core.report_generator import WeeklyDigest
        return await WeeklyDigest().send_to_discord(webhook_url)
    except Exception:
        url = webhook_url or get_webhook_url()
        if not url:
            return False
        return await send_discord(
            content="Weekly Summary",
            embed_title="30-Agent Weekly Summary",
            embed_color=10181046,
            fields=[{"name": "Note", "value": "Full report generation unavailable", "inline": False}],
            webhook_url=url,
        )


# ── Alert Manager ──

async def send_alert(title: str, message: str, severity: str = "info", webhook_url: Optional[str] = None) -> bool:
    color_map = {"info": 3447003, "warning": 15105570, "critical": 15158332}
    color = color_map.get(severity, 3447003)
    return await send_discord(
        content=f"[{severity.upper()}] {title}",
        embed_title=title,
        embed_color=color,
        fields=[
            {"name": "Severity", "value": severity.upper(), "inline": True},
            {"name": "Message", "value": message[:500], "inline": False},
        ],
        webhook_url=webhook_url,
    )


def get_alert_history(limit: int = 50) -> list[dict]:
    try:
        import asyncio
        from core.redis_client import get_redis
        redis = get_redis()

        async def _fetch():
            items = []
            for i in range(limit):
                entry = await redis.lindex("alerts:history", i)
                if entry:
                    items.append(entry)
            return items

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = concurrent.futures.Future()

            async def _run():
                result = await _fetch()
                future.set_result(result)

            loop.create_task(_run())
            return []
        return asyncio.run(_fetch())
    except Exception:
        return []


# ── Health Check Notifier ──

async def send_health_report(health_data: dict, webhook_url: Optional[str] = None) -> bool:
    all_ok = health_data.get("status") == "ok"
    color = 3066993 if all_ok else (15105570 if health_data.get("status") == "degraded" else 15158332)
    return await send_discord(
        content="System Health Report",
        embed_title="System Health",
        embed_color=color,
        fields=[
            {"name": "Status", "value": health_data.get("status", "unknown").upper(), "inline": True},
            {"name": "Ollama", "value": "Connected" if health_data.get("ollama") else "Disconnected", "inline": True},
            {"name": "Redis", "value": "Connected" if health_data.get("redis") else "Disconnected", "inline": True},
            {"name": "Agents", "value": str(health_data.get("agents_registered", "?")), "inline": True},
            {"name": "Models", "value": str(len(health_data.get("models", []))), "inline": True},
        ],
        webhook_url=webhook_url,
    )


# ── Pipeline Notifier ──

async def notify_pipeline_start(pipeline_type: str, details: dict, webhook_url: Optional[str] = None) -> bool:
    if "complete" not in get_notify_on():
        return False
    return await send_discord(
        content=f"Pipeline **{pipeline_type}** starting",
        embed_title=f"{pipeline_type} Pipeline Started",
        embed_color=3447003,
        fields=[{"name": k, "value": str(v)[:200], "inline": True} for k, v in details.items()],
        webhook_url=webhook_url,
    )


async def notify_pipeline_stage(pipeline_type: str, stage: str, status: str, webhook_url: Optional[str] = None) -> bool:
    if "complete" not in get_notify_on():
        return False
    color = 3066993 if status == "complete" else (15105570 if status == "running" else 15158332)
    return await send_discord(
        content=f"Pipeline {pipeline_type}: Stage **{stage}** {status}",
        embed_title=f"{pipeline_type} — {stage}",
        embed_color=color,
        fields=[
            {"name": "Pipeline", "value": pipeline_type, "inline": True},
            {"name": "Stage", "value": stage, "inline": True},
            {"name": "Status", "value": status, "inline": True},
        ],
        webhook_url=webhook_url,
    )