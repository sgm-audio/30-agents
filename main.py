#!/usr/bin/env python3
"""
Main entry point for the 30-Agent Cognitive System.

Usage:
  python main.py serve          # Start the API server
  python main.py chat "task"    # One-shot CLI chat
  python main.py health         # Health check
  python main.py agents         # List all agents
"""
import asyncio
import sys
from pathlib import Path

# Ensure project root is in Python path
sys.path.insert(0, str(Path(__file__).parent))

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from core.config import settings

app = typer.Typer(help="30-Agent Cognitive System CLI")
console = Console()


def _api_headers() -> dict:
    """Shared secret for CLI → local API calls (matches HTTP middleware)."""
    if settings.api_secret:
        return {"X-API-Key": settings.api_secret}
    return {}


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API host"),
    port: int = typer.Option(8000, help="API port"),
    reload: bool = typer.Option(False, help="Enable hot reload"),
):
    """Start the FastAPI server."""
    import uvicorn
    from core.logging_setup import setup_logging
    setup_logging()
    console.print(Panel(f"[bold green]Starting 30-Agent System[/bold green]\nAPI: http://{host}:{port}"))
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def chat(
    task: str = typer.Argument(..., help="Task to execute"),
    session: str = typer.Option("cli", help="Session ID"),
):
    """Run a single task through the agent system."""
    from core.logging_setup import setup_logging
    setup_logging()

    async def _run():
        from agents.registry import register_all_agents
        from core.config import settings
        from core.graph import get_graph

        console.print(f"[dim]Task: {task}[/dim]")
        register_all_agents()
        graph = get_graph()
        try:
            state = await asyncio.wait_for(
                graph.run(task=task, session_id=session),
                timeout=settings.agent_timeout,
            )
            result = state.get("result") or state.get("error") or "No result"
            console.print(Panel(result, title="[bold blue]Result[/bold blue]"))
        except asyncio.TimeoutError:
            console.print(Panel(
                f"[bold red]Timed out after {settings.agent_timeout}s[/bold red]",
                title="[bold red]Error[/bold red]",
            ))

    asyncio.run(_run())


@app.command()
def health():
    """Check system health."""
    async def _check():
        from core.ollama_client import get_ollama
        from core.redis_client import get_redis

        ollama = get_ollama()
        redis = get_redis()

        table = Table(title="System Health")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")

        ollama_ok = await ollama.health()
        models = await ollama.list_models() if ollama_ok else []
        table.add_row("Ollama", "✓ OK" if ollama_ok else "✗ DOWN", f"{len(models)} models")

        redis_ok = await redis.ping()
        table.add_row("Redis", "✓ OK" if redis_ok else "✗ DOWN", "127.0.0.1:6379")

        from pathlib import Path
        from core.config import settings
        chroma_path = Path(settings.chroma_persist_dir)
        table.add_row(
            "ChromaDB",
            "✓ Ready" if chroma_path.parent.exists() else "✗ Missing",
            str(settings.chroma_persist_dir),
        )

        if models:
            table.add_row("Models", "✓ Available", ", ".join(models))

        console.print(table)

    asyncio.run(_check())


@app.command()
def list_agents_cmd():
    """List all 30 agents."""
    from agents.registry import get_agent_info, ALL_AGENTS, _get_tier

    # Instantiate registry metadata without building graph
    table = Table(title="30-Agent Cognitive System")
    table.add_column("#", style="dim", width=4)
    table.add_column("Agent Name", style="cyan")
    table.add_column("Tier", style="yellow", width=6)
    table.add_column("Model", style="dim")
    table.add_column("Description")

    tier_names = {
        1: "Core",
        2: "Research",
        3: "Code",
        4: "Content",
        5: "Analysis",
        6: "Multimodal",
    }

    for i, AgentClass in enumerate(ALL_AGENTS, 1):
        tier = _get_tier(i - 1)

        table.add_row(
            str(i),
            AgentClass.name,
            f"T{tier} {tier_names[tier]}",
            AgentClass.model or "fast",
            AgentClass.description,
        )

    console.print(table)


@app.command()
def pull_models():
    """Pull all required Ollama models."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "scripts/pull_models.py"],
        cwd=str(Path(__file__).parent),
    )
    sys.exit(result.returncode)


@app.command()
def squads():
    """List all available squads."""
    from rich.console import Console
    from rich.table import Table
    from squads import ALL_SQUADS

    console = Console()
    table = Table(title="Available Squads (30-Agent System)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Squad", style="cyan")
    table.add_column("Members", style="dim")
    table.add_column("Description")

    for i, (name, config) in enumerate(ALL_SQUADS.items(), 1):
        members = ", ".join(m.name for m in config.members)
        desc = config.description[:55] + "..." if len(config.description) > 55 else config.description
        table.add_row(str(i), config.display_name, members, desc)

    console.print(table)


# ──────────────────────────────────────────────
# Autopilot Commands
# ──────────────────────────────────────────────
autopilot_app = typer.Typer(help="Manage scheduled autopilots")
app.add_typer(autopilot_app, name="autopilot")


@autopilot_app.command("list")
def autopilot_list():
    """List all configured autopilots."""
    import httpx

    async def _list():
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_api_headers()) as client:
                r = await client.get(f"http://localhost:{settings.api_port}/api/autopilots")
                r.raise_for_status()
                data = r.json()

            if not data["autopilots"]:
                console.print("[yellow]No autopilots configured.[/yellow]")
                return

            table = Table(title="Multica Autopilots")
            table.add_column("Name", style="cyan")
            table.add_column("Agent", style="green")
            table.add_column("Schedule", style="yellow")
            table.add_column("Next Run", style="dim")
            table.add_column("Status", style="magenta")

            for a in data["autopilots"]:
                status = "[green]Enabled[/green]" if a["enabled"] else "[red]Disabled[/red]"
                next_run = a.get("next_run", "N/A")
                if next_run and next_run != "None":
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                        next_run = dt.strftime("%Y-%m-%d %H:%M UTC")
                    except Exception:
                        pass
                else:
                    next_run = "N/A"

                table.add_row(
                    a["name"],
                    a["agent_name"],
                    a["cron"],
                    next_run,
                    status,
                )
            console.print(table)

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API. Start server with: python main.py serve[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_list())


@autopilot_app.command("create")
def autopilot_create(
    name: str = typer.Option(..., "--name", help="Autopilot name"),
    agent: str = typer.Option(..., "--agent", help="Agent name (e.g., lead_scout)"),
    cron: str = typer.Option(..., "--cron", help="Cron expression (5-field)"),
    task: str = typer.Option(..., "--task", help="Task template"),
    timezone: str = typer.Option("UTC", "--tz", help="IANA timezone"),
    webhook: str = typer.Option(None, "--webhook", help="Discord webhook URL"),
    notify: str = typer.Option("failure", "--notify", help="Notify on: success, failure, all (comma-separated)"),
):
    """Create a new autopilot."""
    import httpx

    notify_on = [n.strip() for n in notify.split(",")]

    async def _create():
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_api_headers()) as client:
                r = await client.post(
                    f"http://localhost:{settings.api_port}/api/autopilots",
                    json={
                        "name": name,
                        "agent_name": agent,
                        "cron": cron,
                        "task_template": task,
                        "timezone": timezone,
                        "webhook_url": webhook,
                        "notify_on": notify_on,
                    },
                )
                r.raise_for_status()
                data = r.json()
                console.print(f"[green]Created autopilot '{data['name']}'[/green]")
                console.print(f"  ID: {data['id']}")
                console.print(f"  Agent: {data['agent_name']}")
                console.print(f"  Schedule: {data['cron']}")
                console.print(f"  Next run: {data.get('next_run', 'N/A')}")

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API. Start server with: python main.py serve[/red]")
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Error: {e.response.text}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_create())


@autopilot_app.command("delete")
def autopilot_delete(name: str = typer.Argument(..., help="Autopilot name or ID")):
    """Delete an autopilot."""
    import httpx

    async def _delete():
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_api_headers()) as client:
                list_r = await client.get("http://localhost:8000/api/autopilots")
                list_r.raise_for_status()
                autopilots = list_r.json()["autopilots"]

                autopilot_id = None
                for a in autopilots:
                    if a["name"].lower() == name.lower() or a["id"] == name:
                        autopilot_id = a["id"]
                        break

                if not autopilot_id:
                    console.print(f"[red]Autopilot '{name}' not found[/red]")
                    return

                r = await client.delete(f"http://localhost:8000/api/autopilots/{autopilot_id}")
                r.raise_for_status()
                console.print(f"[green]Deleted autopilot '{name}'[/green]")

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API. Start server with: python main.py serve[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_delete())


@autopilot_app.command("toggle")
def autopilot_toggle(name: str = typer.Argument(..., help="Autopilot name or ID"), enabled: bool = typer.Argument(True, help="Enable (true) or disable (false)")):
    """Enable or disable an autopilot."""
    import httpx

    async def _toggle():
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_api_headers()) as client:
                list_r = await client.get("http://localhost:8000/api/autopilots")
                list_r.raise_for_status()
                autopilots = list_r.json()["autopilots"]

                autopilot_id = None
                for a in autopilots:
                    if a["name"].lower() == name.lower() or a["id"] == name:
                        autopilot_id = a["id"]
                        break

                if not autopilot_id:
                    console.print(f"[red]Autopilot '{name}' not found[/red]")
                    return

                r = await client.patch(
                    f"http://localhost:8000/api/autopilots/{autopilot_id}",
                    json={"enabled": enabled},
                )
                r.raise_for_status()
                console.print(f"[green]Autopilot '{name}' {'enabled' if enabled else 'disabled'}[/green]")

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API. Start server with: python main.py serve[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_toggle())


@autopilot_app.command("setup-defaults")
def autopilot_setup_defaults(
    webhook: str = typer.Option(None, "--webhook", help="Discord webhook URL for alerts"),
):
    """Set up the 4 default autopilots (Daily Lead Scrape, Weekly SEO, Monthly Report, Real-time Alerts)."""
    from core.config import settings

    if not webhook:
        webhook = settings.discord_webhook_url

    if not webhook:
        console.print("[yellow]No Discord webhook provided. Alerts will be disabled.[/yellow]")
        webhook = None

    async def _setup():
        import httpx

        defaults = [
            {
                "name": "Daily Lead Scrape",
                "agent_name": "lead_scout",
                "cron": "0 8 * * *",
                "task_template": "Scrape leads for Vancouver businesses - find businesses without websites",
                "timezone": "America/Vancouver",
                "inputs": {"city": "Vancouver", "region": "BC", "max_leads": 50},
                "webhook_url": webhook,
                "notify_on": ["failure"],
            },
            {
                "name": "Weekly SEO Audit",
                "agent_name": "web_researcher",
                "cron": "0 9 * * 1",
                "task_template": "Run full SEO pipeline audit - analyze top Vancouver business websites for SEO opportunities",
                "timezone": "America/Vancouver",
                "inputs": {},
                "webhook_url": webhook,
                "notify_on": ["failure"],
            },
            {
                "name": "Monthly Report",
                "agent_name": "summarizer",
                "cron": "0 9 1 * *",
                "task_template": "Generate monthly performance report summarizing all outreach activities, leads found, emails sent, and SEO improvements",
                "timezone": "America/Vancouver",
                "inputs": {},
                "webhook_url": webhook,
                "notify_on": ["success", "failure"],
            },
        ]

        created = []
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=_api_headers()) as client:
                for cfg in defaults:
                    try:
                        r = await client.post(
                            f"http://localhost:8000/api/autopilots",
                            json=cfg,
                        )
                        r.raise_for_status()
                        data = r.json()
                        created.append(data["name"])
                        console.print(f"[green]+ Created: {data['name']}[/green]")
                    except Exception as e:
                        console.print(f"[red]Failed to create {cfg['name']}: {e}[/red]")

            if created:
                console.print(f"\n[green]Successfully created {len(created)} autopilots:[/green]")
                for name in created:
                    console.print(f"  - {name}")
            else:
                console.print("[yellow]No autopilots were created.[/yellow]")

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API. Start server with: python main.py serve[/red]")

    asyncio.run(_setup())


@app.command()
def squad_run(
    name: str = typer.Argument(..., help="Squad name (outreach, seo, analytics, content, code, vision)"),
    task: str = typer.Option(None, help="Task description"),
    city: str = typer.Option(None, help="City (for outreach/SEO)"),
    url: str = typer.Option(None, help="URL (for SEO/content)"),
    max_leads: int = typer.Option(None, help="Max leads (for outreach)"),
    session: str = typer.Option(None, help="Session ID"),
):
    """Run a squad pipeline end-to-end via the API."""
    import asyncio
    from squads.cli import run_squad_via_api
    asyncio.run(run_squad_via_api(name, task, city, url, max_leads, session))


@app.command()
def outreach(
    city: str = typer.Option("Vancouver", help="City to target"),
    max_leads: int = typer.Option(50, help="Max leads to find"),
    dry_run: bool = typer.Option(True, help="Generate emails without sending"),
    send: bool = typer.Option(False, help="Actually send emails (overrides dry_run)"),
):
    """Run the full outreach pipeline: scrape → enrich → generate → send."""
    import httpx
    import json
    from core.config import settings

    async def _run():
        base_url = f"http://localhost:{settings.api_port}"
        console.print(Panel(f"[bold green]Outreach Pipeline[/bold green]\nCity: {city} | Max leads: {max_leads} | Send: {not dry_run and send}"))

        # Check health first
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_api_headers()) as client:
                health = await client.get(f"{base_url}/api/health")
                if health.status_code != 200:
                    console.print("[red]API not responding. Start with: python main.py serve[/red]")
                    return
        except Exception:
            console.print("[red]Cannot connect to API at localhost:8000. Start with: python main.py serve[/red]")
            return

        actual_dry_run = not send

        console.print(f"\n[cyan]Running full pipeline (dry_run={actual_dry_run})...[/cyan]")

        try:
            async with httpx.AsyncClient(timeout=300.0, headers=_api_headers()) as client:
                r = await client.post(
                    f"{base_url}/api/outreach/pipeline",
                    params={"city": city, "max_leads": max_leads, "dry_run": actual_dry_run},
                )
                r.raise_for_status()
                data = r.json()

                console.print(Panel(
                    f"[green]Pipeline complete![/green]\n"
                    f"Leads found: {data['leads_found']}\n"
                    f"Emails generated: {data['emails_generated']}\n"
                    f"Status: {data['stage']}",
                    title="[bold]Results[/bold]",
                ))

                if data.get("emails"):
                    console.print("\n[yellow]Sample emails:[/yellow]")
                    for em in data["emails"][:3]:
                        console.print(f"\n--- {em['lead_name']} ---")
                        console.print(f"To: {em['to_email']}")
                        console.print(f"Subject: {em['subject']}")
                        console.print(f"Body: {em['body'][:150]}...")

                # Save to file
                out_path = Path("data/outreach_leads.json")
                out_path.parent.mkdir(exist_ok=True)
                out_path.write_text(json.dumps(data, indent=2))
                console.print(f"\n[dim]Results saved to {out_path}[/dim]")

        except httpx.HTTPStatusError as e:
            console.print(f"[red]Pipeline failed: {e.response.text}[/red]")
        except Exception as e:
            console.print(f"[red]Pipeline failed: {e}[/red]")

    asyncio.run(_run())


# ──────────────────────────────────────────────
# Feedback / Self-Improvement Commands
# ──────────────────────────────────────────────
feedback_app = typer.Typer(help="Log corrections and export fine-tune preference datasets")
app.add_typer(feedback_app, name="feedback")


@feedback_app.command("log")
def feedback_log(
    task: str = typer.Option(..., "--task", help="Original task given to the agent"),
    wrong: str = typer.Option(..., "--wrong", help="The incorrect agent output"),
    right: str = typer.Option(..., "--right", help="The corrected/expected output"),
    agent: str = typer.Option("", "--agent", help="Agent name that produced the wrong output"),
):
    """Log a correction for later preference-dataset export."""
    from core.self_improve import log_correction

    result = log_correction(task, wrong, right, agent)
    console.print(f"[green]Logged correction #{result['count']}[/green]")
    if result["exported"]:
        console.print(f"[cyan]Auto-exported dataset: {result['exported']}[/cyan]")


@feedback_app.command("export")
def feedback_export():
    """Export the current preference dataset from all logged corrections."""
    from core.self_improve import export_preference_dataset

    out = export_preference_dataset()
    if out:
        console.print(f"[green]Exported: {out}[/green]")
    else:
        console.print("[yellow]No corrections logged yet.[/yellow]")


if __name__ == "__main__":
    app()
