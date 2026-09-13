"""Release-gate tests: agent count and required attributes."""
import pytest


def test_all_agents_count_is_40():
    """len(ALL_AGENTS) must be exactly 40 for release gate."""
    from agents.registry import ALL_AGENTS
    assert len(ALL_AGENTS) == 40, f"Expected 40 agents, got {len(ALL_AGENTS)}"


def test_all_agents_have_name():
    """Every agent class must have a non-empty name."""
    from agents.registry import ALL_AGENTS
    for AgentClass in ALL_AGENTS:
        agent = AgentClass()
        assert hasattr(agent, "name"), f"{AgentClass} missing 'name'"
        assert agent.name, f"{AgentClass} has empty name"


def test_all_agents_have_description():
    """Every agent class must have a non-empty description."""
    from agents.registry import ALL_AGENTS
    for AgentClass in ALL_AGENTS:
        agent = AgentClass()
        assert hasattr(agent, "description"), f"{AgentClass} missing 'description'"
        assert agent.description, f"{AgentClass} has empty description"


def test_all_agents_names_are_unique():
    """No duplicate agent names allowed."""
    from agents.registry import ALL_AGENTS
    names = [A.name for A in ALL_AGENTS]
    assert len(names) == len(set(names)), "Duplicate agent names found"