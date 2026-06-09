"""
TIER 4 - CONTENT & CREATIVE AGENTS
Agents 17-21: Writer, Summarizer, Translator, Editor, Content Strategist
"""
from __future__ import annotations

from typing import Any

import structlog

from agents.base import BaseAgent
from core.config import settings
from core.graph import AgentState

log = structlog.get_logger(__name__)

__all__ = [
    "WriterAgent",
    "SummarizerAgent",
    "TranslatorAgent",
    "EditorAgent",
    "ContentStrategistAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 17: Writer
# ══════════════════════════════════════════════════════════════
class WriterAgent(BaseAgent):
    """Generates long-form written content across many formats."""

    name = "writer"
    description = "Generates essays, reports, articles, and long-form content"
    model = settings.model_reason
    system_prompt = """You are a professional writer with expertise in technical writing,
creative writing, business writing, and academic writing.

You write:
- Clear, well-structured content
- Engaging introductions and strong conclusions
- Appropriate tone for the audience
- Content that flows naturally from point to point
- Properly formatted documents with headers, bullets where appropriate

Always ask yourself: "Does this serve the reader's needs?" """

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        format_type = context.get("format", "article")
        audience = context.get("audience", "general")
        tone = context.get("tone", "professional")
        length = context.get("length", "medium")

        prompt = (
            f"Write a {length} {format_type} for {audience} audience with {tone} tone.\n\n"
            f"Topic/Task: {task}"
        )

        content = await self.llm(prompt)

        await self.remember(
            content[:1000],
            metadata={"task": task, "format": format_type},
            namespace="content",
        )

        new_context = dict(context)
        new_context["written_content"] = content

        return {
            "context": new_context,
            "result": content,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 18: Summarizer
# ══════════════════════════════════════════════════════════════
class SummarizerAgent(BaseAgent):
    """Condenses long content into clear, accurate summaries."""

    name = "summarizer"
    description = "Summarizes long documents and conversations"
    model = settings.model_fast
    system_prompt = """You are an expert at summarization. You create summaries that:
- Preserve all key information
- Are significantly shorter than the original
- Maintain the original meaning and nuance
- Highlight the most important points first
- Use clear, simple language

Formats you can produce: bullet points, executive summary, TL;DR, abstract."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        content = context.get("content", context.get("written_content", task))
        summary_type = context.get("summary_type", "brief")

        prompt = f"Create a {summary_type} summary of:\n\n{content}"

        summary = await self.llm(prompt)

        new_context = dict(context)
        new_context["summary"] = summary

        return {
            "context": new_context,
            "result": summary,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 19: Translator
# ══════════════════════════════════════════════════════════════
class TranslatorAgent(BaseAgent):
    """Translates content between languages with cultural awareness."""

    name = "translator"
    description = "Translates text between languages"
    model = settings.model_reason
    system_prompt = """You are a professional translator fluent in many languages.
Your translations:
- Preserve meaning, not just literal words
- Adapt idioms and cultural references appropriately
- Maintain the tone and register of the original
- Flag any terms that have no direct translation

Always confirm which language you're translating from and to."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        text = context.get("content", task)
        target_lang = context.get("target_language", "English")
        source_lang = context.get("source_language", "auto-detect")

        prompt = (
            f"Translate the following from {source_lang} to {target_lang}:\n\n{text}\n\n"
            f"Provide the translation and note any cultural adaptations made:"
        )

        translation = await self.llm(prompt)

        new_context = dict(context)
        new_context["translation"] = translation

        return {
            "context": new_context,
            "result": translation,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 20: Editor
# ══════════════════════════════════════════════════════════════
class EditorAgent(BaseAgent):
    """Improves writing quality, fixes grammar, and enhances clarity."""

    name = "editor"
    description = "Edits and improves written content"
    model = settings.model_reason
    system_prompt = """You are a professional editor. You improve text by:
1. Fixing grammar, spelling, and punctuation
2. Improving sentence structure and flow
3. Eliminating redundancy and wordiness
4. Strengthening word choices
5. Ensuring logical progression of ideas
6. Maintaining the author's voice

Show your edits clearly: provide the improved version and explain major changes."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        content = context.get("written_content", context.get("content", task))
        edit_type = context.get("edit_type", "full")

        prompt = f"Edit and improve this text ({edit_type} edit):\n\n{content}"

        edited = await self.llm(prompt)

        new_context = dict(context)
        new_context["edited_content"] = edited

        return {
            "context": new_context,
            "result": edited,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 21: Content Strategist
# ══════════════════════════════════════════════════════════════
class ContentStrategistAgent(BaseAgent):
    """Plans content strategy, outlines, and messaging frameworks."""

    name = "content_strategist"
    description = "Plans content strategy and messaging frameworks"
    model = settings.model_reason
    system_prompt = """You are a content strategy expert. You help plan:
- Content calendars and publishing schedules
- Audience personas and targeting
- Messaging frameworks and key messages
- Content formats and distribution channels
- SEO and discoverability strategies
- Content performance metrics

Provide structured, actionable content strategies."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        audience = context.get("audience", "general")
        goals = context.get("goals", "engage and inform")

        prompt = (
            f"Create a content strategy for: {task}\n\n"
            f"Audience: {audience}\n"
            f"Goals: {goals}\n\n"
            f"Provide a detailed content strategy with actionable recommendations:"
        )

        strategy = await self.llm(prompt)

        new_context = dict(context)
        new_context["content_strategy"] = strategy

        return {
            "context": new_context,
            "result": strategy,
            "next_agent": "END",
        }
