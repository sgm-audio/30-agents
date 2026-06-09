"""
Squad API Endpoints — REST interface for squad operations.

POST /api/squads              — List all squads
POST /api/squads/{name}/run    — Run a squad pipeline
GET  /api/squads/{name}        — Get squad info
POST /api/squads/run           — Run a specific squad by name
"""
import time
import uuid
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.graph import AgentState
from squads import ALL_SQUADS
from squads.registry import get_squad_config, create_squad_leader

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/squads", tags=["squads"])


class SquadRunRequest(BaseModel):
    task: str
    session_id: Optional[str] = None
    context: Optional[dict] = None
    city: Optional[str] = None
    max_leads: Optional[int] = None
    url: Optional[str] = None


class SquadRunResponse(BaseModel):
    session_id: str
    squad_name: str
    result: str
    elapsed_ms: int
    members_called: list[str]


@router.get("")
async def list_squads():
    """List all available squads."""
    from squads.registry import get_squad_info
    return {"squads": get_squad_info()}


@router.get("/{squad_name}")
async def get_squad(squad_name: str):
    """Get details about a specific squad."""
    config = get_squad_config(squad_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Squad '{squad_name}' not found")

    return {
        "name": config.name,
        "display_name": config.display_name,
        "description": config.description,
        "members": [
            {"name": m.name, "description": m.description, "keywords": m.keywords}
            for m in config.members
        ],
        "routing_rules": [
            {"keywords": r.keywords, "member": r.member_name, "priority": r.priority}
            for r in config.routing_rules
        ],
    }


@router.post("/{squad_name}/run", response_model=SquadRunResponse)
async def run_squad(squad_name: str, req: SquadRunRequest):
    """Run a squad pipeline end-to-end."""
    config = get_squad_config(squad_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Squad '{squad_name}' not found")

    if config.leader_class is None:
        raise HTTPException(status_code=500, detail=f"Squad '{squad_name}' has no leader configured")

    session_id = req.session_id or str(uuid.uuid4())

    initial_context = dict(req.context or {})
    if req.city:
        initial_context["city"] = req.city
    if req.max_leads:
        initial_context["max_leads"] = req.max_leads
    if req.url:
        initial_context["url"] = req.url

    state: AgentState = {
        "messages": [],
        "next_agent": config.leader_class.name,
        "task": req.task,
        "context": initial_context,
        "result": None,
        "error": None,
        "retries": 0,
        "session_id": session_id,
        "user_id": "squad",
        "agent_path": [],
    }

    leader = create_squad_leader(config)

    start = time.time()
    try:
        result = await leader(state)
    except Exception as e:
        log.error("squad.run_failed", squad=squad_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Squad execution failed: {e}")

    elapsed_ms = int((time.time() - start) * 1000)

    final_result = result.get("result", "No result produced")
    agent_path = result.get("agent_path", [])

    return SquadRunResponse(
        session_id=session_id,
        squad_name=squad_name,
        result=final_result,
        elapsed_ms=elapsed_ms,
        members_called=[a for a in agent_path if a != leader.name],
    )


@router.post("/run")
async def run_named_squad(squad: str, req: SquadRunRequest):
    """Run a squad by name (alternative endpoint)."""
    return await run_squad(squad, req)