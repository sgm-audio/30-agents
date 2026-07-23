"""
VISION SQUAD — Image/video/audio processing and multimodal synthesis

Squad: @VisionSquad
Pipeline: vision → embedding → multimodal → media_coordinator

Leader: VisionSquadLeader
Members:
  - vision: Analyzes images using minicpm-v multimodal model
  - embedding: Generates embeddings for semantic search and similarity
  - multimodal: Synthesizes information across text, image, audio modalities
  - media_coordinator: Coordinates media processing and format conversions
  - audio_analyst: Reasons about DSP/audio engineering tasks (no audio decoding libs)

Routing Logic:
  vision_analyst → embedding_engine → multimodal_synthesizer → media_coordinator → END
  Or direct routing based on task type (vision task → vision, embed task → embedding, etc.)
"""
from typing import Any

import structlog

from agents.tier6 import (
    VisionAnalystAgent,
    EmbeddingEngineAgent,
    MultimodalSynthesizerAgent,
    MediaCoordinatorAgent,
    AudioAnalystAgent,
)
from core.config import settings
from core.graph import AgentState

from squads.base import SquadLeader, SquadConfig, SquadMember, RoutingRule

log = structlog.get_logger(__name__)


VISION_MEMBERS = [
    SquadMember(
        name="vision_analyst",
        agent_class=VisionAnalystAgent,
        description="Analyzes images (OCR, description, visual Q&A)",
        keywords=["image", "photo", "picture", "visual", "analyze image", "OCR", "describe"],
        model=settings.model_vision,
    ),
    SquadMember(
        name="embedding_engine",
        agent_class=EmbeddingEngineAgent,
        description="Generates embeddings for semantic search",
        keywords=["embed", "embedding", "vector", "semantic search", "similarity"],
        model=settings.model_embed,
    ),
    SquadMember(
        name="multimodal_synthesizer",
        agent_class=MultimodalSynthesizerAgent,
        description="Synthesizes information across text, image, and audio",
        keywords=["multimodal", "synthesize", "combine", "cross-modal", "integrate"],
        model=settings.model_reason,
    ),
    SquadMember(
        name="media_coordinator",
        agent_class=MediaCoordinatorAgent,
        description="Coordinates media processing and format conversions",
        keywords=["media", "convert", "format", "audio", "video", "transcode", "process"],
        model=settings.model_fast,
    ),
    SquadMember(
        name="audio_analyst",
        agent_class=AudioAnalystAgent,
        description="Reasons about DSP/audio engineering tasks and audio file metadata",
        keywords=["dsp", "mixing", "mastering", "vst", "clap", "plugin design", "reaper", "audio engineering"],
        model=settings.model_fast,
    ),
]


VISION_ROUTING = [
    RoutingRule(
        keywords=["image", "photo", "picture", "visual", "OCR", "describe image", "analyze image"],
        member_name="vision_analyst",
        priority=10,
    ),
    RoutingRule(
        keywords=["embed", "embedding", "vector", "semantic", "similarity"],
        member_name="embedding_engine",
        priority=9,
    ),
    RoutingRule(
        keywords=["multimodal", "synthesize", "combine", "cross-modal", "integrate"],
        member_name="multimodal_synthesizer",
        priority=7,
    ),
    RoutingRule(
        keywords=["media", "convert", "format", "audio", "video", "transcode"],
        member_name="media_coordinator",
        priority=6,
    ),
    RoutingRule(
        keywords=["dsp", "mixing", "mastering", "vst", "clap", "plugin design", "reaper", "audio engineering"],
        member_name="audio_analyst",
        priority=8,
    ),
]


VISION_SQUAD = SquadConfig(
    name="vision",
    display_name="Vision",
    description="Image/video/audio processing: analyze → embed → synthesize → coordinate",
    leader_class=None,
    members=VISION_MEMBERS,
    routing_rules=VISION_ROUTING,
    default_member="vision_analyst",
)


class VisionSquadLeader(SquadLeader):
    """
    Leader for the Vision squad. Manages multimodal image/video/audio processing.

    Workflow:
    1. vision_analyst processes images (always first for visual tasks)
    2. embedding_engine generates embeddings for semantic operations
    3. multimodal_synthesizer combines across modalities
    4. media_coordinator handles format and processing coordination

    For pure embedding tasks, can skip directly to embedding_engine.
    For pure media processing, can start at media_coordinator.
    """

    name = "vision_squad"
    description = "Multimodal vision and media processing squad leader"
    model = settings.model_vision
    system_prompt = """You are the Vision Squad Leader. You coordinate four specialists:

1. vision_analyst: Analyzes images (OCR, description, visual Q&A)
2. embedding_engine: Generates embeddings for semantic search
3. multimodal_synthesizer: Combines text, image, audio into unified output
4. media_coordinator: Handles format conversions and media processing

Workflow: vision → embed → synthesize → coordinate → END
Or direct routing based on task type."""

    WORKFLOW_ORDER = ["vision_analyst", "embedding_engine", "multimodal_synthesizer", "media_coordinator"]

    def route_task(self, task: str, context: dict[str, Any]) -> str:
        """Route to most relevant member based on task keywords."""
        task_lower = task.lower()

        if any(kw in task_lower for kw in ["dsp", "mixing", "mastering", "vst", "clap", "plugin design", "reaper", "audio engineering"]):
            return "audio_analyst"

        if any(kw in task_lower for kw in ["embed", "embedding", "vector", "semantic", "similarity"]):
            return "embedding_engine"

        if any(kw in task_lower for kw in ["media", "convert", "format", "audio", "video", "transcode"]):
            return "media_coordinator"

        if any(kw in task_lower for kw in ["multimodal", "synthesize", "combine", "cross-modal"]):
            return "multimodal_synthesizer"

        if any(kw in task_lower for kw in ["image", "photo", "visual", "OCR", "describe"]):
            return "vision_analyst"

        return "vision_analyst"

    def is_squad_complete(self, last_member: str, member_result: dict, context: dict) -> bool:
        """Complete after media_coordinator runs."""
        return last_member == "media_coordinator"

    def get_next_member(self, last_member: str, member_result: dict, context: dict) -> str | None:
        """Route sequentially through the pipeline."""
        try:
            idx = self.WORKFLOW_ORDER.index(last_member)
            if idx + 1 < len(self.WORKFLOW_ORDER):
                return self.WORKFLOW_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def get_next_task(self, last_member: str, next_member: str, context: dict) -> str:
        """Pass through original task."""
        return context.get("squad_task", "")

    def compile_squad_result(self, last_member: str, squad_result: dict, context: dict) -> str:
        """Compile multimodal processing results."""
        lines = ["[VISION SQUAD Complete]", ""]

        for member_name in self.WORKFLOW_ORDER:
            if member_name in squad_result:
                lines.append(f"--- {member_name.upper().replace('_', ' ')} ---")
                lines.append(squad_result[member_name][:500])
                lines.append("")

        return "\n".join(lines)


VISION_SQUAD.leader_class = VisionSquadLeader