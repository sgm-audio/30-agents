# Case study: Local 30-agent cognitive system

**Scott Mills — sgm-audio / SGM-Studios**  
**Stack:** Python, LangGraph, FastAPI, Ollama, Redis, ChromaDB  
**Repo:** [SGM-Studios/30-agents](https://github.com/SGM-Studios/30-agents) (private; ask for walkthrough)

## Problem

I needed a **fully local** multi-agent stack for research, code, content, and Vancouver local-business outreach — no cloud LLM keys, runnable on a Windows workstation and transferable to a Linux VM.

Most “agent frameworks” either lock you into hosted APIs or leave you with a single chat loop. I wanted **named specialists**, **explicit routing**, and **pipelines** (outreach, SEO, code review) I could call from Cursor, CLI, or HTTP.

## Approach

1. **Own the control flow** — LangGraph nodes return `next_agent`; the orchestrator routes; `result` ends the run. Inspired by [12-factor agents](https://github.com/humanlayer/12-factor-agents) (own prompts, own context, tools as structured outputs).
2. **Small specialists, not one mega-prompt** — ~30 agents across six tiers (infra, research, code, content, analysis, vision), plus domain agents for outreach and SEO.
3. **Squads** — six squad leaders (Outreach, SEO, Analytics, Content, Code, Vision) that sequence or fan-out members and compile a final report.
4. **Trigger from anywhere** — FastAPI (`/api/chat`, `/api/outreach/*`, `/api/seo/*`, `/api/squads/*`), Typer CLI, Windows double-click launchers, and an in-repo **MCP stdio bridge** so Cursor/OpenCode can call the same endpoints as tools.
5. **Local inference** — Ollama for chat + embeddings; Redis for sessions/metrics; ChromaDB for memory.

## What shipped (high signal)

| Capability | How |
|------------|-----|
| Orchestrated chat | `POST /api/chat` → LangGraph |
| Lead → email pipeline | scrape → enrich → generate → send (dry-run default) |
| SEO audit pipeline | on-page / technical / content in parallel + backlinks |
| Cursor integration | `tools/mcp_bridge.py` + `.cursor/mcp.json` |
| Operator UX | Tkinter launcher, `Start-Agents.bat`, browser chat UI |
| Ops extras | Discord webhooks, autopilot templates, KPI/report modules |

## Design choices that mattered

- **Prompts live on the agent class** (`system_prompt`), not buried in a framework — easy to audit and version.
- **Dry-run by default** for outbound email — safety at the trust boundary.
- **Degraded health** when Ollama is down — API still boots so MCP/health/UI stay usable while models catch up.
- **Checkpointed model pulls** (`scripts/pull_models.py`) — long GGUF downloads survive sleep/interrupts.

## Honest limits

- Domain agents from the origin design (legal, healthcare, etc.) were **consciously deferred** — see `TODO.md` Phase 7.
- Quality depends on local model size/VRAM; CPU-only VMs need small models and backend quirks documented for Cursor Cloud.

## Outcome

A self-hosted agent platform I use as infrastructure: Cursor talks to it over MCP, outreach/SEO run as squads, and nothing critical requires a paid LLM API. The same codebase runs as a desktop app entrypoint on Windows and as a FastAPI service on a VM.

## Talk track (60 seconds)

> I built a local multi-agent system on LangGraph + FastAPI + Ollama: thirty specialists, six squad pipelines, and an MCP bridge so my IDE calls the same API as the CLI. The interesting part isn’t “more agents” — it’s owning routing, prompts, and dry-run safety so outreach and SEO automation stay local and inspectable.

## Artifacts for interviewers

- Architecture notes: `AGENTS.md`
- Origin → current gap list: `TODO.md` Phase 7
- Smoke procedure: `docs/WINDOWS_SMOKE.md`
- Live demo: health → chat → one squad (content or outreach dry-run)
