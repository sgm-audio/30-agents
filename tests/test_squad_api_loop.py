"""Unit tests for squad REST loop helper (no live LLM)."""
from __future__ import annotations

import pytest

from core.graph import AgentState
from squads.api import merge_state, run_squad_loop, MAX_SQUAD_HOPS


def _base_state(**kwargs) -> AgentState:
    state: AgentState = {
        "messages": [],
        "next_agent": "content_squad",
        "task": "write one sentence",
        "context": {},
        "result": None,
        "error": None,
        "retries": 0,
        "session_id": "test",
        "user_id": "test",
        "agent_path": [],
    }
    state.update(kwargs)  # type: ignore[typeddict-item]
    return state


class FakeLeader:
    """Mimics SquadLeader: first hop routes, second hop finishes."""

    name = "fake_squad"

    def __init__(self):
        self.calls = 0

    async def __call__(self, state: AgentState) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "context": {"squad_stage": "delegating", "squad_member": "writer"},
                "next_agent": "writer",
            }
        return {
            "context": {"squad_stage": "delegating", "squad_member": "writer"},
            "result": "[FAKE SQUAD Complete]\nhello",
            "next_agent": "END",
        }


class NeverEndingLeader:
    name = "loop_squad"

    async def __call__(self, state: AgentState) -> dict:
        return {
            "context": {"squad_member": "writer"},
            "next_agent": "writer",
        }


@pytest.mark.asyncio
async def test_run_squad_loop_completes():
    leader = FakeLeader()
    final, members = await run_squad_loop(leader, _base_state())
    assert leader.calls == 2
    assert "Complete" in (final.get("result") or "")
    assert members == ["writer"]


@pytest.mark.asyncio
async def test_run_squad_loop_max_hops():
    final, _ = await run_squad_loop(
        NeverEndingLeader(),  # type: ignore[arg-type]
        _base_state(),
        max_hops=3,
    )
    assert final.get("error") == "max_hops_exceeded"
    assert "3 hops" in (final.get("result") or "")


def test_merge_state_merges_context():
    state = _base_state(context={"a": 1})
    merged = merge_state(state, {"context": {"b": 2}, "task": "new"})
    assert merged["context"] == {"a": 1, "b": 2}
    assert merged["task"] == "new"
    assert MAX_SQUAD_HOPS >= 5
