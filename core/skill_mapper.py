"""
Skill mapper: maps OpenCode skills to 30-agent agents.
Provides SkillRegistry, SkillMapper, and AgentSkillProfile.
"""
import json
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)

MAPPINGS_PATH = Path(__file__).parent.parent / "config" / "skill_mappings.json"
DEFAULT_MAPPINGS = json.loads(MAPPINGS_PATH.read_text()) if MAPPINGS_PATH.exists() else {}


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
