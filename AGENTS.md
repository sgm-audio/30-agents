# AGENTS.md — 30-Agent Cognitive System

> **📋 Active development tracking:** See [TODO.md](./TODO.md) for current tasks, progress, blockers, and next steps.

---

## ⚡ Everyday use (Windows)

**Double-click `Start-Agents.bat`**

That starts the system and opens the chat UI in your browser:
**http://127.0.0.1:8000/** — type a task, hit Send.

- `Stop-Agents.bat` — shut it down
- `Create-Desktop-Shortcut.bat` — put a “30-Agents” icon on your Desktop (optional, once)

Mac/Linux: `./start` then open http://127.0.0.1:8000/

---

## What this repo is

Local, fully self-hosted 30-agent AI orchestration system. LangGraph + FastAPI + Ollama (no cloud API keys). Exposed as REST/WebSocket API at `http://localhost:8000` and a Typer CLI (`main.py`).

## Prerequisites

`./start` brings up Redis + the API. For full agent LLM calls you also want:
1. **Ollama** — local models (without it, health shows `degraded` / `ollama:false` but the API still runs)
2. **Redis** — started automatically by `./start` / `./run.sh` (system `redis-server`, Docker, or Podman)
3. **ChromaDB** — embedded; auto-persists to `data/chroma/`

## Developer commands

```bash
./start                         # recommended everyday entrypoint
./run.sh                        # tmux session 'agents30'
./run.sh --no-tmux              # foreground server

python main.py health           # check Ollama + Redis + ChromaDB
python main.py agents           # list all agents
python main.py chat "your task" # one-shot task
python main.py serve --reload   # hot-reload for development

# Install/sync deps (no lockfile — requirements.txt uses >= pins)
pip install -r requirements.txt
```

## Testing

```bash
pytest                                                          # all tests
pytest tests/test_agents.py::TestAgentInstantiation            # single class
pytest tests/test_agents.py::TestAgentExecution::test_summarizer_execute  # single test
pytest -v -x                                                    # verbose, stop at first failure
```

`pytest.ini` sets `asyncio_mode = auto` — all `async def` tests run automatically; no `@pytest.mark.asyncio` needed.

**No linting, formatting, or typecheck tooling is configured** (no ruff, mypy, black, etc.).

## Architecture — things not obvious from filenames

### Agent file layout
All agents for a tier live in **one file**: `agents/tier{N}/__init__.py`. There are no per-agent files.
- Tier 1 (`tier1/__init__.py`): Orchestrator, MemoryManager, ContextTracker, ToolDispatcher, StateMachine
- Tier 2: Web/Doc/Knowledge/Fact/KB/SemanticSearch
- Tier 3: Code writing/review/bugs/arch/testing
- Tier 4: Writer/Summarizer/Translator/Editor/ContentStrategist
- Tier 5: DataAnalyst/Logic/Planner/Critic/Decision
- Tier 6: Vision/Embedding/Multimodal/MediaCoordinator

### Graph singleton
`get_graph()` returns a module-level singleton. **`register_all_agents()` must be called before `graph.run()`** — the server does this in FastAPI `lifespan`; the CLI does it inline. Calling it multiple times accumulates duplicate node registrations; tests use `scope="session"` fixtures to avoid this.

### Routing
`START → orchestrator → <specialist> → orchestrator → ...`  
Agents return `{"next_agent": "<name>"}`. Setting `state["result"]` terminates the graph. Loop guard: orchestrator bails after 5 retries; hard recursion limit: 50 hops.

### `agent_path` tracking
Injected by `AgentGraph.register()`'s `_tracked` wrapper — agents must **not** set `agent_path` themselves.

### State schema (key fields)
`messages`, `next_agent`, `task`, `context`, `result`, `error`, `retries`, `session_id`, `user_id`, `agent_path`

## Config

All config lives in `.env` → `core/config.py` → `settings` singleton.

| Variable | Default | Notes |
|---|---|---|
| `MODEL_FAST` | `hf.co/evalengine/unbound-e2b-gguf:Q4_K_M` | Used by most agents |
| `MODEL_REASON` | `huihui_ai/gemma-4-abliterated:e4b-q4_K` | Heavy reasoning agents |
| `MODEL_VISION` | `minicpm-v:8b` | Vision/multimodal |
| `MODEL_EMBED` | `nomic-embed-text` | ChromaDB embeddings |
| `AGENT_TIMEOUT` | `120` | Seconds per task (504 on breach) |
| `HSA_OVERRIDE_GFX_VERSION` | `11.5.0` | AMD GPU compat hack — remove on non-AMD systems |

## 12-Factor Agent Methodology

Copied to `methodology/` from [github.com/humanlayer/12-factor-agents](https://github.com/humanlayer/12-factor-agents).

| Factor | File | Maps to |
|--------|------|---------|
| 1 — NL to Tool Calls | `methodology/factor-01-*.md` | LLM → JSON → `next_agent` routing |
| 2 — Own Your Prompts | `methodology/factor-02-*.md` | `system_prompt` on each agent |
| 3 — Own Your Context Window | `methodology/factor-03-*.md` | `AgentState.context` + `build_messages()` |
| 4 — Tools as Structured Outputs | `methodology/factor-04-*.md` | Every agent returns a typed `dict` |
| 5 — Unify Execution & Business State | `methodology/factor-05-*.md` | `AgentState` schema with both message + domain fields |
| 6 — Launch/Pause/Resume | `methodology/factor-06-*.md` | Redis session persistence + `state_set`/`state_get` |
| 7 — Contact Humans with Tools | `methodology/factor-07-*.md` | Not yet implemented |
| 8 — Own Your Control Flow | `methodology/factor-08-*.md` | Explicit `next_agent` routing in LangGraph |
| 9 — Compact Errors into Context | `methodology/factor-09-*.md` | `error` + `retries` in state |
| 10 — Small, Focused Agents | `methodology/factor-10-*.md` | 30 single-purpose agents across 6 tiers |
| 11 — Trigger from Anywhere | `methodology/factor-11-*.md` | REST API (`main.py serve`) + CLI (`main.py chat`) |
| 12 — Stateless Reducer | `methodology/factor-12-*.md` | LangGraph nodes as state reducers |
| 13 — Pre-fetch Context | `methodology/appendix-13-*.md` | `context_tracker` + `memory_manager` agents |

A `methodology_advisor` agent (tier 5) can audit agent designs against these principles.

## Gotchas

- **`.env` is parsed on first agent import** — missing/malformed `.env` breaks all agent imports.
- **`core/config.py` creates `data/chroma/` and `logs/` on import** — side effects at import time.
- **`duckduckgo_search` is not in `requirements.txt`** — `ToolDispatcherAgent` web search will fail unless manually installed.
- **Python 3.14 venv** at `./venv/` is the source of truth for exact package versions (no lockfile).
- **Non-AMD GPU**: remove `OLLAMA_VULKAN=1` and `HSA_OVERRIDE_GFX_VERSION` from `.env` and `run.sh`.
- **Redis key namespaces**: `session:<id>`, `workflow:<id>`, `agent:metrics:<name>`, `history:<id>`.

---

## Outreach System — Local Business Outreach Pipeline

### API Keys Required (`.env`)
```
SERPER_API_KEY=        # serper.dev — Google search
TAVILY_API_KEY=        # tavily.ai — web search/enrichment
FIRECRAWL_API_KEY=     # firecrawl.ai — website scraping
HUNTER_API_KEY=        # hunter.io — email finding
RESEND_API_KEY=        # resend.com — email delivery
OUTREACH_EMAIL_FROM=   # your sending address (e.g. scott@sgmstudios.ca)
OUTREACH_DOMAIN=       # your domain (e.g. sgmstudios.ca)
```

### Outreach Agents (Tier 2 & 4)
| Agent | File | Purpose |
|-------|------|---------|
| `lead_scout` | `agents/tier2_outreach.py` | Finds Vancouver businesses without websites via Serper + Tavily |
| `email_finder` | `agents/tier2_outreach.py` | Resolves emails via Hunter.io + domain inference |
| `outreach_writer` | `agents/tier4_outreach.py` | Generates 3-4 sentence personalized cold emails |
| `web_design_concept` | `agents/tier2_seo_design.py` | Researches design trends, proposes redesign concepts |
| `on_page_seo` | `agents/tier2_seo_design.py` | Audits meta tags, headings, keyword density, internal links |
| `technical_seo` | `agents/tier2_seo_design.py` | Audits site speed, mobile, schema, sitemap, robots.txt |
| `content_seo` | `agents/tier2_seo_design.py` | Analyzes content length, readability, keyword gaps vs competitors |
| `backlink_agent` | `agents/tier2_seo_design.py` | Finds competitor backlinks, guest post opps, local citations |

### REST Endpoints
```
POST /api/outreach/scrape          # Find leads
POST /api/outreach/enrich          # Resolve emails
POST /api/outreach/generate        # Generate emails
POST /api/outreach/send            # Send via Resend (dry_run default)
POST /api/outreach/pipeline        # Full pipeline (scrape→enrich→generate→send)

POST /api/seo/analyze              # Full SEO audit (on-page + technical + content, in parallel)
POST /api/seo/backlinks            # Find backlink opportunities
POST /api/seo/pipeline             # SEO + backlink audit in one call

POST /api/design/concept           # Research design trends + propose concept
```

### CLI Usage
```bash
# Run full outreach pipeline (dry-run)
python main.py outreach --city Vancouver --max-leads 50

# Actually send emails
python main.py outreach --city Vancouver --max-leads 100 --send
```

---

## AutoGPT Integration (GCP VM)

AutoGPT runs on GCP at `10.128.0.3` (project: `hivyr-481306`). Custom blocks for this outreach system should be built in `AutoGPT/autogpt_platform/backend/backend/blocks/vancouver_outreach/`.

AutoGPT workflow calls `http://10.128.0.3:8006/api/...` endpoints on the 30-agent server.

To start AutoGPT on GCP:
```bash
# In the AutoGPT/autogpt_platform directory on the VM
docker compose -f docker-compose.yml --profile full up -d
```

---

## Multica Integration

Multica connects an MCP-compatible client (e.g. opencode, Claude Desktop) to the 30-agent system via the **MCP Bridge Server**, plus adds **Discord webhook notifications**, and a **Squad Architecture** for grouped agent workflows.

### MCP Bridge — Expose 30 Agents as MCP Tools

The in-repo bridge (`tools/mcp_bridge.py`) implements the Model Context Protocol over stdio. It proxies MCP `tools/list` and `tools/call` requests to the 30-agent REST API (`localhost:8000`).

#### Cursor wiring (primary)

Project MCP config is committed at `.cursor/mcp.json`. Open this repo in Cursor, start the API (`python main.py serve`), then verify **Settings → MCP** shows `30agents` connected.

```json
{
  "mcpServers": {
    "30agents": {
      "type": "stdio",
      "command": "python3",
      "args": ["${workspaceFolder}/tools/mcp_bridge.py"],
      "env": {
        "AGENTS30_API_BASE": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Optional global install: copy the same server entry into `~/.cursor/mcp.json`, or enable the local plugin at `~/.cursor/plugins/local/30-agents/`.

#### Exposed Tools

| Tool | Maps to | Description |
|------|---------|-------------|
| `agent_chat` | `POST /api/chat` | General purpose agent orchestration |
| `list_agents` | `GET /api/agents` | List registered specialists |
| `list_squads` | `GET /api/squads` | List squad pipelines |
| `run_squad` | `POST /api/squads/{name}/run` | Run a squad end-to-end |
| `outreach_scrape` | `POST /api/outreach/scrape` | Lead discovery (step 1) |
| `outreach_enrich` | `POST /api/outreach/enrich` | Email resolution (step 2) |
| `outreach_generate` | `POST /api/outreach/generate` | Cold email generation (step 3) |
| `outreach_send` | `POST /api/outreach/send` | Email delivery via Resend (step 4) |
| `outreach_pipeline` | `POST /api/outreach/pipeline` | Full outreach pipeline |
| `seo_analyze` | `POST /api/seo/analyze` | Full SEO audit |
| `seo_backlinks` | `POST /api/seo/backlinks` | Backlink opportunity analysis |
| `seo_pipeline` | `POST /api/seo/pipeline` | SEO audit + backlinks |
| `design_concept` | `POST /api/design/concept` | Design trend research + concept |
| `health_check` | `GET /api/health` | System health status |

#### OpenCode / Claude Desktop

The same bridge script works with other MCP clients. Example OpenCode config:

```jsonc
{
  "mcp": {
    "30agents": {
      "type": "local",
      "command": ["python3", "tools/mcp_bridge.py"],
      "enabled": true
    }
  }
}
```

No separate daemon is needed — the MCP client spawns the bridge process automatically on startup.

#### Prerequisites

The 30-agent server must be running on `localhost:8000`:

```bash
python main.py serve
# or (with hot reload)
python main.py serve --reload
```

#### Tool Registration Flow

```
MCP Client (opencode)
  │
  │  stdio JSON-RPC 2.0
  ▼
MCP Bridge (mcp_bridge.py)
  │
  │  HTTP POST /api/*
  ▼
FastAPI Server (localhost:8000)
  │
  ├── /api/chat          → LangGraph orchestrator
  ├── /api/outreach/*    → Tier 2 outreach agents
  ├── /api/seo/*         → Tier 2 SEO/design agents
  └── /api/health        → System health
```

### Discord Webhook Notifications

`core/discord_webhook.py` sends formatted Discord embed messages when agents complete or fail tasks. Config lives in `config/discord_webhook.json`.

#### Configuration

```json
{
  "webhook_url": "PASTE_YOUR_DISCORD_WEBHOOK_URL_HERE",
  "enabled": false,
  "notify_on": ["complete", "error"]
}
```

Set the webhook (programmatic):

```python
from core.discord_webhook import update_webhook_url, set_notify_on
update_webhook_url("https://discord.com/api/webhooks/...")
set_notify_on(["complete", "error"])  # one or both events
```

Or via CLI through autopilot setup:

```bash
python main.py autopilot setup-defaults --webhook https://discord.com/api/webhooks/...
```

#### Notification Types

| Function | Trigger | Embed Color |
|----------|---------|-------------|
| `notify_agent_complete()` | Agent task success | Green (#2ecc71) |
| `notify_agent_error()` | Agent task failure | Red (#e74c3c) |
| `notify_pipeline_complete()` | Pipeline finished | Green (#2ecc71) |
| `test_webhook()` | Configuration test | Orange (#e67e22) |

Each notification includes agent name, task summary, duration, and result/error fields in a Discord embed.

#### Config API

```python
from core.discord_webhook import get_config, is_enabled, get_webhook_url, get_notify_on
```

### Squad Architecture

A **Squad** is a group of specialist agents led by a **Squad Leader** that routes work to members based on task type. This enables addressing a squad as a unit (`@OutreachSquad`) rather than individual agents.

#### Available Squads (6)

| Squad | Members | Pipeline |
|-------|---------|----------|
| `@OutreachSquad` | lead_scout → email_finder → outreach_writer | Sequential: discover → enrich → write |
| `@SEOSquad` | on_page_seo, technical_seo, content_seo → backlink_agent → web_design_concept | Parallel audits → backlinks → design |
| `@AnalyticsSquad` | data_analyst → planner → critic → decision_engine | Sequential with critique loop (max 2 rewrites) |
| `@ContentSquad` | writer → editor → [summarizer\|translator] → content_strategist | Sequential with conditional routing |
| `@CodeSquad` | code_writer → code_reviewer → bug_hunter → system_architect → test_engineer | Sequential with review loop (max 2 rewrites) |
| `@VisionSquad` | vision_analyst → embedding_engine → multimodal_synthesizer → media_coordinator | Sequential or direct routing by task type |

#### Squad Leader Routing

Squad Leaders override `SquadLeader` base class (`squads/base.py`) with custom routing:

- `route_task()` — determines first member based on task analysis
- `is_squad_complete()` — signals when all work is done
- `get_next_member()` — returns next member or `None` (sequential/conditional)
- `get_next_task()` — builds the task string for the next member
- `compile_squad_result()` — produces final aggregated report

Members return to the squad leader (not the orchestrator) via `next_agent: "<squad_leader>"`. The leader tracks progress in `context["squad_stage"]`.

#### Squad Config Files

Each squad has a JSON config in `squads/config/`:

```
squads/config/
├── outreach_squad.json
├── seo_squad.json
├── analytics_squad.json
├── content_squad.json
├── code_squad.json
└── vision_squad.json
```

#### Registration

All 6 squad leaders are registered with the agent graph via `squads/registry.py`:

```python
from squads.registry import register_all_squads
register_all_squads()  # call after agent registration
```

This registers each squad leader as a node in the LangGraph, making them addressable by name.

### REST Endpoints (Squads)

```
GET  /api/squads              # List all squads with member info
GET  /api/squads/{name}       # Get squad details
POST /api/squads/{name}/run   # Run a squad pipeline
POST /api/squads/run          # Run a squad by name (alternative)
```

Request body for `POST /api/squads/{name}/run`:

```json
{
  "task": "Find Vancouver businesses without websites",
  "session_id": "optional-uuid",
  "city": "Vancouver",
  "max_leads": 50,
  "url": "https://example.com"
}
```

Response:

```json
{
  "session_id": "uuid",
  "squad_name": "outreach",
  "result": "[OUTREACH SQUAD Complete]\n\nPipeline summary:...",
  "elapsed_ms": 12345,
  "members_called": ["lead_scout", "email_finder", "outreach_writer"]
}
```

### CLI Commands for Squads

```bash
# List all squads
python main.py squads

# Run a squad pipeline
python main.py squad run outreach                     # default: find Vancouver leads
python main.py squad run seo --url example.com        # SEO audit
python main.py squad run analytics                    # data analysis
python main.py squad run content                      # content creation
python main.py squad run code                         # code generation + review
python main.py squad run vision                       # image analysis

# With options
python main.py squad run outreach --city Vancouver --task "Find restaurants without websites" --max-leads 25
python main.py squad run seo --url https://mysite.com --city Vancouver
```

The `squad run` command calls the REST endpoint and displays results with rich formatting.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (opencode)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ~/.config/opencode/opencode.jsonc                  │   │
│  │  "30agents": { type: "local", command: "python ..." }│   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │ stdio JSON-RPC 2.0
                        ▼
┌──────────────────────────────────────────────────────────────┐
│              MCP Bridge (~/.config/opencode/mcp_bridge.py)    │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │ tools/list  │  │ tools/call   │  │ health_check      │   │
│  │ → 11 MCP    │  │ → proxy POST │  │ → GET /api/health │   │
│  │ tools       │  │ to REST API  │  │                   │   │
│  └─────────────┘  └──────┬───────┘  └───────────────────┘   │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP localhost:8000
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              FastAPI Server (main.py serve)                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                 REST Endpoints                       │    │
│  │  /api/chat  /api/outreach/*  /api/seo/*  /api/squads │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │              Squad Leaders (6 registered)             │    │
│  │  ┌──────────┐ ┌──────┐ ┌────────┐ ┌───────┐ ┌────┐  │    │
│  │  │Outreach  │ │ SEO  │ │Analytics│ │Content│ │Code│  │    │
│  │  │Leader    │ │Leader│ │Leader   │ │Leader │ │Leader│  │    │
│  │  └────┬─────┘ └──┬───┘ └───┬────┘ └───┬───┘ └──┬───┘  │    │
│  │       │          │         │          │        │       │    │
│  │  ┌────▼────┐ ┌──▼──┐ ┌───▼───┐ ┌──▼──┐ ┌──▼───┐ │    │
│  │  │3 members│ │5    │ │4      │ │5    │ │5     │ │    │
│  │  │         │ │membr│ │members│ │membr│ │membrs│ │    │
│  │  └─────────┘ └─────┘ └───────┘ └─────┘ └──────┘ │    │
│  └───────────────────────────────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │            LangGraph Agent Graph (30 nodes)          │    │
│  │  Tier 1-6 Specialist Agents, Orchestrator, Memory,   │    │
│  │  Context, Tool Dispatcher, State Machine             │    │
│  └──────────────────────────────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐    │
│  │       Discord Webhook (core/discord_webhook.py)      │    │
│  │  agent_complete → Green embed   agent_error → Red    │    │
│  │  pipeline_complete → Green      test_webhook → Orange│    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### File Layout Summary

| File | Purpose |
|------|---------|
| `Start-Agents.bat` | Windows: double-click → start API + open chat UI |
| `Stop-Agents.bat` | Windows: stop the API |
| `Create-Desktop-Shortcut.bat` | Windows: Desktop shortcut for Start-Agents |
| `start` | One-command ready: venv + Redis + API |
| `scripts/shell_init.sh` | Puts venv on PATH; aliases `agents-up` / `agents-status` / … |
| `tools/mcp_bridge.py` | MCP stdio bridge — Cursor/OpenCode tools mapped to REST endpoints |
| `.cursor/mcp.json` | Cursor project MCP config — registers `30agents` server |
| `.cursor/rules/30-agents-mcp.mdc` | Cursor rule — when/how to use 30agents MCP tools |
| `squads/__init__.py` | Exports all 6 squad configs + leaders |
| `squads/base.py` | `SquadLeader`, `SquadConfig`, `SquadMember`, `RoutingRule` base classes |
| `squads/registry.py` | `register_all_squads()` — registers leaders with agent graph |
| `squads/outreach.py` | `@OutreachSquad` — lead_scout → email_finder → outreach_writer |
| `squads/seo.py` | `@SEOSquad` — 3 parallel audits → backlinks → design |
| `squads/analytics.py` | `@AnalyticsSquad` — analyze → plan → critique → decide |
| `squads/content.py` | `@ContentSquad` — write → edit → [summarize\|translate] → strategize |
| `squads/code.py` | `@CodeSquad` — write → review (loop) → bug hunt → architect → test |
| `squads/vision.py` | `@VisionSquad` — analyze → embed → synthesize → coordinate |
| `squads/api.py` | FastAPI router for `POST /api/squads/{name}/run` and `GET /api/squads` |
| `squads/cli.py` | Typer CLI for `python main.py squad run/list` |
| `squads/config/*.json` | Per-squad JSON config files |
| `core/discord_webhook.py` | Discord notification sender (completion, error, pipeline, test) |
| `config/discord_webhook.json` | Webhook URL, enabled flag, notify_on filter |
| `main.py` | Updated with `squads`, `squad run` commands + `--webhook` on autopilot |
