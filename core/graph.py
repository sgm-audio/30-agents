"""
LangGraph state definitions and graph builder for the 30-agent system.
The graph routes tasks from the Orchestrator to specialized agents.
"""
import asyncio
from typing import Annotated, Any, Optional, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────
# Shared State Schema
# ──────────────────────────────────────────────
class AgentState(TypedDict):
    # Conversation history (auto-appended via add_messages reducer)
    messages: Annotated[list, add_messages]
    # Which agent should handle the next step
    next_agent: str
    # The current task description
    task: str
    # Accumulated context / artifacts produced so far
    context: dict[str, Any]
    # Final answer (set by whichever agent finishes)
    result: Optional[str]
    # Error tracking
    error: Optional[str]
    # Retry counter
    retries: int
    # Session metadata
    session_id: str
    user_id: str
    # Routing trace: ordered list of agent names visited
    agent_path: list[str]


# ──────────────────────────────────────────────
# Graph Factory
# ──────────────────────────────────────────────
class AgentGraph:
    """
    Builds and runs the LangGraph workflow.
    Agents register themselves via `register()`.
    """

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._graph = None

    def register(self, name: str, agent_fn):
        """Register an async callable as a graph node.

        Wraps the callable to append the agent's name to state["agent_path"]
        so the full routing trace is available after the graph finishes.
        """
        async def _tracked(state: AgentState) -> dict:
            out = await agent_fn(state)
            path = list(state.get("agent_path") or [])
            path.append(name)
            if isinstance(out, dict):
                out["agent_path"] = path
            return out

        self._agents[name] = _tracked
        log.info("graph.registered", agent=name)

    def build(self):
        """Compile the graph after all agents are registered."""
        builder = StateGraph(AgentState)

        # Add all agent nodes
        for name, fn in self._agents.items():
            builder.add_node(name, fn)

        # Entry point: always start at orchestrator
        builder.add_edge(START, "orchestrator")

        # Dynamic routing: orchestrator sets state["next_agent"]
        def route(state: AgentState) -> str:
            nxt = state.get("next_agent", "")
            if nxt == "END" or not nxt or state.get("result"):
                return END
            if nxt not in self._agents:
                log.warning("graph.unknown_agent", agent=nxt)
                return END
            return nxt

        builder.add_conditional_edges("orchestrator", route)

        # All non-orchestrator agents route back to orchestrator
        # (unless they set result directly)
        for name in self._agents:
            if name != "orchestrator":
                builder.add_conditional_edges(
                    name,
                    lambda s: END if s.get("result") else "orchestrator",
                )

        self._graph = builder.compile()
        log.info("graph.compiled", nodes=list(self._agents.keys()))
        return self._graph

    async def run(self, task: str, session_id: str = "default", user_id: str = "user") -> AgentState:
        """Execute the graph for a given task."""
        if self._graph is None:
            self.build()

        initial_state: AgentState = {
            "messages": [],
            "next_agent": "orchestrator",
            "task": task,
            "context": {},
            "result": None,
            "error": None,
            "retries": 0,
            "session_id": session_id,
            "user_id": user_id,
            "agent_path": [],
        }

        log.info("graph.run.start", task=task[:80], session=session_id)
        final_state = await self._graph.ainvoke(
            initial_state,
            config={"recursion_limit": 50},
        )
        log.info("graph.run.done", result_len=len(final_state.get("result") or ""))
        return final_state


# Singleton
# NOTE: check-then-create is not thread-safe, but acceptable here because:
# 1) This is async single-threaded (no preemption between check and assign)
# 2) Worst case is two AgentGraph instances; second overwrites first (harmless)
_graph_instance: Optional[AgentGraph] = None


def get_graph() -> AgentGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = AgentGraph()
    return _graph_instance
