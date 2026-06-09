"""
Squad Registry — Registers all squad leaders with the agent graph.
"""
import structlog

from core.graph import get_graph
from core.config import settings

from squads import ALL_SQUADS
from squads.outreach import OUTREACH_SQUAD
from squads.seo import SEO_SQUAD
from squads.analytics import ANALYTICS_SQUAD
from squads.content import CONTENT_SQUAD
from squads.code import CODE_SQUAD
from squads.vision import VISION_SQUAD

log = structlog.get_logger(__name__)


def create_squad_leader(config):
    """Instantiate a squad leader from its config."""
    if config.leader_class is None:
        raise ValueError(f"Squad {config.name} has no leader_class configured")
    return config.leader_class(config)


def register_all_squads():
    """Register all 6 squad leaders with the agent graph."""
    graph = get_graph()

    for squad_name, config in ALL_SQUADS.items():
        try:
            leader = create_squad_leader(config)
            graph.register(leader.name, leader)
            log.info("squad.registered", squad=squad_name, leader=leader.name)
        except Exception as e:
            log.error("squad.register_failed", squad=squad_name, error=str(e))

    log.info("all_squads_registered", count=len(ALL_SQUADS))


def get_squad_info():
    """Return metadata for all squads (for UI display)."""
    return [
        {
            "name": config.name,
            "display_name": config.display_name,
            "description": config.description,
            "members": [m.name for m in config.members],
            "member_count": len(config.members),
        }
        for config in ALL_SQUADS.values()
    ]


def get_squad_config(name: str):
    """Get squad config by name."""
    return ALL_SQUADS.get(name)