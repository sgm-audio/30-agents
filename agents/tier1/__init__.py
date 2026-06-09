"""
TIER 1 - CORE INFRASTRUCTURE AGENTS
Agents 1-5: Orchestrator, Memory Manager, Context Tracker, Tool Dispatcher, State Machine
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from agents.base import BaseAgent, extract_json
from core.config import settings
from core.graph import AgentState
from core.memory import get_memory
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

__all__ = [
    "OrchestratorAgent",
    "MemoryManagerAgent",
    "ContextTrackerAgent",
    "ToolDispatcherAgent",
    "StateMachineAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 1: Orchestrator
# ══════════════════════════════════════════════════════════════
class OrchestratorAgent(BaseAgent):
    """
    Routes incoming tasks to the appropriate specialist agent.
    Acts as the entry point and coordinator of the graph.
    """

    name = "orchestrator"
    description = "Routes tasks to appropriate specialist agents"
    model = settings.model_fast
    system_prompt = """You are the central orchestrator of a 30-agent cognitive system.
Analyze the user's task and decide which specialized agent should handle it.

Available agents:
TIER 1 (Infrastructure): memory_manager, context_tracker, tool_dispatcher, state_machine
TIER 2 (Research): web_researcher, doc_reader, knowledge_synthesizer, fact_verifier, knowledge_base, semantic_searcher
TIER 3 (Code): code_writer, code_reviewer, bug_hunter, system_architect, test_engineer
TIER 4 (Content): writer, summarizer, translator, editor, content_strategist
TIER 5 (Analysis): data_analyst, logic_engine, planner, critic, decision_engine, methodology_advisor
TIER 6 (Multimodal): vision_analyst, embedding_engine, multimodal_synthesizer, media_coordinator

Respond with ONLY a JSON object:
{"next_agent": "<agent_name>", "reasoning": "<brief explanation>", "subtask": "<refined task for the agent>"}

If the task is complete or cannot be handled, set next_agent to "END".
"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        mem = get_memory()

        try:
            # Determine operation from task
            if any(w in task.lower() for w in ["store", "save", "remember", "memorize"]):
                # Store operation
                content_to_store = context.get("content", task)
                doc_id = await mem.store(
                    text=content_to_store,
                    metadata={"task": task, "session": state["session_id"]},
                    namespace="global",
                )
                result = f"Stored in memory with ID: {doc_id}"
            else:
                # Search/retrieve operation
                memories = await mem.search(query=task, n_results=5, namespace="global")
                if memories:
                    formatted = "\n".join(
                        f"[{i+1}] (dist={m['distance']:.3f}) {m['text'][:200]}"
                        for i, m in enumerate(memories)
                    )
                    result = f"Found {len(memories)} relevant memories:\n{formatted}"
                else:
                    result = "No relevant memories found."
        except Exception as e:
            return self.error_result(f"Memory operation failed: {e}")

        new_context = dict(context)
        new_context["memory_result"] = result

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }

        # Build routing prompt
        history_summary = ""
        if context:
            history_summary = f"\nPrevious context: {json.dumps(context, indent=2)[:500]}"

        prompt = f"Task: {task}{history_summary}\n\nRoute this task to the best agent."

        response = await self.llm(prompt)

        # Parse JSON response
        try:
            routing = extract_json(response)
        except Exception as e:
            log.warning("orchestrator.parse_fail", error=str(e), response=response[:200])
            # Fallback: infer from task content
            code_keywords = ("code", "function", "bug", "debug", "test", "compile", "class", "method", "refactor")
            fallback_agent = "code_writer" if any(kw in task.lower() for kw in code_keywords) else "writer"
            routing = {"next_agent": fallback_agent, "subtask": task}

        next_agent = routing.get("next_agent", "orchestrator")
        subtask = routing.get("subtask", task)

        log.info("orchestrator.route", next=next_agent, reason=routing.get("reasoning", "")[:80])

        # Update context with routing decision
        new_context = dict(context)
        new_context["last_route"] = next_agent
        new_context["refined_task"] = subtask

        return {
            "next_agent": next_agent,
            "task": subtask,
            "context": new_context,
            "retries": retries + 1,
        }


# ══════════════════════════════════════════════════════════════
# Agent 2: Memory Manager
# ══════════════════════════════════════════════════════════════
class MemoryManagerAgent(BaseAgent):
    """Manages ChromaDB operations: store, retrieve, summarize memories."""

    name = "memory_manager"
    description = "Manages vector memory storage and retrieval"
    model = settings.model_fast
    system_prompt = """You are the Memory Manager for an AI system.
Your job is to:
1. Store important information in long-term vector memory
2. Retrieve relevant memories for a given query
3. Summarize and consolidate memory fragments
4. Decide what is worth remembering vs. ephemeral

Always return structured results."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        mem = get_memory()

        try:
            # Determine operation from task
            if any(w in task.lower() for w in ["store", "save", "remember", "memorize"]):
                # Store operation
                content_to_store = context.get("content", task)
                doc_id = await mem.store(
                    text=content_to_store,
                    metadata={"task": task, "session": state["session_id"]},
                    namespace="global",
                )
                result = f"Stored in memory with ID: {doc_id}"
            else:
                # Search/retrieve operation
                memories = await mem.search(query=task, n_results=5, namespace="global")
                if memories:
                    formatted = "\n".join(
                        f"[{i+1}] (dist={m['distance']:.3f}) {m['text'][:200]}"
                        for i, m in enumerate(memories)
                    )
                    result = f"Found {len(memories)} relevant memories:\n{formatted}"
                else:
                    result = "No relevant memories found."
        except Exception as e:
            return self.error_result(f"Memory operation failed: {e}")

        new_context = dict(context)
        new_context["memory_result"] = result

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 3: Context Tracker
# ══════════════════════════════════════════════════════════════
class ContextTrackerAgent(BaseAgent):
    """Maintains and compresses session context to prevent context overflow."""

    name = "context_tracker"
    description = "Tracks and compresses conversation context"
    model = settings.model_fast
    system_prompt = """You are the Context Tracker. Your job is to:
1. Summarize long conversation histories into concise context
2. Extract key facts and decisions from the context
3. Identify what information is still relevant vs. stale
4. Maintain a running summary of the session

Return a JSON with: {"summary": "...", "key_facts": [...], "next_agent": "..."}"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        messages = state.get("messages", [])
        context = state.get("context", {})
        session_id = state["session_id"]

        try:
            # Compress if messages > 10
            if len(messages) > 10:
                history_text = "\n".join(
                    f"{m.get('type', 'msg')}: {str(m.get('content', ''))[:200]}"
                    for m in messages[-10:]
                )
                summary_prompt = f"""Compress this conversation history into a 200-word summary.
Extract key facts, decisions, and pending items.

History:
{history_text}"""
                summary = await self.llm(summary_prompt)
            else:
                summary = context.get("summary", "Session just started.")

            # Store context in Redis
            redis = get_redis()
            await redis.hset(
                f"session:{session_id}",
                {"summary": summary, "message_count": len(messages)},
            )
        except Exception as e:
            return self.error_result(f"Context tracking failed: {e}")

        new_context = dict(context)
        new_context["summary"] = summary

        return {
            "context": new_context,
            "next_agent": "orchestrator",
        }


# ══════════════════════════════════════════════════════════════
# Agent 4: Tool Dispatcher
# ══════════════════════════════════════════════════════════════
class ToolDispatcherAgent(BaseAgent):
    """Dispatches calls to external tools (filesystem, search, code exec)."""

    name = "tool_dispatcher"
    description = "Executes external tools and returns results"
    model = settings.model_fast
    system_prompt = """You are the Tool Dispatcher. You coordinate calls to:
- File system tools (read, write, list files)
- Web search tools
- Code execution sandbox
- System utilities

Given a task, determine which tool to use and format the result."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        # Determine tool from task
        tool_result = ""

        if any(w in task.lower() for w in ["read file", "open file", "cat "]):
            from tools.file_ops import read_file
            filepath = context.get("filepath", "")
            if filepath:
                tool_result = read_file(filepath)
            else:
                tool_result = "Error: no filepath specified in context"

        elif any(w in task.lower() for w in ["search", "find online", "look up"]):
            try:
                from duckduckgo_search import DDGS
                query = context.get("query", task)
                with DDGS() as ddgs:
                    hits = list(ddgs.text(query, max_results=5))
                if hits:
                    lines = [f"{i+1}. {h['title']}\n   {h['href']}\n   {h['body'][:200]}"
                             for i, h in enumerate(hits)]
                    tool_result = "Web search results:\n\n" + "\n\n".join(lines)
                else:
                    tool_result = f"No results found for: {query}"
            except Exception as e:
                tool_result = f"Web search failed: {e}"

        elif any(w in task.lower() for w in ["run", "execute"]):
            from tools.code_exec import safe_exec
            code = context.get("code", "")
            if code:
                tool_result = await safe_exec(code)
            else:
                tool_result = "Error: no code specified in context"
        else:
            tool_result = f"No matching tool for task: {task}"

        new_context = dict(context)
        new_context["tool_result"] = tool_result

        return {
            "context": new_context,
            "result": tool_result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 5: State Machine
# ══════════════════════════════════════════════════════════════
class StateMachineAgent(BaseAgent):
    """
    Manages persistent workflow state: tracks multi-step task progress,
    handles pauses, resumes, and cancellations.
    """

    name = "state_machine"
    description = "Manages multi-step workflow state and progress tracking"
    model = settings.model_fast
    system_prompt = """You are the State Machine agent. You manage long-running workflows by:
1. Breaking tasks into discrete steps
2. Tracking which steps are complete
3. Resuming interrupted workflows
4. Detecting when workflows are stuck

Return JSON: {"steps": [...], "current_step": N, "status": "running|paused|complete", "next_agent": "..."}"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        session_id = state["session_id"]
        redis = get_redis()

        # Check for existing workflow state
        wf_key = f"workflow:{session_id}"
        existing = await redis.hgetall(wf_key)

        if not existing:
            # New workflow: decompose task into steps
            decompose_prompt = f"""Break this task into 3-7 concrete steps:
Task: {task}

Return as JSON: {{"steps": ["step1", "step2", ...], "current_step": 0}}"""
            response = await self.llm(decompose_prompt)
            try:
                wf_data = extract_json(response)
            except Exception:
                wf_data = {"steps": [task], "current_step": 0}

            await redis.hset(wf_key, {**wf_data, "status": "running"})
            await redis.expire(wf_key, 3600)
        else:
            wf_data = existing

        steps = wf_data.get("steps", [task])
        current = int(wf_data.get("current_step", 0))

        if current < len(steps):
            current_step_task = steps[current]
            # Advance step counter
            await redis.hset(wf_key, {"current_step": current + 1})

            new_context = dict(context)
            new_context["workflow_step"] = current + 1
            new_context["workflow_total"] = len(steps)
            new_context["current_step_task"] = current_step_task

            return {
                "task": current_step_task,
                "context": new_context,
                "next_agent": "orchestrator",
            }
        else:
            await redis.hset(wf_key, {"status": "complete"})
            return {
                "result": "All workflow steps completed.",
                "next_agent": "END",
            }
