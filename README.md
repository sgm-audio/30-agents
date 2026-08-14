# 30 Agents

A fully self-hosted, multi-agent orchestration system. **LangGraph + FastAPI + Ollama** — no cloud API keys. Thirty-plus specialist agents across six tiers, composable into **squads** (pipeline workflows), exposed through a REST/WebSocket API, a Typer CLI, a Windows desktop launcher, and an in-repo **MCP stdio bridge** so Cursor/OpenCode can call the same endpoints as tools.

- **Local inference** via Ollama — nothing leaves your machine
- **Explicit routing** — agents return `next_agent`; the orchestrator routes; `result` ends the run
- **Pipelines as squads** — Outreach, SEO, Analytics, Content, Code, Vision
- **Memory & sessions** — ChromaDB for vector memory, Redis for session/workflow state
- **Trigger from anywhere** — HTTP, CLI, WebSocket, MCP, Windows double-click

---

## Quick start

**Windows** — double-click `Start-Agents.bat` (first run creates the venv and installs deps). Open http://127.0.0.1:8000/.

**macOS / Linux**

```bash
./start            # venv + Redis + API server, in the background
./start --fg       # foreground
./start --status   # health only
./start --stop     # stop the background server
```

Then open http://127.0.0.1:8000/ (chat UI) or http://localhost:8000/docs (OpenAPI).

> Optional (recommended for real inference): install [Ollama](https://ollama.com) and pull a model. Without it the API still boots and reports `"degraded"` health.

### Requirements

- Python 3.12+
- Redis (system `redis-server`, Docker, or Podman — `./start` starts it for you)
- Ollama (optional; required for LLM inference)
- ChromaDB (embedded; auto-persists to `data/chroma/`)

---

## Usage

### CLI

```bash
python main.py health             # Ollama + Redis + ChromaDB status
python main.py agents             # list registered agents
python main.py chat "your task"   # one-shot task
python main.py serve --reload     # dev server with hot reload
python main.py squads             # list squads
python main.py squad run code     # run a squad pipeline
```

### REST API

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/agents

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"task": "Your task here", "session_id": "my-session"}'
```

Full endpoint surface: `/api/chat`, `/api/outreach/*`, `/api/seo/*`, `/api/squads/*`, `/api/webhook/*`, `/api/autopilots/*`, plus WebSocket streaming at `/ws/{session_id}`.

### WebSocket (streaming)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/my-session');
ws.send(JSON.stringify({ task: "Analyze this data" }));
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## The agent tiers

| Tier | Role | Agents |
|------|------|--------|
| 1 — Core infrastructure | `orchestrator`, `memory_manager`, `context_tracker`, `tool_dispatcher`, `state_machine` |
| 2 — Research & knowledge | `web_researcher`, `doc_reader`, `knowledge_synthesizer`, `fact_verifier`, `knowledge_base`, `semantic_searcher` |
| 3 — Code & engineering | `code_writer`, `code_reviewer`, `bug_hunter`, `system_architect`, `test_engineer` |
| 4 — Content & creative | `writer`, `summarizer`, `translator`, `editor`, `content_strategist` |
| 5 — Reasoning & analysis | `data_analyst`, `logic_engine`, `planner`, `critic`, `decision_engine`, `methodology_advisor` |
| 6 — Multimodal | `vision_analyst`, `embedding_engine`, `multimodal_synthesizer`, `media_coordinator`, `audio_analyst` |

Plus domain extensions: outreach (`lead_scout`, `email_finder`, `outreach_writer`) and SEO/design (`on_page_seo`, `technical_seo`, `content_seo`, `backlink_agent`, `web_design_concept`).

## Squads

A **squad** is a group of specialists led by a **squad leader** that routes work to members and compiles a final report — addressable as a unit (`@OutreachSquad`) instead of individual agents.

| Squad | Pipeline |
|-------|----------|
| `@OutreachSquad` | lead_scout → email_finder → outreach_writer |
| `@SEOSquad` | parallel audits → backlinks → design |
| `@AnalyticsSquad` | analyze → plan → critique → decide |
| `@ContentSquad` | write → edit → [summarize\|translate] → strategize |
| `@CodeSquad` | write → review (loop) → bug hunt → architect → test |
| `@VisionSquad` | analyze → embed → synthesize → coordinate |

## MCP bridge

`tools/mcp_bridge.py` exposes the REST API as MCP tools over stdio. Wire it into Cursor (`.cursor/mcp.json`) or OpenCode:

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

The server must be running on `localhost:8000`.

---

## Configuration

All config lives in `.env` → `core/config.py` → `settings` singleton.

| Variable | Default | Notes |
|---|---|---|
| `MODEL_FAST` | `hf.co/evalengine/unbound-e2b-gguf:Q4_K_M` | Used by most agents |
| `MODEL_REASON` | `huihui_ai/gemma-4-abliterated:e4b-q4_K` | Heavy reasoning agents |
| `MODEL_VISION` | `minicpm-v:8b` | Vision/multimodal |
| `MODEL_EMBED` | `nomic-embed-text` | ChromaDB embeddings |
| `AGENT_TIMEOUT` | `120` | Seconds per task (504 on breach) |

## Development

```bash
pip install -r requirements.txt
pytest
```

## Methodology

The `methodology/` folder contains the **12-factor agent** methodology, a third-party work by [humanlayer](https://github.com/humanlayer/12-factor-agents), distributed under the **Apache License 2.0**. See [`methodology/README.md`](methodology/README.md) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and license terms.

## Documentation

- [`AGENTS.md`](AGENTS.md) — developer guide and architecture notes
- [`docs/WINDOWS_SMOKE.md`](docs/WINDOWS_SMOKE.md) — smoke checklist
- [`methodology/`](methodology/) — 12-factor agent methodology (third-party)

## License

Apache License 2.0. See [`LICENSE`](LICENSE). Third-party content is documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
