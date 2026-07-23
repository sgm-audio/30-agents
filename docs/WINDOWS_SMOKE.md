# Windows smoke checklist

Run after clone, dependency changes, or before a demo. Goal: prove Redis + API + one agent path + one squad path work.

## 0. Prerequisites

- [ ] Python 3.12+ available
- [ ] Ollama installed (optional for API boot; required for real inference)
- [ ] Redis reachable on `6379` (Docker `redis-agent`, system Redis, or `./start`)

## 1. Bring the stack up

```powershell
cd C:\Users\you\OneDrive\Desktop\30_agents
# Preferred:
.\Start-Agents.bat
# Or:
.\venv\Scripts\python.exe main.py serve
# Or (bash-ish):
# ./start
```

- [ ] Browser opens `http://127.0.0.1:8000/` (or open it manually)
- [ ] No crash in the launcher / terminal within ~30s

## 2. Health

```powershell
curl.exe -s http://127.0.0.1:8000/api/health
```

Expect JSON with:

| Field | Pass |
|-------|------|
| `redis` | `true` |
| `status` | `"ok"` if Ollama up; `"degraded"` is OK if Ollama is off (API still up) |
| `ollama` | `true` for full inference smoke |

- [ ] Health responds (not connection refused)

## 3. Agents list

```powershell
curl.exe -s http://127.0.0.1:8000/api/agents
```

- [ ] Returns a non-empty agent list

## 4. One chat (orchestrator path)

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/chat `
  -H "Content-Type: application/json" `
  -d "{\"task\": \"Summarize this in one sentence: Redis stores session state for agents.\", \"session_id\": \"smoke-chat-1\"}"
```

- [ ] HTTP 200 (or documented timeout only if Ollama is cold / missing)
- [ ] Body has a `result` or clear `error` (not an unhandled 500)

Without Ollama, chat may fail on LLM call — that is a **models** failure, not an API boot failure. Record which.

## 5. One squad

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/squads/content/run `
  -H "Content-Type: application/json" `
  -d "{\"task\": \"Write one sentence about local multi-agent systems.\"}"
```

Or CLI:

```powershell
.\venv\Scripts\python.exe main.py squad run content --task "Write one sentence about local multi-agent systems."
```

- [ ] Request completes without process crash
- [ ] Note: REST squad run may return a thin result (`No result produced`) — known limitation if LangGraph loop is not fully driven; CLI/`/api/chat` is the stronger path

## 6. Fast tests (no live LLM required for most)

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_mcp_bridge.py -q
```

- [ ] MCP bridge tests pass

Optional broader:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

- [ ] Note known stale failures separately (e.g. agent-count assertion drift) — do not block smoke on pre-existing skips

## 7. Models (only if testing real inference)

```powershell
.\venv\Scripts\python.exe main.py pull-models
# or:
.\venv\Scripts\python.exe scripts\pull_models.py
```

- [ ] `nomic-embed-text` present at minimum
- [ ] Fast/reason/vision models present if you care about those agents

Optional: run `.\scripts\schedule_pull_models.ps1` once to register an hourly Windows Scheduled Task that retries missing/interrupted pulls automatically.

## 8. Shut down

```powershell
.\Stop-Agents.bat
```

- [ ] Port 8000 freed (`curl` fails with connection refused)

## Pass / fail log

| Date | Health | Chat | Squad | pytest MCP | Notes |
|------|--------|------|-------|------------|-------|
|      |        |      |       |            |       |
