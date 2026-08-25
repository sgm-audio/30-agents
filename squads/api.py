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
from core.safety import validate_public_http_url
from squads import ALL_SQUADS
from squads.base import SquadLeader
from squads.registry import get_squad_config, create_squad_leader

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/squads", tags=["squads"])

# ponytail: hard hop ceiling; raise if a squad legitimately needs >20 member hops
MAX_SQUAD_HOPS = 20


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


def merge_state(state: AgentState, update: dict[str, Any]) -> AgentState:
    """Apply a partial agent update onto state (shallow merge)."""
    merged = dict(state)
    for key, value in update.items():
        if key == "context" and isinstance(value, dict):
            ctx = dict(merged.get("context") or {})
            ctx.update(value)
            merged["context"] = ctx
        else:
            merged[key] = value
    return merged  # type: ignore[return-value]


async def run_squad_loop(
    leader: SquadLeader,
    state: AgentState,
    *,
    max_hops: int = MAX_SQUAD_HOPS,
) -> tuple[AgentState, list[str]]:
    """Drive the squad leader until it sets result / END / error.

    SquadLeader.execute on stage \"start\" only routes; on \"delegating\" it
    runs members itself. Calling the leader once left REST with no result —
    this loop finishes the pipeline.
    """
    members_called: list[str] = []
    current = state

    for hop in range(max_hops):
        update = await leader(current)
        current = merge_state(current, update)

        member = (current.get("context") or {}).get("squad_member")
        if member and member not in members_called:
            members_called.append(member)

        next_agent = update.get("next_agent")
        if update.get("result") is not None:
            break
        if update.get("error"):
            break
        if next_agent in (None, "END", "orchestrator"):
            break

        log.debug("squad.hop", hop=hop + 1, next=next_agent, member=member)
    else:
        current = merge_state(
            current,
            {
                "result": current.get("result")
                or f"Squad stopped after {max_hops} hops without a final result.",
                "error": "max_hops_exceeded",
            },
        )

    return current, members_called


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
        safe_url = validate_public_http_url(req.url)
        if not safe_url:
            raise HTTPException(status_code=400, detail="Unsafe or invalid URL")
        initial_context["url"] = safe_url

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
        final_state, members_called = await run_squad_loop(leader, state)
    except Exception as e:
        log.error("squad.run_failed", squad=squad_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Squad execution failed: {e}")

    elapsed_ms = int((time.time() - start) * 1000)
    final_result = final_state.get("result") or "No result produced"

    return SquadRunResponse(
        session_id=session_id,
        squad_name=squad_name,
        result=final_result,
        elapsed_ms=elapsed_ms,
        members_called=members_called,
    )


@router.post("/run")
async def run_named_squad(squad: str, req: SquadRunRequest):
    """Run a squad by name (alternative endpoint)."""
    return await run_squad(squad, req)
