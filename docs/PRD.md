# PRD — 30-Agent Cognitive Orchestration System

> **Status:** Production-ready · **Type:** Local, self-hosted multi-agent AI platform
> **Single source of truth** for what this system is, who it serves, and how success is measured.

---

## 1. Business Problem

Small agencies, freelancers, and solo technical consultants lose billable hours to three expensive patterns:

1. **Cloud LLM cost & lock-in** — Every "AI-powered" workflow (lead-gen outreach, SEO audits, content, code review) routes through per-token cloud APIs. At agency volume this is a recurring five-figure line item and a data-privacy liability (client data leaves the building).
2. **Prompt spaghetti** — Ad-hoc ChatGPT/Claude usage has no routing, no memory, no retry discipline, no audit trail. Output quality varies by who typed the prompt that day.
3. **No reusable pipeline** — Lead discovery → email enrichment → personalized outreach → SEO audit → report is re-assembled by hand for every client engagement.

**The expensive problem:** knowledge-work businesses pay cloud-margin prices for orchestration that is deterministic enough to run locally, and they re-build the same pipelines per-client instead of owning the pipeline as an asset.

## 2. Product

A **local, fully self-hosted multi-agent orchestration system**: LangGraph state machine + FastAPI + Ollama (no cloud API keys required for inference). 40 specialist agents across 6 capability tiers, addressable individually, as **6 pre-wired squads** (`@OutreachSquad`, `@SEOSquad`, `@AnalyticsSquad`, `@ContentSquad`, `@CodeSquad`, `@VisionSquad`), or via REST/WebSocket/CLI/MCP.

**Surfaces:**

| Surface | Entry point |
|---|---|
| Chat UI | `http://127.0.0.1:8000/` |
| REST / WebSocket API | `POST /api/chat`, `/api/outreach/*`, `/api/seo/*`, `/api/squads/*` |
| Typer CLI | `python main.py chat / squads / outreach / serve` |
| MCP bridge | `tools/mcp_bridge.py` / `tools/mcp_hub.py` (Cursor, OpenCode, Claude Desktop) |
| Windows launcher | `Start-Agents.bat` / one-file exe |

## 3. Target Users

- **Technical freelancer / agency** (primary): runs outreach + SEO + content pipelines for local-business clients; wants margin, not API bills.
- **Solo developer** (secondary): wants a local agent workbench with real routing, memory, and observability instead of a framework kit.

## 4. Target Metrics

| Metric | Target | How measured |
|---|---|---|
| Inference cost per pipeline run | **$0 marginal** (local Ollama) | `core/kpi_tracker.py` agent cost report |
| Outreach pipeline: leads → personalized emails | 50 leads/run, dry-run safe | `/api/outreach/pipeline`, `lead_manager` |
| Graph routing integrity | full `agent_path` trace on every run | `core/graph.py` `_tracked` wrapper |
| Failure containment | 504 at `AGENT_TIMEOUT` (default 120 s); orchestrator bail at 5 retries; hard recursion limit 50 hops | `core/config.py`, `BaseAgent.__call__` |
| Auth safety | fail-closed 503 when `API_SECRET` unset | `api/server.py` middleware |
| Test coverage | pytest suite, `asyncio_mode=auto` | `tests/` |

## 5. Technical Constraints

- **Pluggable inference, one interface.** All agent LLM calls go through `get_ollama()`, which dispatches on `LLM_BACKEND`: `ollama` → local quantized GGUF (zero marginal cost, no data egress); `nim` → NVIDIA NIM (OpenAI-compatible, higher quality, paid). Default is `nim`; `ollama` is the no-cloud-key mode. `MODEL_FAST` / `MODEL_REASON` / `MODEL_VISION` resolve against the active backend.
- **Local-first state.** Redis for sessions/metrics (`session:*`, `workflow:*`, `agent:metrics:*`), ChromaDB embedded → `data/chroma/`.
- **Single-writer graph.** `get_graph()` is a module-level singleton; `register_all_agents()` must run exactly once before `graph.run()` (server does it in FastAPI `lifespan`).
- **Security gate.** Tool calls pass a whitelist + blocked-arg pattern check; webhook URLs allowlisted to HTTPS Discord domains; PII scrubbed (`core/security_gate.py`, `core/validation.py`).
- **Windows-first packaging**, cross-platform via `./start`.

## 6. Scope

**In scope:** orchestration, 6 squads, outreach pipeline (scrape→enrich→generate→send via Resend, dry-run default), SEO pipeline, design concepts, KPI/reporting, Discord notifications, autopilot scheduler, MCP exposure.

**Out of scope (by design):** human-in-the-loop approval tools (12-factor #7 — not yet implemented); multi-tenant SaaS hosting; cloud-managed inference fallback.

## 7. Success Definition

A freelancer can point the system at a city, run one command, and get a dry-run outreach campaign + SEO audit with a full routing trace and cost report — at zero marginal inference cost, on hardware they own.
