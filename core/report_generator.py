"""
Report generation: weekly digest, monthly report, agent cost report.
Generates structured reports for Discord and API consumption.
"""
import time
from typing import Any, Optional
import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)


class ReportGenerator:
    """Base report generator with format support."""

    def _format_output(self, data: dict, fmt: str = "json") -> Any:
        if fmt == "json":
            return data
        if fmt == "markdown":
            return self._to_markdown(data)
        return data

    def _to_markdown(self, data: dict) -> str:
        lines = [f"# {data.get('title', 'Report')}", "", f"Generated: {data.get('generated_at', '')}", ""]
        for section in data.get("sections", []):
            lines.append(f"## {section['title']}")
            for item in section.get("items", []):
                lines.append(f"- **{item['label']}**: {item['value']}")
            lines.append("")
        return "\n".join(lines)

    def _to_discord_embed(self, data: dict) -> list[dict]:
        embeds = []
        for section in data.get("sections", []):
            fields = [{"name": item["label"], "value": str(item["value"]), "inline": item.get("inline", True)} for item in section.get("items", [])]
            embeds.append({
                "title": section.get("title", ""),
                "color": section.get("color", 3066993),
                "fields": fields[:25],
            })
        return embeds


class WeeklyDigest(ReportGenerator):
    """Generates a weekly summary digest."""

    def __init__(self):
        self.redis = get_redis()

    async def generate(self, days: int = 7) -> dict:
        sections = []
        outreach = await self._outreach_section()
        if outreach:
            sections.append(outreach)
        seo_sec = await self._seo_section()
        if seo_sec:
            sections.append(seo_sec)
        agent_sec = await self._agent_section()
        if agent_sec:
            sections.append(agent_sec)
        health = await self._health_section()
        if health:
            sections.append(health)

        report = {
            "title": "Weekly Digest",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "period_days": days,
            "sections": sections,
        }
        date_key = time.strftime("%Y-%m-%d", time.gmtime())
        await self.redis.set(f"reports:weekly:{date_key}", report, ex=30 * 86400)
        await self.redis.sadd("reports:weekly:index", date_key)
        return report

    async def _outreach_section(self) -> Optional[dict]:
        try:
            cids = await self.redis.smembers("campaigns:all") or []
            total_scraped, total_sent, total_opened, total_replied, total_won = 0, 0, 0, 0, 0
            for cid in cids:
                meta = await self.redis.hgetall(f"campaign:{cid}:meta")
                if meta:
                    total_scraped += int(meta.get("total_leads", 0) or 0)
                    total_sent += int(meta.get("emails_sent", 0) or 0)
                    total_opened += int(meta.get("emails_opened", 0) or 0)
                    total_replied += int(meta.get("replies_received", 0) or 0)
                    total_won += int(meta.get("conversions", 0) or 0)
            open_rate = round(total_opened / total_sent * 100, 1) if total_sent else 0
            reply_rate = round(total_replied / total_sent * 100, 1) if total_sent else 0
            conv_rate = round(total_won / total_sent * 100, 1) if total_sent else 0
            return {
                "title": "Outreach",
                "color": 3447003,
                "items": [
                    {"label": "Leads Scraped", "value": str(total_scraped), "inline": True},
                    {"label": "Emails Sent", "value": str(total_sent), "inline": True},
                    {"label": "Opens", "value": str(total_opened), "inline": True},
                    {"label": "Replies", "value": str(total_replied), "inline": True},
                    {"label": "Conversions", "value": str(total_won), "inline": True},
                    {"label": "Open Rate", "value": f"{open_rate}%", "inline": True},
                    {"label": "Reply Rate", "value": f"{reply_rate}%", "inline": True},
                    {"label": "Conversion Rate", "value": f"{conv_rate}%", "inline": True},
                ],
            }
        except Exception as e:
            log.warning("weekly.outreach_failed", error=str(e))
            return None

    async def _seo_section(self) -> Optional[dict]:
        try:
            kpi = KPITracker()
            score = await kpi.get_current("seo_score_avg")
            return {
                "title": "SEO",
                "color": 10181046,
                "items": [
                    {"label": "Avg Score", "value": f"{score}" if score else "N/A", "inline": True},
                    {"label": "Audits This Week", "value": str(await kpi.get_current("seo_audits_weekly") or "N/A"), "inline": True},
                ],
            }
        except Exception:
            return None

    async def _agent_section(self) -> Optional[dict]:
        try:
            kpi = KPITracker()
            total = await kpi.get_current("agent_executions_total") or 0
            daily = await kpi.get_current("agent_executions_daily") or 0
            errors = await kpi.get_current("agent_errors_rate") or 0
            return {
                "title": "Agents",
                "color": 15844367,
                "items": [
                    {"label": "Total Executions", "value": str(total), "inline": True},
                    {"label": "Today", "value": str(daily), "inline": True},
                    {"label": "Error Rate", "value": f"{errors}%", "inline": True},
                ],
            }
        except Exception:
            return None

    async def _health_section(self) -> Optional[dict]:
        try:
            autopilot_ids = await self.redis.smembers("autopilots:all") or []
            active = 0
            for aid in autopilot_ids:
                cfg = await self.redis.hgetall(f"autopilot:{aid}:config")
                if cfg and cfg.get("enabled") == "true":
                    active += 1
            return {
                "title": "System Health",
                "color": 3066993,
                "items": [
                    {"label": "Active Autopilots", "value": str(active), "inline": True},
                    {"label": "Redis Connected", "value": "Yes", "inline": True},
                ],
            }
        except Exception:
            return None

    async def send_to_discord(self, webhook_url: Optional[str] = None) -> bool:
        try:
            from core.discord_webhook import send_discord
            report = await self.generate()
            embeds = self._to_discord_embed(report)
            for embed in embeds:
                await send_discord(
                    content="",
                    embed_title=embed["title"],
                    embed_color=embed["color"],
                    fields=embed["fields"],
                    webhook_url=webhook_url,
                )
            return True
        except Exception as e:
            log.error("weekly.discord_failed", error=str(e))
            return False


class MonthlyReport(ReportGenerator):
    """Generates a monthly summary report."""

    def __init__(self):
        self.redis = get_redis()

    async def generate(self) -> dict:
        sections = []
        outreach = await WeeklyDigest()._outreach_section()
        if outreach:
            outreach["title"] = "Monthly Outreach"
            sections.append(outreach)

        revenue = await self._revenue_estimate()
        if revenue:
            sections.append(revenue)

        seo = await self._seo_monthly()
        if seo:
            sections.append(seo)

        agent = await self._agent_cost()
        if agent:
            sections.append(agent)

        report = {
            "title": "Monthly Report",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sections": sections,
        }
        month_key = time.strftime("%Y-%m", time.gmtime())
        await self.redis.set(f"reports:monthly:{month_key}", report, ex=90 * 86400)
        await self.redis.sadd("reports:monthly:index", month_key)
        return report

    async def _revenue_estimate(self) -> Optional[dict]:
        try:
            cids = await self.redis.smembers("campaigns:all") or []
            total_won = 0
            for cid in cids:
                meta = await self.redis.hgetall(f"campaign:{cid}:meta")
                if meta:
                    total_won += int(meta.get("conversions", 0) or 0)
            default_deal = 500
            estimated = total_won * default_deal
            return {
                "title": "Revenue Estimate",
                "color": 3066993,
                "items": [
                    {"label": "Deals Won", "value": str(total_won), "inline": True},
                    {"label": "Est. Revenue", "value": f"${estimated:,}", "inline": True},
                    {"label": "Avg Deal Size", "value": f"${default_deal}", "inline": True},
                ],
            }
        except Exception:
            return None

    async def _seo_monthly(self) -> Optional[dict]:
        try:
            from core.seo_tracker import SEOReportGenerator
            seo_gen = SEOReportGenerator()
            monthly = await seo_gen.generate_monthly()
            return {
                "title": "SEO Performance",
                "color": 10181046,
                "items": [
                    {"label": "Domains Tracked", "value": str(monthly.get("domains_tracked", 0)), "inline": True},
                    {"label": "Average Score", "value": str(monthly.get("average_score", "N/A")), "inline": True},
                    {"label": "Improving", "value": str(monthly.get("improving", 0)), "inline": True},
                    {"label": "Declining", "value": str(monthly.get("declining", 0)), "inline": True},
                ],
            }
        except Exception:
            return None

    async def _agent_cost(self) -> Optional[dict]:
        try:
            kpi = KPITracker()
            total = await kpi.get_current("agent_executions_total") or 0
            avg_dur = await kpi.get_current("agent_avg_duration") or 0
            compute_hours = round(total * avg_dur / 3600, 1) if avg_dur else 0
            return {
                "title": "Agent Costs",
                "color": 15844367,
                "items": [
                    {"label": "Total Executions", "value": str(total), "inline": True},
                    {"label": "Avg Duration", "value": f"{avg_dur}s", "inline": True},
                    {"label": "Compute Hours", "value": str(compute_hours), "inline": True},
                    {"label": "Model Cost", "value": "$0 (local)", "inline": True},
                ],
            }
        except Exception:
            return None

    async def send_to_discord(self, webhook_url: Optional[str] = None) -> bool:
        try:
            from core.discord_webhook import send_discord
            report = await self.generate()
            embeds = self._to_discord_embed(report)
            for embed in embeds:
                await send_discord(
                    content="",
                    embed_title=embed["title"],
                    embed_color=embed["color"],
                    fields=embed["fields"],
                    webhook_url=webhook_url,
                )
            return True
        except Exception as e:
            log.error("monthly.discord_failed", error=str(e))
            return False


class AgentCostReport(ReportGenerator):
    """Estimates agent compute costs."""

    def __init__(self):
        self.redis = get_redis()

    async def estimate_cost(self) -> dict:
        kpi = KPITracker()
        total = await kpi.get_current("agent_executions_total") or 0
        avg_dur = await kpi.get_current("agent_avg_duration") or 0
        compute_hours = round(total * avg_dur / 3600, 1) if avg_dur else 0

        report = {
            "title": "Agent Cost Report",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sections": [{
                "title": "Compute Usage",
                "color": 15844367,
                "items": [
                    {"label": "Total Executions", "value": str(total), "inline": True},
                    {"label": "Avg Duration (s)", "value": str(avg_dur), "inline": True},
                    {"label": "Compute Hours", "value": str(compute_hours), "inline": True},
                    {"label": "Model", "value": "Local Ollama ($0)", "inline": True},
                    {"label": "Redis Storage", "value": "~estimating...", "inline": True},
                ],
            }],
        }
        return report


class KPITracker:
    """Minimal inline KPI reader (delegates to core.kpi_tracker)."""

    def __init__(self):
        self.redis = get_redis()

    async def get_current(self, name: str) -> Optional[float]:
        from core.kpi_tracker import KPITracker as KPI
        return await KPI().get_current(name)
