"""
TIER 6 - MULTIMODAL AGENTS
Agents 27-30: Vision Analyst, Embedding Engine, Multimodal Synthesizer, Media Coordinator
"""
from __future__ import annotations

import base64
import json
from typing import Any

import structlog

from agents.base import BaseAgent
from core.config import settings
from core.graph import AgentState
from core.memory import get_memory
from core.ollama_client import get_ollama
from core.safety import resolve_workspace_path, validate_public_http_url

log = structlog.get_logger(__name__)

__all__ = [
    "VisionAnalystAgent",
    "EmbeddingEngineAgent",
    "MultimodalSynthesizerAgent",
    "MediaCoordinatorAgent",
    "AudioAnalystAgent",
]


# ══════════════════════════════════════════════════════════════
# Agent 27: Vision Analyst
# ══════════════════════════════════════════════════════════════
class VisionAnalystAgent(BaseAgent):
    """
    Analyzes images using minicpm-v multimodal model.
    Supports image description, OCR, visual Q&A.
    """

    name = "vision_analyst"
    description = "Analyzes images using the minicpm-v vision model"
    model = settings.model_vision
    system_prompt = """You are a visual analysis expert. You analyze images to:
1. Describe content in detail
2. Extract text (OCR)
3. Identify objects, people, scenes
4. Answer questions about visual content
5. Detect anomalies or issues
6. Provide structured data from visual inputs (tables, charts, diagrams)"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        image_path = context.get("image_path", "")
        image_url = context.get("image_url", "")
        image_b64 = context.get("image_b64", "")

        ollama = get_ollama()

        if not image_b64 and image_path:
            safe_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
            if (
                not isinstance(image_path, str)
                or not image_path.strip()
                or "\x00" in image_path
                or image_path.startswith(("/", "\\"))
            ):
                analysis = "Blocked unsafe image path."
                return {"result": analysis, "next_agent": "END"}

            p = resolve_workspace_path(image_path)
            if p and p.is_file() and p.suffix.lower() in safe_exts:
                image_b64 = base64.b64encode(p.read_bytes()).decode()
            else:
                analysis = f"Image file not found or unsupported type: {image_path}"
                return {"result": analysis, "next_agent": "END"}

        if not image_b64 and image_url:
            safe_image_url = validate_public_http_url(image_url)
            if not safe_image_url:
                analysis = "Blocked unsafe image URL."
                return {"result": analysis, "next_agent": "END"}
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(safe_image_url)
                    resp.raise_for_status()
                    image_b64 = base64.b64encode(resp.content).decode()
            except Exception as e:
                analysis = f"Failed to fetch image from URL: {e}"
                return {"result": analysis, "next_agent": "END"}

        if image_b64:
            # Use Ollama chat API with image
            messages = [
                {
                    "role": "user",
                    "content": task,
                    "images": [image_b64],
                }
            ]
            try:
                analysis = await ollama.chat(model=self.model, messages=messages)
            except Exception as e:
                analysis = f"Vision model error: {e}. (Is {self.model} pulled?)"
        else:
            analysis = (
                f"[Vision analysis requested but no image provided. "
                f"Provide image_path, image_url, or image_b64 in context.]\n\n"
                f"Task was: {task}"
            )

        new_context = dict(context)
        new_context["vision_analysis"] = analysis

        return {
            "context": new_context,
            "result": analysis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 28: Embedding Engine
# ══════════════════════════════════════════════════════════════
class EmbeddingEngineAgent(BaseAgent):
    """
    Generates and manages semantic embeddings using nomic-embed-text.
    Used for similarity search, clustering, and semantic operations.
    """

    name = "embedding_engine"
    description = "Generates semantic embeddings for text"
    model = settings.model_embed
    system_prompt = "You are the embedding engine."  # Not used for LLM calls

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        texts = context.get("texts", [task])
        if isinstance(texts, str):
            texts = [texts]

        ollama = get_ollama()
        embeddings = []
        for text in texts[:20]:  # Limit batch size
            try:
                emb = await ollama.embed(model=self.model, text=text)
                embeddings.append({"text": text[:100], "embedding_dim": len(emb)})
            except Exception as e:
                embeddings.append({"text": text[:100], "error": str(e)})

        # If operation is similarity search
        if context.get("operation") == "similarity" and len(texts) >= 2:
            try:
                emb1 = await ollama.embed(model=self.model, text=texts[0])
                emb2 = await ollama.embed(model=self.model, text=texts[1])
                # Cosine similarity
                import math
                dot = sum(a * b for a, b in zip(emb1, emb2))
                mag1 = math.sqrt(sum(a ** 2 for a in emb1))
                mag2 = math.sqrt(sum(b ** 2 for b in emb2))
                sim = dot / (mag1 * mag2) if mag1 and mag2 else 0.0
                result = f"Cosine similarity between texts: {sim:.4f}\n\nTexts:\n1: {texts[0][:100]}\n2: {texts[1][:100]}"
            except Exception as e:
                result = f"Similarity computation error: {e}"
        else:
            result = f"Generated embeddings for {len(embeddings)} texts:\n" + "\n".join(
                f"- '{e['text']}...' → {e.get('embedding_dim', 'error')} dims"
                for e in embeddings
            )

        new_context = dict(context)
        new_context["embeddings"] = embeddings

        return {
            "context": new_context,
            "result": result,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 29: Multimodal Synthesizer
# ══════════════════════════════════════════════════════════════
class MultimodalSynthesizerAgent(BaseAgent):
    """
    Combines text and visual information to produce unified multimodal outputs.
    Coordinates between vision and language models.
    """

    name = "multimodal_synthesizer"
    description = "Combines text and visual modalities for unified analysis"
    model = settings.model_reason
    system_prompt = """You are a multimodal synthesis expert. You combine:
- Visual information (image descriptions, OCR results)
- Text information (documents, knowledge base)
- Audio transcriptions
- Structured data

Your goal is to create unified, coherent responses that leverage all available modalities."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        # Gather all modality results from context
        modality_data = {}
        for key in ["vision_analysis", "doc_analysis", "research_result", "data_analysis"]:
            if key in context:
                modality_data[key] = context[key]

        if not modality_data:
            # Route to vision first if image is present
            if context.get("image_path") or context.get("image_url") or context.get("image_b64"):
                return {"next_agent": "vision_analyst"}

        synthesis_prompt = f"Synthesize a comprehensive response for: {task}\n\n"
        for modality, data in modality_data.items():
            synthesis_prompt += f"[{modality}]:\n{str(data)[:500]}\n\n"
        synthesis_prompt += "Provide a unified multimodal analysis:"

        synthesis = await self.llm(synthesis_prompt)

        new_context = dict(context)
        new_context["multimodal_synthesis"] = synthesis

        return {
            "context": new_context,
            "result": synthesis,
            "next_agent": "END",
        }


# ══════════════════════════════════════════════════════════════
# Agent 30: Media Coordinator
# ══════════════════════════════════════════════════════════════
class MediaCoordinatorAgent(BaseAgent):
    """
    Coordinates multi-step multimedia tasks across agents.
    Routes based on media type detection.
    """

    name = "media_coordinator"
    description = "Coordinates multimedia tasks and routes to appropriate agents"
    model = settings.model_fast
    system_prompt = """You are the Media Coordinator. You:
1. Detect media types (image, audio, video, document)
2. Route tasks to the appropriate specialist agent
3. Coordinate multi-step media processing pipelines
4. Manage file format conversions
5. Aggregate results from multiple media processing steps

Return JSON: {"media_type": "...", "next_agent": "...", "pipeline": [...]}"""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        # Detect media type from context
        has_image = any(
            k in context for k in ["image_path", "image_url", "image_b64"]
        )
        has_doc = "filepath" in context
        has_text = "content" in context

        if has_image:
            media_type = "image"
            next_agent = "vision_analyst"
        elif has_doc:
            media_type = "document"
            next_agent = "doc_reader"
        elif has_text:
            media_type = "text"
            next_agent = "knowledge_synthesizer"
        else:
            # Ask the LLM to determine
            response = await self.llm(
                prompt=f"What type of media processing is needed for: {task}\n"
                       f"Respond with JSON: {{\"media_type\": \"...\", \"next_agent\": \"...\"}}",
            )
            try:
                start = response.find("{")
                end = response.rfind("}") + 1
                parsed = json.loads(response[start:end])
                media_type = parsed.get("media_type", "text")
                next_agent = parsed.get("next_agent", "knowledge_synthesizer")
            except Exception:
                media_type = "text"
                next_agent = "knowledge_synthesizer"

        new_context = dict(context)
        new_context["media_type"] = media_type

        return {
            "context": new_context,
            "next_agent": next_agent,
        }


# ══════════════════════════════════════════════════════════════
# Agent (Audio): Audio Analyst
# ══════════════════════════════════════════════════════════════
class AudioAnalystAgent(BaseAgent):
    """
    Reasons about audio/DSP engineering tasks. No heavy audio libraries are
    used — if an audio file path is given, only lightweight filesystem
    metadata (size, extension) is inspected via pathlib; the LLM reasons
    about the engineering task itself (mixing, mastering, plugin design,
    DSP algorithms, etc.).
    """

    name = "audio_analyst"
    description = "Analyzes audio file metadata and reasons about DSP/audio engineering tasks"
    model = settings.model_fast
    system_prompt = """You are an audio engineering and DSP expert. You reason about:
1. Mixing, mastering, and audio production workflows
2. DSP algorithms (filters, dynamics, reverb, EQ, compression)
3. Plugin architecture (VST3/CLAP/AU) and real-time audio constraints
4. Audio file formats, sample rates, bit depths, and codecs
5. REAPER/DAW scripting and session organization

You do not have access to audio decoding or signal-analysis libraries —
reason from the task description and any file metadata provided."""

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = state["task"]
        context = state.get("context", {})

        audio_path = context.get("audio_path", "") or context.get("file_path", "")
        file_info = ""
        if audio_path:
            p = resolve_workspace_path(audio_path)
            if p and p.exists() and p.is_file():
                size_kb = p.stat().st_size / 1024
                file_info = f"\n\nAudio file: {p.name} ({p.suffix or 'no extension'}, {size_kb:.1f} KB)"
            else:
                file_info = f"\n\nNote: audio file not found at {audio_path} (reasoning from task description only)."

        analysis = await self.llm(f"{task}{file_info}")

        new_context = dict(context)
        new_context["audio_analysis"] = analysis

        return {
            "context": new_context,
            "result": analysis,
            "next_agent": "END",
        }
