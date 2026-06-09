"""
Agent Registry: instantiates and registers all agents with the LangGraph.
"""
import structlog

from agents.tier1 import (
    OrchestratorAgent,
    MemoryManagerAgent,
    ContextTrackerAgent,
    ToolDispatcherAgent,
    StateMachineAgent,
)
from agents.tier2 import (
    WebResearcherAgent,
    DocReaderAgent,
    KnowledgeSynthesizerAgent,
    FactVerifierAgent,
    KnowledgeBaseAgent,
    SemanticSearcherAgent,
)
from agents.tier3 import (
    CodeWriterAgent,
    CodeReviewerAgent,
    BugHunterAgent,
    SystemArchitectAgent,
    TestEngineerAgent,
)
from agents.tier4 import (
    WriterAgent,
    SummarizerAgent,
    TranslatorAgent,
    EditorAgent,
    ContentStrategistAgent,
)
from agents.tier5 import (
    DataAnalystAgent,
    LogicEngineAgent,
    PlannerAgent,
    CriticAgent,
    DecisionEngineAgent,
    MethodologyAdvisorAgent,
)
from agents.tier6 import (
    VisionAnalystAgent,
    EmbeddingEngineAgent,
    MultimodalSynthesizerAgent,
    MediaCoordinatorAgent,
)
from agents.tier2_outreach import LeadScoutAgent, EmailFinderAgent
from agents.tier4_outreach import OutreachWriterAgent
from agents.tier2_seo_design import (
    WebDesignConceptAgent,
    OnPageSEOAgent,
    TechnicalSEOAgent,
    ContentSEOAgent,
    BacklinkAgent,
)
from core.graph import get_graph

log = structlog.get_logger(__name__)


# All 30 agent classes in order
ALL_AGENTS = [
    # Tier 1
    OrchestratorAgent,
    MemoryManagerAgent,
    ContextTrackerAgent,
    ToolDispatcherAgent,
    StateMachineAgent,
    # Tier 2
    WebResearcherAgent,
    DocReaderAgent,
    KnowledgeSynthesizerAgent,
    FactVerifierAgent,
    KnowledgeBaseAgent,
    SemanticSearcherAgent,
    # OUTREACH (tier 2 extension)
    LeadScoutAgent,
    EmailFinderAgent,
    # Tier 3
    CodeWriterAgent,
    CodeReviewerAgent,
    BugHunterAgent,
    SystemArchitectAgent,
    TestEngineerAgent,
    # Tier 4
    WriterAgent,
    SummarizerAgent,
    TranslatorAgent,
    EditorAgent,
    ContentStrategistAgent,
    # OUTREACH (tier 4 extension)
    OutreachWriterAgent,
    # SEO & Design (tier 2 extensions)
    WebDesignConceptAgent,
    OnPageSEOAgent,
    TechnicalSEOAgent,
    ContentSEOAgent,
    BacklinkAgent,
    # Tier 5
    DataAnalystAgent,
    LogicEngineAgent,
    PlannerAgent,
    CriticAgent,
    DecisionEngineAgent,
    MethodologyAdvisorAgent,
    # Tier 6
    VisionAnalystAgent,
    EmbeddingEngineAgent,
    MultimodalSynthesizerAgent,
    MediaCoordinatorAgent,
]


def register_all_agents() -> None:
    """Instantiate all 30 agents and register them with the graph."""
    graph = get_graph()

    for AgentClass in ALL_AGENTS:
        instance = AgentClass()
        graph.register(instance.name, instance)
        log.debug("registered", agent=instance.name)

    graph.build()
    log.info(
        "all_agents_registered",
        count=len(ALL_AGENTS),
        agents=[A.name for A in ALL_AGENTS],
    )


def get_agent_info() -> list[dict]:
    """Return metadata for all agents (for UI display)."""
    return [
        {
            "name": A.name,
            "description": A.description,
            "model": A.model or "default",
            "tier": _get_tier(i),
        }
        for i, A in enumerate(ALL_AGENTS)
    ]


def _get_tier(index: int) -> int:
    tiers = [5, 6, 11, 16, 21, 27, 31]
    for tier, max_idx in enumerate(tiers, 1):
        if index < max_idx:
            return tier
    return 6
