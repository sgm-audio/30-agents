"""
Skill mapper: maps OpenCode skills to 30-agent agents.
Provides SkillRegistry, SkillMapper, and AgentSkillProfile.
"""
import json
from pathlib import Path
from typing import Any, Optional

import structlog
from core.config import settings

log = structlog.get_logger(__name__)

MAPPINGS_PATH = Path(__file__).parent.parent / "config" / "skill_mappings.json"

DEFAULT_MAPPINGS = {
    "12-factor-agents": {"agent": "methodology_advisor", "relevance": 95, "category": "engineering"},
    "ableton-live": {"agent": "multimodal_synthesizer", "relevance": 85, "category": "audio"},
    "academic-paper": {"agent": "writer", "relevance": 90, "category": "content"},
    "academic-paper-reviewer": {"agent": "critic", "relevance": 90, "category": "content"},
    "academic-pipeline": {"agent": "orchestrator", "relevance": 85, "category": "content"},
    "agent-driven-ci-cd-pipelines-github-actions": {"agent": "test_engineer", "relevance": 90, "category": "devops"},
    "agentic-tool-use-function-calling-for-daws": {"agent": "tool_dispatcher", "relevance": 90, "category": "audio"},
    "ai-agent-multi-agent-orchestration-langgraph-autogen": {"agent": "orchestrator", "relevance": 95, "category": "engineering"},
    "ai-assisted-software-engineering-cursor-copilot-pro": {"agent": "code_writer", "relevance": 85, "category": "devops"},
    "ai-powered-mastering-chain-optimization": {"agent": "multimodal_synthesizer", "relevance": 85, "category": "audio"},
    "arm-cortex-m-dsp-optimization-cmsis-dsp": {"agent": "system_architect", "relevance": 85, "category": "dsp"},
    "audio-analysis": {"agent": "data_analyst", "relevance": 90, "category": "audio"},
    "audio-business": {"agent": "decision_engine", "relevance": 90, "category": "business"},
    "audio-embeddings-vector-database-architecture": {"agent": "embedding_engine", "relevance": 95, "category": "audio"},
    "audio-mastering": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "audio-restoration": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "audio-to-midi": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "automated-audio-regression-and-unit-testing": {"agent": "test_engineer", "relevance": 90, "category": "devops"},
    "automated-video-demo-short-form-content-generation": {"agent": "content_strategist", "relevance": 85, "category": "content"},
    "autonomous-ai-customer-support-agents": {"agent": "orchestrator", "relevance": 85, "category": "business"},
    "bilingual-ux-accessibility-compliance-bill-96-aoda": {"agent": "fact_checker", "relevance": 85, "category": "legal"},
    "bootstrap-financial-engineering-unit-economics": {"agent": "decision_engine", "relevance": 90, "category": "business"},
    "browse": {"agent": "web_researcher", "relevance": 85, "category": "research"},
    "canadian-copyright-law-consultation-registration": {"agent": "fact_checker", "relevance": 90, "category": "legal"},
    "clap-protocol-implementation": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "cli-open-source-tools": {"agent": "tool_dispatcher", "relevance": 80, "category": "devops"},
    "cmake-modern-cpp": {"agent": "system_architect", "relevance": 85, "category": "devops"},
    "cmrra-soproq-royalty-workflow-design": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "coding": {"agent": "code_writer", "relevance": 95, "category": "engineering"},
    "community-driven-open-source-roadmap-management": {"agent": "planner", "relevance": 85, "category": "business"},
    "cross-compilation-toolchains": {"agent": "system_architect", "relevance": 85, "category": "devops"},
    "cusma-usmca-digital-trade-chapter-navigation": {"agent": "fact_checker", "relevance": 85, "category": "legal"},
    "data-formats": {"agent": "data_analyst", "relevance": 80, "category": "engineering"},
    "ddex-digital-data-exchange-xml-json-parsing": {"agent": "data_analyst", "relevance": 85, "category": "engineering"},
    "decentralized-storage-ipfs-for-sample-libraries": {"agent": "system_architect", "relevance": 80, "category": "engineering"},
    "deep-research": {"agent": "web_researcher", "relevance": 95, "category": "research"},
    "defensive-patenting-open-source-copyleft-hybrid-strategy": {"agent": "decision_engine", "relevance": 85, "category": "legal"},
    "deterministic-audio-sandboxing": {"agent": "test_engineer", "relevance": 85, "category": "dsp"},
    "diagnostic-dsp": {"agent": "data_analyst", "relevance": 90, "category": "dsp"},
    "digital-signal-processing-dsp-mathematics": {"agent": "logic_reasoner", "relevance": 90, "category": "dsp"},
    "embedded-linux-audio-programming-bela-elk-audio-os": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "emc-emi-compliance-testing-fcc-ised": {"agent": "fact_checker", "relevance": 85, "category": "legal"},
    "ethical-synthetic-dataset-curation": {"agent": "data_analyst", "relevance": 85, "category": "ml"},
    "eurorack-modular-hardware-design": {"agent": "system_architect", "relevance": 85, "category": "dsp"},
    "factor-canada-council-grant-architecture": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "faust-functional-audio-stream-integration": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "few-shot-voice-cloning-ethical-watermarked": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "fpga-based-dsp-programming-vhdl-verilog": {"agent": "system_architect", "relevance": 85, "category": "dsp"},
    "game-audio": {"agent": "multimodal_synthesizer", "relevance": 85, "category": "audio"},
    "gcloud": {"agent": "tool_dispatcher", "relevance": 85, "category": "devops"},
    "generative-music": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "gepeto": {"agent": "tool_dispatcher", "relevance": 75, "category": "devops"},
    "gitops-semantic-versioning-automation": {"agent": "test_engineer", "relevance": 85, "category": "devops"},
    "gstack-upgrade": {"agent": "tool_dispatcher", "relevance": 75, "category": "devops"},
    "hardware-security-module-hsm-integration": {"agent": "system_architect", "relevance": 85, "category": "security"},
    "infrastructure-as-code-iac-for-audio-rendering": {"agent": "system_architect", "relevance": 85, "category": "devops"},
    "interactive-mdx-gitbook-documentation-engineering": {"agent": "content_strategist", "relevance": 85, "category": "content"},
    "jtag-debugging-for-audio-hardware": {"agent": "system_architect", "relevance": 80, "category": "dsp"},
    "juce-framework-mastery": {"agent": "code_writer", "relevance": 95, "category": "dsp"},
    "latent-diffusion-model-architecture-audioldm-stable-audio": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "live-sound": {"agent": "multimodal_synthesizer", "relevance": 85, "category": "audio"},
    "local-large-language-model-llm-orchestration": {"agent": "orchestrator", "relevance": 90, "category": "ml"},
    "local-llms": {"agent": "orchestrator", "relevance": 85, "category": "ml"},
    "lock-free-concurrency-and-real-time-safety": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "machine-learning": {"agent": "data_analyst", "relevance": 95, "category": "ml"},
    "midi-2.0-and-mpe-engineering": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "mixing-engineer": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "ml-audio": {"agent": "data_analyst", "relevance": 95, "category": "ml"},
    "model-quantization-for-audio": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "multimodal-ai-vision-audio-scoring": {"agent": "multimodal_synthesizer", "relevance": 95, "category": "audio"},
    "music-information-retrieval-mir-techniques": {"agent": "data_analyst", "relevance": 90, "category": "audio"},
    "music-theory": {"agent": "writer", "relevance": 90, "category": "audio"},
    "neural-ambisonics-spatial-audio-synthesis": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "neural-audio-codec-implementation-encodec-soundstream": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "neural-audio-synthesis-ddsp-gans": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "npu-inference": {"agent": "system_architect", "relevance": 85, "category": "ml"},
    "ollama": {"agent": "orchestrator", "relevance": 85, "category": "ml"},
    "open-source-license-compliance-automation-fossology": {"agent": "fact_checker", "relevance": 85, "category": "legal"},
    "output-placement": {"agent": "tool_dispatcher", "relevance": 75, "category": "engineering"},
    "patent-troll-defense-prior-art-research": {"agent": "web_researcher", "relevance": 90, "category": "legal"},
    "permissive-vs-copyleft-licensing-strategy": {"agent": "decision_engine", "relevance": 85, "category": "legal"},
    "pinokio": {"agent": "tool_dispatcher", "relevance": 75, "category": "devops"},
    "plan-ceo-review": {"agent": "decision_engine", "relevance": 90, "category": "business"},
    "plan-eng-review": {"agent": "code_reviewer", "relevance": 90, "category": "engineering"},
    "plugin-ci-cd": {"agent": "test_engineer", "relevance": 90, "category": "devops"},
    "podcast-production": {"agent": "multimodal_synthesizer", "relevance": 85, "category": "audio"},
    "power-management-thermal-design": {"agent": "system_architect", "relevance": 85, "category": "dsp"},
    "product-led-growth-plg-loop-engineering": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "qa": {"agent": "test_engineer", "relevance": 95, "category": "engineering"},
    "quantization-aware-training-qat-for-edge-ai": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "real-time-neural-network-inference-rtneural-onnx": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "real-time-neural-timbre-transfer": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "real-time-operating-system-rtos-configuration": {"agent": "system_architect", "relevance": 85, "category": "dsp"},
    "reaper-custom-action-builder": {"agent": "tool_dispatcher", "relevance": 85, "category": "audio"},
    "reaper-fxchain-designer": {"agent": "content_strategist", "relevance": 85, "category": "audio"},
    "reaper-intake-normalizer": {"agent": "planner", "relevance": 80, "category": "audio"},
    "reaper-midi-arrangement-builder": {"agent": "content_strategist", "relevance": 85, "category": "audio"},
    "reaper-midi-clip-composer": {"agent": "writer", "relevance": 85, "category": "audio"},
    "reaper-midi-drum-programmer": {"agent": "writer", "relevance": 85, "category": "audio"},
    "reaper-midi-expression-designer": {"agent": "content_strategist", "relevance": 85, "category": "audio"},
    "reaper-midi-harmony-planner": {"agent": "logic_reasoner", "relevance": 85, "category": "audio"},
    "reaper-midi-humanizer": {"agent": "content_strategist", "relevance": 80, "category": "audio"},
    "reaper-midi-intake-normalizer": {"agent": "planner", "relevance": 80, "category": "audio"},
    "reaper-midi-orchestrator": {"agent": "orchestrator", "relevance": 85, "category": "audio"},
    "reaper-midi-reascript-author": {"agent": "code_writer", "relevance": 90, "category": "audio"},
    "reaper-midi-session-architect": {"agent": "system_architect", "relevance": 85, "category": "audio"},
    "reaper-midi-validator": {"agent": "test_engineer", "relevance": 85, "category": "audio"},
    "reaper-orchestrator": {"agent": "orchestrator", "relevance": 85, "category": "audio"},
    "reaper-preset-mapper": {"agent": "tool_dispatcher", "relevance": 80, "category": "audio"},
    "reaper-reascript-author": {"agent": "code_writer", "relevance": 90, "category": "audio"},
    "reaper-session-architect": {"agent": "system_architect", "relevance": 85, "category": "audio"},
    "reaper-theme-builder": {"agent": "content_strategist", "relevance": 85, "category": "audio"},
    "reaper-validator": {"agent": "test_engineer", "relevance": 85, "category": "audio"},
    "reinforcement-learning-for-synth-patching": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "retro": {"agent": "critic", "relevance": 85, "category": "engineering"},
    "review": {"agent": "code_reviewer", "relevance": 95, "category": "engineering"},
    "rocm-on-igpu": {"agent": "system_architect", "relevance": 85, "category": "ml"},
    "secure-openapi-grpc-gateway-design": {"agent": "system_architect", "relevance": 90, "category": "engineering"},
    "setup-browser-cookies": {"agent": "tool_dispatcher", "relevance": 75, "category": "devops"},
    "ship": {"agent": "orchestrator", "relevance": 85, "category": "devops"},
    "simd-vectorization-and-avx-neon-optimization": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "socan-resound-api-integration": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "sound-design": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "sound-for-film": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "source-separation-pipeline-integration": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "sr-ed-scientific-research-experimental-development-tax-credit-optimization": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "subscription-micro-transaction-billing-architecture-stripe-paddle": {"agent": "decision_engine", "relevance": 85, "category": "business"},
    "synthetic-data-generation-pipeline": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "telemetry-privacy-first-analytics": {"agent": "data_analyst", "relevance": 85, "category": "engineering"},
    "transformer-architecture-for-music-musicgen-jukebox": {"agent": "data_analyst", "relevance": 90, "category": "ml"},
    "usb-audio-class-2-0-driver-development": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
    "voice-synthesis": {"agent": "multimodal_synthesizer", "relevance": 90, "category": "audio"},
    "vst3-ara-protocol": {"agent": "system_architect", "relevance": 90, "category": "dsp"},
}


class SkillRegistry:
    """Manages skill-to-agent mappings persisted as JSON."""

    def __init__(self):
        self._mappings: dict[str, dict] = {}
        self._load()

    def _load(self):
        if MAPPINGS_PATH.exists():
            try:
                self._mappings = json.loads(MAPPINGS_PATH.read_text())
            except Exception:
                self._mappings = dict(DEFAULT_MAPPINGS)
                self._save()
        else:
            self._mappings = dict(DEFAULT_MAPPINGS)
            self._save()

    def _save(self):
        MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        MAPPINGS_PATH.write_text(json.dumps(self._mappings, indent=2))
        log.info("skill.mappings_saved", path=str(MAPPINGS_PATH))

    def get_all(self) -> dict:
        return dict(self._mappings)

    def get(self, skill_name: str) -> Optional[dict]:
        return self._mappings.get(skill_name)

    def set_mapping(self, skill_name: str, agent_name: str, relevance: int = 80, category: str = "general"):
        self._mappings[skill_name] = {"agent": agent_name, "relevance": relevance, "category": category}
        self._save()

    def remove(self, skill_name: str):
        if skill_name in self._mappings:
            del self._mappings[skill_name]
            self._save()

    def get_mapped_count(self) -> int:
        return len(self._mappings)


class SkillMapper:
    """Queries skill-to-agent mappings."""

    def __init__(self):
        self.registry = SkillRegistry()

    def find_agent_for_skill(self, skill_name: str) -> Optional[dict]:
        mapping = self.registry.get(skill_name)
        if not mapping:
            return None
        return {
            "skill": skill_name,
            "agent": mapping["agent"],
            "relevance": mapping.get("relevance", 80),
            "category": mapping.get("category", "general"),
        }

    def find_skills_for_agent(self, agent_name: str) -> list[dict]:
        results = []
        for skill, mapping in self.registry.get_all().items():
            if mapping["agent"] == agent_name:
                results.append({"skill": skill, **mapping})
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results

    def suggest_agent(self, task_description: str) -> dict:
        task_lower = task_description.lower()
        best_agent = "orchestrator"
        best_score = 0
        alternatives: list[dict] = []

        for skill, mapping in self.registry.get_all().items():
            skill_words = skill.replace("-", " ").split()
            matches = sum(1 for w in skill_words if w in task_lower)
            if matches > 0:
                score = matches * mapping.get("relevance", 80) / 100.0
                if score > best_score:
                    best_score = score
                    best_agent = mapping["agent"]
                alternatives.append({"agent": mapping["agent"], "skill": skill, "score": round(score, 1)})

        alternatives.sort(key=lambda x: x["score"], reverse=True)
        return {
            "task": task_description[:100],
            "suggested_agent": best_agent,
            "confidence": round(best_score, 1),
            "alternatives": alternatives[:5],
        }

    def get_coverage_stats(self) -> dict:
        all_mappings = self.registry.get_all()
        agent_counts: dict[str, int] = {}
        for mapping in all_mappings.values():
            agent = mapping["agent"]
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

        return {
            "total_skills_mapped": len(all_mappings),
            "unique_agents_used": len(agent_counts),
            "per_agent": agent_counts,
        }

    def validate_mappings(self) -> dict:
        try:
            from agents.registry import ALL_AGENTS
            valid_agents = {a["name"] for a in ALL_AGENTS}
        except Exception:
            valid_agents = set()

        all_mappings = self.registry.get_all()
        invalid = []
        for skill, mapping in all_mappings.items():
            if valid_agents and mapping["agent"] not in valid_agents:
                invalid.append({"skill": skill, "agent": mapping["agent"]})

        return {
            "total_mappings": len(all_mappings),
            "valid": len(all_mappings) - len(invalid),
            "invalid": invalid,
            "valid_agents_known": len(valid_agents) > 0,
        }


class AgentSkillProfile:
    """Builds skill profiles for agents."""

    def __init__(self):
        self.mapper = SkillMapper()

    def get_profile(self, agent_name: str) -> dict:
        skills = self.mapper.find_skills_for_agent(agent_name)
        try:
            from agents.registry import ALL_AGENTS
            agent_info = next((a for a in ALL_AGENTS if a["name"] == agent_name), {})
        except Exception:
            agent_info = {}

        return {
            "agent": agent_name,
            "tier": agent_info.get("tier", "unknown"),
            "description": agent_info.get("description", ""),
            "skills": skills,
            "skill_count": len(skills),
        }

    def list_all_profiles(self) -> list[dict]:
        mapper = self.mapper
        agent_set: set[str] = set()
        for mapping in mapper.registry.get_all().values():
            agent_set.add(mapping["agent"])

        profiles = []
        for agent in sorted(agent_set):
            profiles.append(self.get_profile(agent))
        return profiles
