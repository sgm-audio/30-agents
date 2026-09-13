# Definition of Done — 30-Agents System

- [ ] **Server starts with no API_SECRET**: health endpoint returns ok; all 40 agents from `agents/registry.py ALL_AGENTS` load; 6 squad pipelines registered.
- [ ] **Frontend at / loads with no prompt**: chat UI appears at http://127.0.0.1:8000/ without requiring user input.
- [ ] **4 actions send via WS**: Find leads, SEO audit, Write outreach, Improve repo each dispatch WebSocket message on execution.
- [ ] **All 40 agents callable via POST /api/chat**: every agent in `ALL_AGENTS` responds to `/api/chat` with task routing.
- [ ] **6 squad pipelines run via POST /api/squads/{name}/run**: outreach, seo, analytics, content, code, vision squads execute end-to-end.
- [ ] **CLI commands**: `serve`, `health`, `agents`, `chat`, `squad run`, `outreach` all functional.
- [ ] **MCP tools in `tools/mcp_bridge.py` all 14 work**: `agent_chat`, `list_agents`, `list_squads`, `run_squad`, `outreach_scrape`, `outreach_enrich`, `outreach_generate`, `outreach_send`, `outreach_pipeline`, `seo_analyze`, `seo_backlinks`, `seo_pipeline`, `design_concept`, `health_check`.
- [ ] **Verification commands list**: `python main.py health`, `python main.py agents`, `python main.py chat "<task>"`, `python main.py squad run <name>`, `python main.py outreach --city Vancouver --max-leads 10`, `python main.py squad run seo --url <url>`.