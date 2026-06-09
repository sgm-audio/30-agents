"""Multica Autopilot Scheduler - Automated recurring task execution.

Provides cron-based scheduling for agent tasks with Redis persistence
and Discord webhook notifications.

Autopilot Configuration Schema:
{
    "id": "uuid",
    "name": "Human-readable name",
    "agent_name": "Agent to run (e.g., 'lead_scout')",
    "cron": "5-field cron expression",
    "timezone": "IANA timezone",
    "task_template": "Task description template",
    "inputs": {"key": "value"},
    "enabled": true,
    "webhook_url": "Discord webhook URL (optional)",
    "notify_on": ["success", "failure", "all"],
    "last_run": "ISO timestamp",
    "next_run": "ISO timestamp",
    "run_count": 0,
}

Redis Key Patterns:
- autopilot:<id> - Hash storing autopilot config
- autopilots:index - Set of all autopilot IDs
- autopilot:history:<id> - List of recent runs
"""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import redis.asyncio as redis
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AutopilotConfig:
    name: str
    agent_name: str
    cron: str
    task_template: str
    timezone: str = "UTC"
    inputs: dict = field(default_factory=dict)
    enabled: bool = True
    webhook_url: str | None = None
    notify_on: list[str] = field(default_factory=lambda: ["failure"])
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0
    retry_on_failure: bool = False
    max_retries: int = 1
    retry_delay_seconds: int = 300
    retry_count: int = 0


class AutopilotScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.redis: redis.Redis | None = None
        self._job_map: dict[str, str] = {}

    async def start(self):
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)
        await self._load_and_register_jobs()
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self.scheduler.start()
        logger.info("AutopilotScheduler started")

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        if self.redis:
            await self.redis.close()
        logger.info("AutopilotScheduler stopped")

    async def _load_and_register_jobs(self):
        index_key = "autopilots:index"
        autopilot_ids = await self.redis.smembers(index_key)
        for aid in autopilot_ids:
            config = await self._get_autopilot(aid)
            if config and config.enabled:
                await self._schedule_autopilot(config)

    async def _get_autopilot(self, autopilot_id: str) -> AutopilotConfig | None:
        key = f"autopilot:{autopilot_id}"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        return AutopilotConfig(
            id=data["id"],
            name=data["name"],
            agent_name=data["agent_name"],
            cron=data["cron"],
            task_template=data["task_template"],
            timezone=data.get("timezone", "UTC"),
            inputs=json.loads(data.get("inputs", "{}")),
            enabled=data.get("enabled", "true").lower() == "true",
            webhook_url=data.get("webhook_url"),
            notify_on=json.loads(data.get("notify_on", '["failure"]')),
            last_run=data.get("last_run"),
            next_run=data.get("next_run"),
            run_count=int(data.get("run_count", "0")),
            retry_on_failure=data.get("retry_on_failure", "false").lower() == "true",
            max_retries=int(data.get("max_retries", "1")),
            retry_delay_seconds=int(data.get("retry_delay_seconds", "300")),
            retry_count=int(data.get("retry_count", "0")),
        )

    async def _save_autopilot(self, config: AutopilotConfig):
        key = f"autopilot:{config.id}"
        await self.redis.hset(key, mapping={
            "id": config.id,
            "name": config.name,
            "agent_name": config.agent_name,
            "cron": config.cron,
            "task_template": config.task_template,
            "timezone": config.timezone,
            "inputs": json.dumps(config.inputs),
            "enabled": str(config.enabled).lower(),
            "webhook_url": config.webhook_url or "",
            "notify_on": json.dumps(config.notify_on),
            "last_run": config.last_run or "",
            "next_run": config.next_run or "",
            "run_count": str(config.run_count),
            "retry_on_failure": str(config.retry_on_failure).lower(),
            "max_retries": str(config.max_retries),
            "retry_delay_seconds": str(config.retry_delay_seconds),
            "retry_count": str(config.retry_count),
        })
        await self.redis.sadd("autopilots:index", config.id)

    async def _schedule_autopilot(self, config: AutopilotConfig):
        job_id = f"autopilot_{config.id}"

        trigger = CronTrigger.from_crontab(config.cron, timezone=config.timezone)

        self.scheduler.add_job(
            self._execute_autopilot,
            trigger=trigger,
            id=job_id,
            args=[config.id],
            replace_existing=True,
            name=config.name,
        )
        self._job_map[job_id] = config.id

        try:
            next_run = self.scheduler.get_job(job_id).next_run_time
            if next_run:
                config.next_run = next_run.isoformat()
                await self._save_autopilot(config)
        except Exception:
            pass

        logger.info(f"Scheduled autopilot '{config.name}' with cron '{config.cron}'")

    async def create_autopilot(
        self,
        name: str,
        agent_name: str,
        cron: str,
        task_template: str,
        timezone: str = "UTC",
        inputs: dict | None = None,
        webhook_url: str | None = None,
        notify_on: list[str] | None = None,
    ) -> AutopilotConfig:
        config = AutopilotConfig(
            name=name,
            agent_name=agent_name,
            cron=cron,
            task_template=task_template,
            timezone=timezone,
            inputs=inputs or {},
            webhook_url=webhook_url,
            notify_on=notify_on or ["failure"],
        )
        await self._save_autopilot(config)
        await self._schedule_autopilot(config)
        return config

    async def delete_autopilot(self, autopilot_id: str):
        job_id = f"autopilot_{autopilot_id}"
        if job_id in self._job_map:
            self.scheduler.remove_job(job_id)
            del self._job_map[job_id]
        await self.redis.delete(f"autopilot:{autopilot_id}")
        await self.redis.srem("autopilots:index", autopilot_id)
        logger.info(f"Deleted autopilot {autopilot_id}")

    async def list_autopilots(self) -> list[AutopilotConfig]:
        autopilot_ids = await self.redis.smembers("autopilots:index")
        configs = []
        for aid in autopilot_ids:
            config = await self._get_autopilot(aid)
            if config:
                configs.append(config)
        return configs

    async def get_autopilot(self, autopilot_id: str) -> AutopilotConfig | None:
        return await self._get_autopilot(autopilot_id)

    async def toggle_autopilot(self, autopilot_id: str, enabled: bool) -> AutopilotConfig | None:
        config = await self._get_autopilot(autopilot_id)
        if not config:
            return None
        config.enabled = enabled
        await self._save_autopilot(config)

        job_id = f"autopilot_{autopilot_id}"
        if enabled:
            await self._schedule_autopilot(config)
        else:
            if job_id in self._job_map:
                self.scheduler.remove_job(job_id)
                del self._job_map[job_id]
        return config

    async def _execute_autopilot(self, autopilot_id: str):
        config = await self._get_autopilot(autopilot_id)
        if not config or not config.enabled:
            return

        start_time = datetime.now(timezone.utc)
        success = False
        error_message = None
        result = None

        try:
            logger.info(f"Executing autopilot '{config.name}' ({autopilot_id})")

            from core.graph import get_graph
            from agents.registry import register_all_agents

            register_all_agents()
            graph = get_graph()

            task = config.task_template.format(**config.inputs) if config.inputs else config.task_template

            state = await graph.run(task=task, session_id=f"autopilot_{autopilot_id}")

            result = state.get("result") or state.get("error") or "Completed"
            success = "error" not in state
            logger.info(f"Autopilot '{config.name}' completed: success={success}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"Autopilot '{config.name}' failed: {e}")

            if config.retry_on_failure and config.retry_count < config.max_retries:
                config.retry_count += 1
                await self._save_autopilot(config)
                delay = config.retry_delay_seconds
                logger.info(f"Autopilot '{config.name}' retry {config.retry_count}/{config.max_retries} in {delay}s")
                await asyncio.sleep(delay)
                await self._execute_autopilot(autopilot_id)
                return

        finally:
            end_time = datetime.now(timezone.utc)
            config.last_run = start_time.isoformat()
            config.run_count += 1
            if success:
                config.retry_count = 0

            job_id = f"autopilot_{autopilot_id}"
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                config.next_run = job.next_run_time.isoformat()

            await self._save_autopilot(config)
            await self._record_run(autopilot_id, start_time, end_time, success, result, error_message)

            if config.webhook_url:
                await self._send_webhook(config, success, result, error_message, start_time)

    async def _record_run(
        self,
        autopilot_id: str,
        start: datetime,
        end: datetime,
        success: bool,
        result: str | None,
        error: str | None,
    ):
        history_key = f"autopilot:history:{autopilot_id}"
        run_record = json.dumps({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "success": success,
            "result": result,
            "error": error,
        })
        await self.redis.lpush(history_key, run_record)
        await self.redis.ltrim(history_key, 0, 99)

    async def _send_webhook(
        self,
        config: AutopilotConfig,
        success: bool,
        result: str | None,
        error: str | None,
        run_time: datetime,
    ):
        should_notify = (
            ("all" in config.notify_on) or
            ("success" in config.notify_on and success) or
            ("failure" in config.notify_on and not success)
        )
        if not should_notify or not config.webhook_url:
            return

        try:
            from core.discord_webhook import send_discord
            color = 3066993 if success else 15158332
            status_text = "Succeeded" if success else "Failed"
            fields = [
                {"name": "Status", "value": status_text, "inline": True},
                {"name": "Agent", "value": config.agent_name, "inline": True},
                {"name": "Run", "value": f"#{config.run_count}", "inline": True},
                {"name": "Time", "value": run_time.strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": False},
            ]
            if result:
                fields.append({"name": "Result", "value": str(result)[:500], "inline": False})
            if error:
                fields.append({"name": "Error", "value": str(error)[:500], "inline": False})
            await send_discord(
                content="",
                embed_title=f"Autopilot: {config.name}",
                embed_color=color,
                fields=fields,
                webhook_url=config.webhook_url,
            )
        except Exception as e:
            logger.warning(f"Failed to send Discord webhook: {e}")

    # ── Template Methods ──

    async def create_lead_scrape_autopilot(
        self, city: str = "Vancouver", max_leads: int = 50, notify: bool = True
    ) -> AutopilotConfig:
        """Create a pre-configured daily lead scrape autopilot."""
        webhook_url = None
        if notify:
            from core.discord_webhook import get_webhook_url
            webhook_url = get_webhook_url()
        return await self.create_autopilot(
            name=f"Daily Lead Scrape — {city}",
            agent_name="lead_scout",
            cron="0 8 * * *",
            task_template=f"Find {city} businesses without websites",
            timezone="America/Vancouver",
            inputs={"city": city, "max_leads": str(max_leads)},
            webhook_url=webhook_url,
            notify_on=["failure"] if notify else [],
        )

    async def create_seo_audit_autopilot(
        self, url: str, keyword: str = "", notify: bool = True
    ) -> AutopilotConfig:
        """Create a pre-configured weekly SEO audit autopilot."""
        webhook_url = None
        if notify:
            from core.discord_webhook import get_webhook_url
            webhook_url = get_webhook_url()
        return await self.create_autopilot(
            name=f"Weekly SEO Audit — {url}",
            agent_name="web_researcher",
            cron="0 9 * * 1",
            task_template=f"Run full SEO audit for {url}" + (f" targeting keyword {keyword}" if keyword else ""),
            timezone="America/Vancouver",
            inputs={"url": url, "keyword": keyword},
            webhook_url=webhook_url,
            notify_on=["failure"] if notify else [],
        )

    async def create_report_autopilot(
        self, report_type: str = "weekly", notify: bool = True
    ) -> AutopilotConfig:
        """Create a pre-configured report generation autopilot."""
        webhook_url = None
        if notify:
            from core.discord_webhook import get_webhook_url
            webhook_url = get_webhook_url()
        if report_type == "weekly":
            cron = "0 9 * * 1"
            name = "Weekly Summary Report"
            task = "Generate weekly outreach and SEO summary report"
        else:
            cron = "0 9 1 * *"
            name = "Monthly Summary Report"
            task = "Generate monthly outreach and SEO summary report"
        return await self.create_autopilot(
            name=name,
            agent_name="summarizer",
            cron=cron,
            task_template=task,
            timezone="America/Vancouver",
            inputs={"report_type": report_type},
            webhook_url=webhook_url,
            notify_on=["failure"] if notify else [],
        )

    # ── Group Support ──

    async def create_group(self, name: str, autopilot_ids: list[str]) -> str:
        """Create a group of autopilots that run together."""
        group_id = str(uuid.uuid4())
        group_data = {
            "id": group_id,
            "name": name,
            "autopilot_ids": json.dumps(autopilot_ids),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.hset(f"autopilot:group:{group_id}", mapping=group_data)
        await self.redis.sadd("autopilots:groups", group_id)
        logger.info(f"Created autopilot group '{name}' with {len(autopilot_ids)} autopilots")
        return group_id

    async def get_group(self, group_id: str) -> dict | None:
        data = await self.redis.hgetall(f"autopilot:group:{group_id}")
        if not data:
            return None
        data["autopilot_ids"] = json.loads(data.get("autopilot_ids", "[]"))
        return data

    async def list_groups(self) -> list[dict]:
        ids = await self.redis.smembers("autopilots:groups")
        groups = []
        for gid in ids:
            g = await self.get_group(gid)
            if g:
                groups.append(g)
        return groups

    async def run_group(self, group_id: str) -> dict:
        """Execute all autopilots in a group sequentially."""
        group = await self.get_group(group_id)
        if not group:
            return {"error": "group not found", "group_id": group_id}
        results = []
        for aid in group.get("autopilot_ids", []):
            try:
                await self._execute_autopilot(aid)
                results.append({"id": aid, "status": "triggered"})
            except Exception as e:
                results.append({"id": aid, "status": "failed", "error": str(e)})
        return {"group": group["name"], "results": results}

    def _job_listener(self, event):
        if event.exception:
            logger.error(f"Autopilot job {event.job_id} failed: {event.exception}")


_scheduler: AutopilotScheduler | None = None


def get_autopilot_scheduler() -> AutopilotScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AutopilotScheduler()
    return _scheduler