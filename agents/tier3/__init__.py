"""
TIER 3 - CODE & ENGINEERING AGENTS
Agents 12-16: Code Writer, Code Reviewer, Bug Hunter, System Architect, Test Engineer
"""
from __future__ import annotations

from typing import Any

import structlog

from agents.base import BaseAgent
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)

__all__ = [
    "CodeWriterAgent",
    "CodeReviewerAgent",
    "BugHunterAgent",
    "SystemArchitectAgent",
    "TestEngineerAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 12: Code Writer
# ══════════════════════════════════════════════════════════════
class CodeWriterAgent(BaseAgent):
    """Generates high-quality code from natural language descriptions."""

    name = "code_writer"
    description = "Generates code from natural language descriptions"
    model = settings.model_reason
    system_prompt = """You are an expert software engineer. Write clean, efficient,
well-documented code based on the requirements provided.

Follow these principles:
- Write idiomatic code for the target language
- Add docstrings and comments for complex logic
- Handle edge cases and errors
- Follow PEP 8 for Python, standard style guides for other languages
- Prefer simple, readable solutions over clever ones

Always wrap code in proper markdown code blocks with the language specified."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        language = context.get("language", "python")
        existing_code = context.get("existing_code", "")

        prompt = f"Write {language} code for: {task}"
        if existing_code:
            prompt += f"\n\nExisting code to extend/modify:\n```{language}\n{existing_code}\n```"

        code = await self.llm(prompt)

        # Store the generated code in context for downstream agents
        new_context = dict(context)
        new_context["generated_code"] = code
        new_context["language"] = language

        return {
            "context": new_context,
            "result": code,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 13: Code Reviewer
# ══════════════════════════════════════════════════════════════
class CodeReviewerAgent(BaseAgent):
    """Reviews code for correctness, style, security, and performance."""

    name = "code_reviewer"
    description = "Reviews code for quality, security, and correctness"
    model = settings.model_reason
    system_prompt = """You are a senior code reviewer with expertise in security,
performance, and software design. Review code for:

1. **Correctness**: Does it do what it claims?
2. **Security**: Are there vulnerabilities (SQL injection, XSS, etc.)?
3. **Performance**: Algorithmic complexity, unnecessary copies, N+1 queries
4. **Style**: Readability, naming, structure
5. **Error Handling**: Edge cases, exception handling
6. **Testing**: Is the code testable?

Rate severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
Provide specific line-by-line feedback where applicable."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        code = context.get("generated_code", context.get("code", task))

        review = await self.llm(
            prompt=f"Review this code:\n\n{code}\n\nProvide a detailed code review:",
        )

        new_context = dict(context)
        new_context["code_review"] = review

        return {
            "context": new_context,
            "result": review,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 14: Bug Hunter
# ══════════════════════════════════════════════════════════════
class BugHunterAgent(BaseAgent):
    """Analyzes error messages and code to identify and fix bugs."""

    name = "bug_hunter"
    description = "Analyzes bugs and provides fixes"
    model = settings.model_reason
    system_prompt = """You are an expert debugger. Given code and/or error messages:

1. Identify the root cause of the bug
2. Explain why the bug occurs
3. Provide a concrete fix with the corrected code
4. Suggest how to prevent similar bugs in the future

Be precise: specify exact line numbers and changes needed."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        code = context.get("code", "")
        error_msg = context.get("error", "")

        prompt = f"Debug task: {task}"
        if error_msg:
            prompt += f"\n\nError message:\n{error_msg}"
        if code:
            prompt += f"\n\nCode:\n{code}"

        analysis = await self.llm(prompt)

        new_context = dict(context)
        new_context["bug_analysis"] = analysis

        return {
            "context": new_context,
            "result": analysis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 15: System Architect
# ══════════════════════════════════════════════════════════════
class SystemArchitectAgent(BaseAgent):
    """Designs system architectures, APIs, and data models."""

    name = "system_architect"
    description = "Designs system architectures and technical specifications"
    model = settings.model_reason
    system_prompt = """You are a principal software architect with deep experience in:
- Distributed systems and microservices
- Database design (SQL and NoSQL)
- API design (REST, GraphQL, gRPC)
- Cloud-native and on-premises architectures
- Security and compliance requirements
- Scalability and performance patterns

Produce detailed architectural designs with:
- Component diagrams (text-based ASCII)
- Data flow descriptions
- Technology choices with justifications
- Trade-off analysis
- Implementation phases"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        requirements = context.get("requirements", task)

        architecture = await self.llm(
            prompt=f"Design a system architecture for: {requirements}\n\n"
                   f"Provide a detailed technical specification:",
        )

        await self.remember(
            architecture,
            metadata={"task": task, "type": "architecture"},
            namespace="architecture",
        )

        new_context = dict(context)
        new_context["architecture"] = architecture

        return {
            "context": new_context,
            "result": architecture,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 16: Test Engineer
# ══════════════════════════════════════════════════════════════
class TestEngineerAgent(BaseAgent):
    """Writes comprehensive test suites for code."""

    name = "test_engineer"
    description = "Writes unit, integration, and end-to-end tests"
    model = settings.model_reason
    system_prompt = """You are a test engineering expert. Write comprehensive tests:

1. **Unit tests**: Test individual functions/methods
2. **Integration tests**: Test component interactions
3. **Edge cases**: Empty inputs, boundaries, errors
4. **Fixtures and mocks**: Isolate dependencies
5. **Test naming**: Descriptive names following `test_<what>_<condition>_<expected>`

Use pytest for Python, Jest for JavaScript, and language-appropriate frameworks.
Aim for high coverage but prioritize meaningful tests over coverage metrics."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        code = context.get("generated_code", context.get("code", ""))
        language = context.get("language", "python")

        prompt = f"Write tests for: {task}"
        if code:
            prompt += f"\n\nCode to test:\n{code}"
        prompt += f"\n\nWrite comprehensive {language} tests:"

        tests = await self.llm(prompt)

        new_context = dict(context)
        new_context["tests"] = tests

        return {
            "context": new_context,
            "result": tests,
            "next_agent": "END",
        }
