# 30-Agents Active TODO

> Live backlog. Items marked ✅ are done; 🔄 in progress; ⏳ pending.

---

## 🔴 Critical / In Progress

### 1. 🔄 **Orchestrator routing regression test**
- **What:** Add test confirming orchestrator routes to specialists (not memory manager)
- **Why:** The bug was a copy-paste that returned early; need regression guard
- **Context:** Fixed in `agents/tier1/__init__.py:59` — old body was dead code
- **Files:** `tests/test_agents.py` (new test in `TestAgentExecution`)
- **Depends on:** None

---

## 🟠 High Impact

### 2. ⏳ **Memory warm-start / empty-state UX**
- **What:** On first launch, ChromaDB is empty → "No relevant memories found" for every query
- **Why:** Users see useless response until they manually seed memory
- **Options:**
  - A) Auto-seed system knowledge on first run (architecture, capabilities, agent list)
  - B) Orchestrator handles empty memory gracefully with a helpful default response
  - C) Show welcome hint in UI when memory is empty
- **Files:** `core/memory.py`, `agents/tier1/__init__.py`, `api/ui/index.html`
- **Depends on:** None

### 3. ⏳ **Verify end-to-end chat flow works**
- **What:** Manual/automated test that user message → WebSocket → orchestrator → specialist → response
- **Why:** Ensure the fix actually routes to specialists now
- **Files:** `api/server.py` (WebSocket), `core/graph.py`, `agents/registry.py`
- **Depends on:** #1

### 4. ⏳ **Health endpoint LLM backend reporting**
- **What:** `/api/health` reports `llm_backend` correctly (already in NIM backend PR)
- **Why:** Verify NIM vs Ollama selection works end-to-end
- **Status:** Code merged, needs manual verification
- **Depends on:** Ollama running locally

---

## 🟡 Medium

### 5. ⏳ **Agent detail view in sidebar**
- **What:** Click agent in sidebar → show capabilities, model, example tasks
- **Why:** Browser shows list but no detail; users need to know what each agent does
- **Files:** `api/ui/index.html` (add modal/panel), `/api/agents` already has data
- **Depends on:** None

### 6. ⏳ **Squad detail view + run from UI**
- **What:** Click squad card → show members, routing rules, "Run" button
- **Why:** Squads are powerful but only accessible via API/CLI currently
- **Files:** `api/ui/index.html`, `/api/squads/{name}/run`
- **Depends on:** None

### 7. ⏳ **Streaming response UX**
- **What:** Show partial tokens as they arrive (currently waits for full result)
- **Why:** Long-running agents feel slow; streaming improves perceived performance
- **Files:** `api/server.py` (WebSocket `type: 'stream'`), `index.html` (incremental render)
- **Depends on:** #3

---

## 🟢 Nice to Have

### 8. ⏳ **Command palette (⌘K)**
- **What:** Fuzzy search agents/squads/actions from keyboard
- **Why:** Power users want fast access; sidebar takes screen space
- **Files:** `api/ui/index.html`
- **Depends on:** #5

### 9. ⏳ **Agent chaining visualization**
- **What:** Show `agent_path` trace after run (graph of who called whom)
- **Why:** Debugging & transparency; the trace exists in state but isn't shown
- **Files:** `api/ui/index.html`, `core/graph.py` (already tracks `agent_path`)
- **Depends on:** #3

### 10. ⏳ **Autopilot UI**
- **What:** Create/list/run autopilots from browser (daily scrape, weekly SEO, etc.)
- **Why:** Autopilot scheduler exists in `core/autopilot_scheduler.py` but no UI
- **Files:** `api/ui/index.html`, `/api/autopilots/*`
- **Depends on:** None

---

## 📋 Maintenance

### 11. ⏳ **Update AGENTS.md config table with LLM_BACKEND**
- **What:** `AGENTS.md` config section already updated in NIM backend PR — verify it's current
- **Status:** Likely done, confirm
- **Depends on:** None

### 12. ⏳ **Consolidate TODO.md**
- **What:** Current `TODO.md` is a completed-work log; replace with this active backlog
- **Why:** Single source of truth for what's next
- **Files:** `TODO.md`
- **Depends on:** This list

---

## ✅ Recently Completed (for reference)

| Item | PR / Commit |
|------|-------------|
| Portfolio docs (PRD, ADR-001, README) | PR #5 |
| `tools/file_ops.py` import fix | PR #6 |
| Pluggable LLM backend (NIM default, Ollama opt-in) | PR #8 |
| Dynamic agent/squad browser sidebar | `9b7f206` |
| Orchestrator routing bug fix | *this session* |

---

## 🚫 Not in Scope (explicitly deferred)

- Multi-tenant SaaS hosting
- Human-in-the-loop approval tools (12-factor #7)
- Custom squad builder UI
- Per-agent backend override (heavy → NIM, cheap → Ollama)
- Dark/light theme toggle
- Custom Modelfile management UI