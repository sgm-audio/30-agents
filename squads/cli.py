"""
Squad CLI — Command-line interface for squad operations.

Usage:
    python main.py squads              # List all squads
    python main.py squad run outreach  # Run outreach squad
    python main.py squad run seo --url example.com  # Run SEO squad
"""
import asyncio
from pathlib import Path

import httpx
import structlog
import typer

from squads import ALL_SQUADS
from squads.registry import get_squad_info

log = structlog.get_logger(__name__)

squad_cli = typer.Typer(help="Squad management commands")


async def run_squad_via_api(
    squad_name: str,
    task: str | None = None,
    city: str | None = None,
    url: str | None = None,
    max_leads: int | None = None,
    session: str | None = None,
):
    """Programmatic entry point for running a squad via the API. Used by main.py squad_run."""
    from rich.console import Console
    from rich.panel import Panel
    from core.config import settings

    console = Console()

    if squad_name not in ALL_SQUADS:
        console.print(f"[red]Unknown squad: {squad_name}[/red]")
        console.print(f"Available: {', '.join(ALL_SQUADS.keys())}")
        return

    config = ALL_SQUADS[squad_name]

    default_tasks = {
        "outreach": f"Find {city or 'Vancouver'} businesses without websites",
        "seo": f"Analyze {url or 'https://example.com'} for SEO improvements",
        "analytics": "Analyze this data and recommend actions",
        "content": "Write a blog post about AI agents",
        "code": "Write a function to calculate fibonacci numbers",
        "vision": "Analyze this image and describe what you see",
    }

    actual_task = task or default_tasks.get(squad_name, "Process this task")
    session_id = session or f"squad-{squad_name}"

    console.print(Panel(f"[bold green]{config.display_name} Squad[/bold green]\nRunning: {actual_task[:60]}..."))

    base_url = f"http://localhost:{settings.api_port}"

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            req = {"task": actual_task, "session_id": session_id}
            context = {}
            if city:
                context["city"] = city
            if url:
                context["url"] = url
            if max_leads:
                context["max_leads"] = max_leads
            if context:
                req["context"] = context

            r = await client.post(f"{base_url}/api/squads/{squad_name}/run", json=req)
            r.raise_for_status()
            data = r.json()

            elapsed = data.get("elapsed_ms", 0) / 1000
            console.print(Panel(
                f"[green]Squad complete in {elapsed:.1f}s[/green]\n"
                f"Members called: {', '.join(data.get('members_called', []))}",
                title="[bold]Results[/bold]",
            ))

            result = data.get("result", "")
            if len(result) > 1000:
                console.print(result[:1000] + "\n...[truncated]")
            else:
                console.print(result)

    except httpx.ConnectError:
        console.print("[red]Cannot connect to API at localhost:8000. Start with: python main.py serve[/red]")
    except Exception as e:
        console.print(f"[red]Squad failed: {e}[/red]")


@squad_cli.command("list")
def list_squads():
    """List all available squads."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Available Squads")
    table.add_column("Squad", style="cyan")
    table.add_column("Members", style="dim")
    table.add_column("Description")

    for name, config in ALL_SQUADS.items():
        members = ", ".join(m.name for m in config.members)
        table.add_row(
            config.display_name,
            members,
            config.description[:60] + "..." if len(config.description) > 60 else config.description,
        )

    console.print(table)


@squad_cli.command("run")
def run_squad(
    squad_name: str = typer.Argument(..., help="Squad name (outreach, seo, analytics, content, code, vision)"),
    task: str = typer.Option(None, help="Task description (defaults to squad-specific default)"),
    city: str = typer.Option(None, help="City for outreach/SEO tasks"),
    url: str = typer.Option(None, help="URL for SEO/content tasks"),
    max_leads: int = typer.Option(None, help="Max leads for outreach"),
    session: str = typer.Option(None, help="Session ID"),
):
    """Run a squad pipeline."""
    from rich.console import Console
    from rich.panel import Panel
    from core.config import settings

    console = Console()

    if squad_name not in ALL_SQUADS:
        console.print(f"[red]Unknown squad: {squad_name}[/red]")
        console.print(f"Available: {', '.join(ALL_SQUADS.keys())}")
        raise typer.Exit(1)

    config = ALL_SQUADS[squad_name]

    default_tasks = {
        "outreach": f"Find {city or 'Vancouver'} businesses without websites",
        "seo": f"Analyze {url or 'https://example.com'} for SEO improvements",
        "analytics": "Analyze this data and recommend actions",
        "content": "Write a blog post about AI agents",
        "code": "Write a function to calculate fibonacci numbers",
        "vision": "Analyze this image and describe what you see",
    }

    actual_task = task or default_tasks.get(squad_name, "Process this task")
    session_id = session or f"squad-{squad_name}"

    console.print(Panel(f"[bold green]{config.display_name} Squad[/bold green]\nRunning: {actual_task[:60]}..."))

    async def _run():
        base_url = f"http://localhost:{settings.api_port}"

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                req = {
                    "task": actual_task,
                    "session_id": session_id,
                }
                if city:
                    req["context"] = {"city": city}
                if url:
                    req["context"] = {"url": url}
                if max_leads:
                    if "context" not in req:
                        req["context"] = {}
                    req["context"]["max_leads"] = max_leads

                r = await client.post(f"{base_url}/api/squads/{squad_name}/run", json=req)
                r.raise_for_status()
                data = r.json()

                elapsed = data.get("elapsed_ms", 0) / 1000
                console.print(Panel(
                    f"[green]Squad complete in {elapsed:.1f}s[/green]\n"
                    f"Members called: {', '.join(data.get('members_called', []))}",
                    title="[bold]Results[/bold]",
                ))

                result = data.get("result", "")
                if len(result) > 1000:
                    console.print(result[:1000] + "\n...[truncated]")
                else:
                    console.print(result)

        except httpx.ConnectError:
            console.print("[red]Cannot connect to API at localhost:8000. Start with: python main.py serve[/red]")
        except Exception as e:
            console.print(f"[red]Squad failed: {e}[/red]")

    asyncio.run(_run())


if __name__ == "__main__":
    squad_cli()