"""
Integration tests for the 30-agent system.
Tests cover: agent instantiation, graph routing, tool execution, memory.
"""
import asyncio
from pathlib import Path

import pytest


# ──────────────────────────────────────────────
# Tests: Agent Instantiation
# ──────────────────────────────────────────────
class TestAgentInstantiation:
    def test_all_30_agents_can_be_imported(self):
        from agents.registry import ALL_AGENTS
        # Tier specialists + outreach/SEO extensions + audio_analyst
        assert len(ALL_AGENTS) >= 30, f"Expected >=30 agents, got {len(ALL_AGENTS)}"
        names = {A.name for A in ALL_AGENTS}
        assert "orchestrator" in names
        assert "audio_analyst" in names

    def test_all_agents_have_required_attributes(self):
        from agents.registry import ALL_AGENTS
        for AgentClass in ALL_AGENTS:
            agent = AgentClass()
            assert hasattr(agent, "name"), f"{AgentClass} missing 'name'"
            assert hasattr(agent, "description"), f"{AgentClass} missing 'description'"
            assert hasattr(agent, "system_prompt"), f"{AgentClass} missing 'system_prompt'"
            assert agent.name, f"{AgentClass} has empty name"
            assert agent.description, f"{AgentClass} has empty description"

    def test_agent_names_are_unique(self):
        from agents.registry import ALL_AGENTS
        names = [A.name for A in ALL_AGENTS]
        assert len(names) == len(set(names)), "Duplicate agent names found"

    def test_all_agents_are_callable(self):
        from agents.registry import ALL_AGENTS
        for AgentClass in ALL_AGENTS:
            agent = AgentClass()
            assert callable(agent), f"{AgentClass} is not callable"


# ──────────────────────────────────────────────
# Tests: Graph
# ──────────────────────────────────────────────
class TestGraph:
    def test_graph_builds_successfully(self):
        from agents.registry import register_all_agents
        from core.graph import get_graph
        register_all_agents()
        graph = get_graph()
        assert graph._graph is not None

    def test_graph_has_all_agents_registered(self):
        from agents.registry import ALL_AGENTS, register_all_agents
        from core.graph import get_graph
        register_all_agents()
        graph = get_graph()
        expected = {A.name for A in ALL_AGENTS}
        registered = set(graph._agents.keys())
        assert expected == registered, f"Missing: {expected - registered}"


# ──────────────────────────────────────────────
# Tests: Tools
# ──────────────────────────────────────────────
class TestTools:
    def test_read_existing_file(self):
        from tools.file_ops import read_file, WORKSPACE
        test_file = WORKSPACE / "test_read.txt"
        test_file.write_text("Hello, agent!")
        result = read_file(str(test_file))
        assert "Hello, agent!" in result
        test_file.unlink()

    def test_read_nonexistent_file(self):
        from tools.file_ops import read_file
        result = read_file("/nonexistent/path/file.txt")
        assert "Error" in result or "not found" in result.lower()

    def test_write_and_read_file(self):
        from tools.file_ops import read_file, write_file, WORKSPACE
        test_file = WORKSPACE / "test_write.txt"
        write_result = write_file(str(test_file), "Test content")
        assert "Written" in write_result
        read_result = read_file(str(test_file))
        assert "Test content" in read_result
        test_file.unlink()

    async def test_safe_exec_basic(self):
        from tools.code_exec import safe_exec
        result = await safe_exec("x = 2 + 2\nprint(x)")
        assert "4" in result

    async def test_safe_exec_blocks_import(self):
        from tools.code_exec import safe_exec
        result = await safe_exec("import os\nos.system('rm -rf /')")
        # Should fail or block
        assert "Error" in result or "None" in result or "error" in result.lower()

    async def test_safe_exec_timeout(self):
        from tools.code_exec import safe_exec
        result = await safe_exec("while True: pass", timeout=2.0)
        assert "timed out" in result.lower()


# ──────────────────────────────────────────────
# Tests: Config
# ──────────────────────────────────────────────
class TestConfig:
    def test_settings_load(self, app_settings):
        assert app_settings.ollama_host.startswith("http")
        assert app_settings.model_fast
        assert app_settings.model_reason
        assert app_settings.model_embed
        assert app_settings.model_vision
        assert app_settings.redis_port == 6379
        assert app_settings.api_port == 8000

    def test_log_dir_created(self, app_settings):
        assert Path(app_settings.log_dir).exists()

    def test_chroma_dir_created(self, app_settings):
        assert Path(app_settings.chroma_persist_dir).parent.exists()


# ──────────────────────────────────────────────
# Tests: Agent execute() with mock LLM
# ──────────────────────────────────────────────
class TestAgentExecution:
    """Tests that mock Ollama to avoid requiring a running instance."""

    @pytest.fixture
    def mock_state(self):
        return {
            "messages": [],
            "next_agent": "orchestrator",
            "task": "Write hello world in Python",
            "context": {},
            "result": None,
            "error": None,
            "retries": 0,
            "session_id": "test-session",
            "user_id": "test-user",
        }

    async def test_summarizer_execute(self, mock_state, monkeypatch):
        from agents.tier4 import SummarizerAgent

        async def mock_llm(self_inner, prompt, **kwargs):
            return "This is a summary of the content."

        monkeypatch.setattr("agents.base.BaseAgent.llm", mock_llm)

        agent = SummarizerAgent()
        mock_state["context"]["content"] = "Long text to summarize " * 50
        result = await agent.execute(mock_state)

        assert "result" in result
        assert result["next_agent"] == "END"

    async def test_code_writer_execute(self, mock_state, monkeypatch):
        from agents.tier3 import CodeWriterAgent

        async def mock_llm(self_inner, prompt, **kwargs):
            return "```python\nprint('Hello, World!')\n```"

        monkeypatch.setattr("agents.base.BaseAgent.llm", mock_llm)

        agent = CodeWriterAgent()
        result = await agent.execute(mock_state)

        assert "result" in result
        assert "python" in result["result"].lower() or "print" in result["result"]


# ──────────────────────────────────────────────
# Tests: Memory (ChromaDB - no Ollama needed mock)
# ──────────────────────────────────────────────
class TestMemory:
    async def test_memory_store_and_search(self, monkeypatch, tmp_path):
        """Test memory store/search with mocked embeddings."""
        import core.memory as mem_module

        async def mock_embed(self_inner, model, text):
            # Return consistent fake embeddings based on text hash
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            return [(h >> (i * 4)) % 256 / 256.0 for i in range(384)]

        monkeypatch.setattr("core.ollama_client.OllamaClient.embed", mock_embed)

        # Use a temp directory for this test
        import chromadb
        client = chromadb.PersistentClient(path=str(tmp_path))
        mem = mem_module.MemoryManager()
        mem._client = client
        mem._collections = {}

        doc_id = await mem.store(
            text="The sky is blue",
            metadata={"test": True},
            namespace="test",
        )
        assert doc_id

        results = await mem.search("sky color", n_results=1, namespace="test")
        # Results may be empty with fake embeddings but no error
        assert isinstance(results, list)
