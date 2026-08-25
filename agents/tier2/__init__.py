"""
TIER 2 - RESEARCH & KNOWLEDGE AGENTS
Agents 6-11: Web Researcher, Doc Reader, Knowledge Synthesizer,
             Fact Verifier, Knowledge Base, Semantic Searcher
"""
from __future__ import annotations

from typing import Any

import structlog

from agents.base import BaseAgent
from core.config import settings
from core.graph import AgentState
from core.memory import get_memory
from core.safety import resolve_workspace_path, validate_public_http_url

log = structlog.get_logger(__name__)

__all__ = [
    "WebResearcherAgent",
    "DocReaderAgent",
    "KnowledgeSynthesizerAgent",
    "FactVerifierAgent",
    "KnowledgeBaseAgent",
    "SemanticSearcherAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 6: Web Researcher
# ══════════════════════════════════════════════════════════════
class WebResearcherAgent(BaseAgent):
    """Fetches and summarizes web content using httpx."""

    name = "web_researcher"
    description = "Searches and fetches web content"
    model = settings.model_fast
    system_prompt = """You are a research expert. Given source content from the web,
extract key facts, summarize findings, and highlight the most relevant information
for the user's query. Be concise and cite specific details."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        import httpx
        from html2text import html2text

        task = state["task"]
        context = state.get("context", {})
        url = context.get("url", "")
        safe_url = None

        if url:
            safe_url = validate_public_http_url(url)
            if not safe_url:
                md_content = f"Blocked unsafe URL: {url}"
            else:
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
                        resp = await client.get(safe_url, headers=headers)
                        resp.raise_for_status()
                        md_content = html2text(resp.text)[:4000]
                except Exception:
                    log.exception("research_agent_fetch_failed", url=safe_url)
                    md_content = f"Failed to fetch {safe_url}"
        else:
            md_content = f"[No URL provided. Would search for: {task}]"

        summary = await self.llm(
            prompt=f"Research task: {task}\n\nSource content:\n{md_content}\n\nSummarize the key findings:",
        )

        # Store in memory
        await self.remember(summary, metadata={"source": (safe_url or "") if url else "", "task": task})

        new_context = dict(context)
        new_context["research_result"] = summary

        return {
            "context": new_context,
            "result": summary,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 7: Document Reader
# ══════════════════════════════════════════════════════════════
class DocReaderAgent(BaseAgent):
    """Reads and extracts content from PDFs and Word documents."""

    name = "doc_reader"
    description = "Reads and extracts content from documents (PDF, DOCX, TXT)"
    model = settings.model_reason
    system_prompt = """You are a document analysis expert. Extract and organize
information from documents. Identify: main topics, key facts, structure, and
actionable insights. Format your output clearly."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        filepath = context.get("filepath", "")

        content = ""
        if isinstance(filepath, str) and filepath.strip():
            filepath = filepath.strip()
            if "\x00" in filepath:
                content = f"Access denied for file path: {filepath}"
            else:
                path = resolve_workspace_path(filepath)
                if path is None:
                    content = f"Access denied for file path: {filepath}"
                elif path.suffix.lower() not in (".pdf", ".docx", ".doc", ".txt"):
                    content = f"Unsupported file type for path: {filepath}"
                elif not path.exists():
                    content = f"File not found: {filepath}"
                elif path.suffix.lower() == ".pdf":
                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(str(path))
                        content = "\n".join(page.extract_text() or "" for page in reader.pages)
                        content = content[:8000]
                    except Exception as e:
                        content = f"PDF read error: {e}"
                elif path.suffix.lower() in (".docx", ".doc"):
                    try:
                        from docx import Document
                        doc = Document(str(path))
                        content = "\n".join(p.text for p in doc.paragraphs)
                        content = content[:8000]
                    except Exception as e:
                        content = f"DOCX read error: {e}"
                else:
                    try:
                        content = path.read_text(encoding="utf-8", errors="replace")[:8000]
                    except Exception as e:
                        content = f"Read error: {e}"
        else:
            content = f"[No filepath provided for task: {task}]"

        analysis = await self.llm(
            prompt=f"Task: {task}\n\nDocument content:\n{content}\n\nProvide analysis:",
        )

        # Store extracted content in memory
        if content and len(content) > 50:
            await self.remember(
                content[:2000],
                metadata={"source": filepath, "type": "document"},
                namespace="documents",
            )

        new_context = dict(context)
        new_context["doc_analysis"] = analysis

        return {
            "context": new_context,
            "result": analysis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 8: Knowledge Synthesizer
# ══════════════════════════════════════════════════════════════
class KnowledgeSynthesizerAgent(BaseAgent):
    """Combines information from multiple sources into coherent knowledge."""

    name = "knowledge_synthesizer"
    description = "Synthesizes knowledge from multiple sources"
    model = settings.model_reason
    system_prompt = """You are a knowledge synthesis expert. Your job is to:
1. Combine information from multiple sources
2. Identify patterns, connections, and contradictions
3. Create coherent, well-structured summaries
4. Highlight gaps in knowledge
5. Produce actionable insights

Always cite which source each insight came from."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        try:
            # Gather all context fragments
            sources = []
            for key in ["research_result", "doc_analysis", "memory_result", "tool_result"]:
                if key in context:
                    sources.append(f"[{key}]: {context[key]}")

            # Also search memory for relevant info
            memories = await self.recall(task, n=5, namespace="global")
            for m in memories:
                if m["distance"] < 0.5:  # Only close matches
                    sources.append(f"[memory]: {m['text'][:300]}")

            sources_text = "\n\n".join(sources) if sources else "No prior context available."

            synthesis = await self.llm(
                prompt=f"Task: {task}\n\nSources:\n{sources_text}\n\nSynthesize a comprehensive answer:",
            )

            await self.remember(synthesis, metadata={"task": task, "type": "synthesis"})
        except Exception as e:
            return self.error_result(f"Knowledge synthesis failed: {e}")

        new_context = dict(context)
        new_context["synthesis"] = synthesis

        return {
            "context": new_context,
            "result": synthesis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 9: Fact Verifier
# ══════════════════════════════════════════════════════════════
class FactVerifierAgent(BaseAgent):
    """Checks claims against known facts and identifies potential inaccuracies."""

    name = "fact_verifier"
    description = "Verifies facts and identifies inaccuracies"
    model = settings.model_reason
    system_prompt = """You are a fact-checking expert. For each claim presented:
1. Assess its plausibility based on your knowledge
2. Identify potential issues or inaccuracies
3. Rate confidence: HIGH / MEDIUM / LOW / UNCERTAIN
4. Suggest how to verify if unsure
5. Never make up sources

Be objective and intellectually honest."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        try:
            content_to_check = context.get("synthesis", context.get("result", task))

            verification = await self.llm(
                prompt=f"Fact-check the following:\n\n{content_to_check}\n\n"
                       f"Original query: {task}\n\n"
                       f"Provide a detailed fact-check report:",
            )
        except Exception as e:
            return self.error_result(f"Fact verification failed: {e}")

        new_context = dict(context)
        new_context["fact_check"] = verification

        return {
            "context": new_context,
            "result": verification,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 10: Knowledge Base
# ══════════════════════════════════════════════════════════════
class KnowledgeBaseAgent(BaseAgent):
    """Manages the persistent structured knowledge base."""

    name = "knowledge_base"
    description = "Manages structured knowledge storage and retrieval"
    model = settings.model_fast
    system_prompt = """You are the Knowledge Base manager. You:
1. Store structured knowledge (facts, procedures, relationships)
2. Retrieve relevant knowledge for queries
3. Update outdated knowledge
4. Organize knowledge by topic and confidence level"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        mem = get_memory()

        try:
            operation = "search"
            if any(w in task.lower() for w in ["add", "store", "save", "learn", "remember"]):
                operation = "store"

            if operation == "store":
                content = context.get("content", task)
                topic = context.get("topic", "general")
                doc_id = await mem.store(
                    text=content,
                    metadata={"topic": topic, "type": "knowledge", "task": task},
                    namespace="knowledge_base",
                )
                result = f"Knowledge stored: {doc_id}"
            else:
                results = await mem.search(
                    query=task,
                    n_results=8,
                    namespace="knowledge_base",
                )
                if results:
                    formatted = "\n".join(
                        f"- {r['text'][:250]} (relevance: {1-r['distance']:.2f})"
                        for r in results
                    )
                    result = f"Found {len(results)} knowledge entries:\n{formatted}"
                else:
                    result = "No matching knowledge found."
        except Exception as e:
            return self.error_result(f"Knowledge base operation failed: {e}")

        new_context = dict(context)
        new_context["kb_result"] = result

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 11: Semantic Searcher
# ══════════════════════════════════════════════════════════════
class SemanticSearcherAgent(BaseAgent):
    """Performs semantic similarity search across all memory namespaces."""

    name = "semantic_searcher"
    description = "Semantic search across all agent memory namespaces"
    model = settings.model_fast
    system_prompt = """You are the Semantic Search agent. You find the most
semantically relevant information across all stored knowledge, regardless of
exact keyword matches. Present results ranked by relevance."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})
        mem = get_memory()

        # Search across all namespaces
        namespaces = mem.list_namespaces()
        if not namespaces:
            namespaces = ["global"]

        all_results = []
        for ns in namespaces:
            try:
                results = await mem.search(query=task, n_results=3, namespace=ns)
                for r in results:
                    r["namespace"] = ns
                    all_results.append(r)
            except Exception as e:
                log.debug("semantic_search.namespace_failed", namespace=ns, error=str(e))

        # Sort by distance (lower = more relevant)
        all_results.sort(key=lambda x: x.get("distance", 1.0))
        top_results = all_results[:8]

        if top_results:
            formatted = "\n\n".join(
                f"[{r['namespace']}] (score: {1-r['distance']:.3f})\n{r['text'][:300]}"
                for r in top_results
            )
            result = f"Top {len(top_results)} semantic matches:\n\n{formatted}"
        else:
            result = "No semantically similar content found."

        new_context = dict(context)
        new_context["search_results"] = result

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }
