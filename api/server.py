"""
FastAPI server: REST + WebSocket interface for the 30-agent system.
Endpoints:
  POST /api/chat       - Send task, get response
  GET  /api/agents     - List all agents
  GET  /api/health     - Health check
  GET  /api/metrics    - Agent metrics from Redis
  WS   /ws/{session}   - WebSocket streaming
"""
import asyncio
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from agents.registry import get_agent_info, register_all_agents
from core.config import settings
from core.graph import get_graph
from core.logging_setup import setup_logging
from core.ollama_client import get_ollama
from core.redis_client import get_redis
from squads.api import router as squads_router

from core.autopilot_scheduler import get_autopilot_scheduler
from core.discord_webhook import (
    get_config as get_discord_config,
    notify_agent_complete,
    notify_agent_error,
    update_webhook_url,
    set_notify_on,
    test_webhook,
)

log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────
# Startup / Shutdown
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log.info("server.starting")

    # Check Ollama
    ollama = get_ollama()
    ready = await ollama.wait_ready(max_wait=30)
    if not ready:
        log.warning("ollama.not_ready", msg="continuing anyway")

    # Check Redis
    redis = get_redis()
    redis_ok = await redis.ping()
    log.info("redis.status", ok=redis_ok)

    # Register all 30 agents
    register_all_agents()

    # Start autopilot scheduler
    autopilot_scheduler = get_autopilot_scheduler()
    await autopilot_scheduler.start()

    log.info("server.ready", port=settings.api_port)
    yield

    # Shutdown: clean up resources
    log.info("server.shutdown")
    try:
        await get_autopilot_scheduler().stop()
    except Exception:
        pass
    try:
        await get_ollama().close()
    except Exception:
        pass
    try:
        await get_redis().close()
    except Exception:
        pass


app = FastAPI(
    title="30-Agent Cognitive System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths that stay public (health + static UI shell + provider webhooks).
# Resend/Stripe cannot send API_SECRET — they use their own event payloads.
_PUBLIC_PATHS = frozenset({
    "/",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/docs/oauth2-redirect",
    "/api/webhooks/resend",
    "/api/webhooks/stripe",
})


def _extract_api_secret_values(headers, query_params) -> Optional[str]:
    """Headers first, then query — same order for HTTP and WebSocket."""
    api_key = headers.get("x-api-key")
    if api_key:
        return api_key
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return query_params.get("token") or query_params.get("api_key")


def _extract_api_secret(request: Request) -> Optional[str]:
    return _extract_api_secret_values(request.headers, request.query_params)


def _secret_ok(provided: Optional[str]) -> bool:
    expected = settings.api_secret
    if not expected or not provided:
        return False
    # compare_digest raises if lengths differ
    if len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


@app.middleware("http")
async def require_api_secret(request: Request, call_next):
    """Reject unauthenticated HTTP API calls when API_SECRET is configured.

    Fail closed if API_SECRET is unset (except public paths) so a misconfigured
    bind to 0.0.0.0 cannot expose outreach/send/chat.
    """
    if request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    if not settings.api_secret:
        return JSONResponse(
            {"detail": "API_SECRET not configured — refusing request"},
            status_code=503,
        )

    if not _secret_ok(_extract_api_secret(request)):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    return await call_next(request)


app.include_router(squads_router)


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    task: str
    session_id: Optional[str] = None
    user_id: Optional[str] = "user"
    context: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    session_id: str
    result: str
    agent_path: list[str]
    elapsed_ms: int


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    redis: bool
    models: list[str]
    agents_registered: int


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse)
async def health():
    ollama = get_ollama()
    redis = get_redis()

    ollama_ok = await ollama.health()
    redis_ok = await redis.ping()
    models = []
    if ollama_ok:
        try:
            models = await ollama.list_models()
        except Exception as e:
            log.warning("health.model_list_failed", error=str(e))

    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        ollama=ollama_ok,
        redis=redis_ok,
        models=models,
        agents_registered=len(get_agent_info()),
    )


# ──────────────────────────────────────────────
# Discord Webhook Configuration
# ──────────────────────────────────────────────
class WebhookUpdateRequest(BaseModel):
    webhook_url: Optional[str] = None
    enabled: Optional[bool] = None
    notify_on: Optional[list[str]] = None


@app.get("/api/webhook/discord")
async def get_discord_webhook_config():
    return get_discord_config()


@app.post("/api/webhook/discord")
async def update_discord_webhook(req: WebhookUpdateRequest):
    if req.webhook_url is not None:
        update_webhook_url(req.webhook_url)
    if req.notify_on is not None:
        set_notify_on(req.notify_on)
    return get_discord_config()


@app.post("/api/webhook/discord/test")
async def test_discord_webhook(webhook_url: Optional[str] = None):
    url = webhook_url or get_discord_config().get("webhook_url")
    if not url:
        raise HTTPException(status_code=400, detail="No webhook URL configured")
    result = await test_webhook(url)
    return result


@app.get("/api/agents")
async def list_agents():
    return {"agents": get_agent_info(), "total": len(get_agent_info())}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    graph = get_graph()

    # Build initial state with any provided context
    state_override = {}
    if req.context:
        state_override["context"] = req.context

    agent_path = []
    start = time.time()
    try:
        final_state = await asyncio.wait_for(
            graph.run(
                task=req.task,
                session_id=session_id,
                user_id=req.user_id or "user",
            ),
            timeout=settings.agent_timeout,
        )
    except asyncio.TimeoutError:
        await notify_agent_error(
            agent_name="orchestrator",
            task_summary=req.task[:200],
            duration=f"{settings.agent_timeout}s",
            error_message=f"Task timed out after {settings.agent_timeout}s",
        )
        raise HTTPException(
            status_code=504,
            detail=f"Task timed out after {settings.agent_timeout}s",
        )

    elapsed_ms = int((time.time() - start) * 1000)
    result = final_state.get("result") or final_state.get("error") or "No result produced"
    agent_path = final_state.get("agent_path") or []

    # Send Discord notification for task completion/failure
    duration_str = f"{elapsed_ms / 1000:.1f}s"
    if final_state.get("error"):
        await notify_agent_error(
            agent_name=agent_path[-1] if agent_path else "unknown",
            task_summary=req.task[:200],
            duration=duration_str,
            error_message=final_state["error"][:500],
        )
    else:
        await notify_agent_complete(
            agent_name=agent_path[-1] if agent_path else "unknown",
            task_summary=req.task[:200],
            duration=duration_str,
            result_summary=result[:200],
        )

    # Track in Redis
    try:
        redis = get_redis()
        await redis.lpush(
            f"history:{session_id}",
            {"task": req.task, "result": result[:500], "elapsed_ms": elapsed_ms},
        )
        await redis.expire(f"history:{session_id}", 86400)
    except Exception as e:
        log.debug("history.write_failed", error=str(e))

    return ChatResponse(
        session_id=session_id,
        result=result,
        agent_path=final_state.get("agent_path") or [],
        elapsed_ms=elapsed_ms,
    )


@app.get("/api/metrics")
async def metrics():
    redis = get_redis()
    result = {}
    for info in get_agent_info():
        key = f"agent:metrics:{info['name']}"
        data = await redis.hgetall(key)
        if data:
            result[info["name"]] = data
    return {"metrics": result}


@app.get("/api/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    redis = get_redis()
    items = await redis.lrange(f"history:{session_id}", 0, limit - 1)
    return {"session_id": session_id, "history": items}


# ══════════════════════════════════════════════════════════════
# Feedback / Self-Improvement Endpoints
# ══════════════════════════════════════════════════════════════
class CorrectionRequest(BaseModel):
    task: str
    wrong: str
    right: str
    agent: str = ""


@app.post("/api/feedback/correction")
async def log_feedback_correction(req: CorrectionRequest):
    from core.self_improve import log_correction
    return log_correction(req.task, req.wrong, req.right, req.agent)


# ══════════════════════════════════════════════════════════════
# Outreach Endpoints
# ══════════════════════════════════════════════════════════════
from pydantic import BaseModel
from typing import Optional

class ScrapeRequest(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    max_leads: Optional[int] = None


class EnrichRequest(BaseModel):
    leads: list[dict]


class GenerateRequest(BaseModel):
    leads: list[dict]


class SendRequest(BaseModel):
    emails: list[dict]
    dry_run: bool = True


class OutreachEmailResponse(BaseModel):
    id: str
    lead_name: str
    to_email: str
    from_email: str
    subject: str
    body: str
    status: str


@app.post("/api/outreach/scrape")
async def scrape_leads(req: ScrapeRequest):
    from agents.tier2_outreach import LeadScoutAgent
    from core.graph import AgentState

    agent = LeadScoutAgent()
    state: AgentState = {
        "messages": [],
        "next_agent": "orchestrator",
        "task": f"Find {req.city or settings.outreach_city} businesses without websites",
        "context": {
            "city": req.city or settings.outreach_city,
            "region": req.region or settings.outreach_region,
            "industry": req.industry or "",
            "max_leads": req.max_leads or settings.outreach_max_leads,
        },
        "result": None,
        "error": None,
        "retries": 0,
        "session_id": "outreach-scrape",
        "user_id": "outreach",
        "agent_path": [],
    }
    result = await agent(state)
    leads = result.get("context", {}).get("leads", [])
    return {"leads": leads, "count": len(leads), "result": result.get("result", "")}


@app.post("/api/outreach/enrich")
async def enrich_leads(req: EnrichRequest):
    from agents.tier2_outreach import EmailFinderAgent
    from core.graph import AgentState

    if not req.leads:
        raise HTTPException(status_code=400, detail="No leads provided")

    agent = EmailFinderAgent()
    state: AgentState = {
        "messages": [],
        "next_agent": "orchestrator",
        "task": "Find email addresses for these businesses",
        "context": {"leads": req.leads},
        "result": None,
        "error": None,
        "retries": 0,
        "session_id": "outreach-enrich",
        "user_id": "outreach",
        "agent_path": [],
    }
    result = await agent(state)
    leads = result.get("context", {}).get("leads", [])
    emails_found = result.get("context", {}).get("emails_found", 0)
    return {
        "leads": leads,
        "count": len(leads),
        "emails_found": emails_found,
        "result": result.get("result", ""),
    }


@app.post("/api/outreach/generate")
async def generate_emails(req: GenerateRequest):
    from agents.tier4_outreach import OutreachWriterAgent
    from core.graph import AgentState

    if not req.leads:
        raise HTTPException(status_code=400, detail="No leads provided")

    agent = OutreachWriterAgent()
    state: AgentState = {
        "messages": [],
        "next_agent": "orchestrator",
        "task": "Generate personalized cold emails for these leads",
        "context": {"leads": req.leads},
        "result": None,
        "error": None,
        "retries": 0,
        "session_id": "outreach-generate",
        "user_id": "outreach",
        "agent_path": [],
    }
    result = await agent(state)
    emails = result.get("context", {}).get("emails", [])
    return {
        "emails": emails,
        "count": len(emails),
        "result": result.get("result", ""),
    }


@app.post("/api/outreach/send")
async def send_emails(req: SendRequest):
    from core.config import settings
    import httpx

    if not req.emails:
        raise HTTPException(status_code=400, detail="No emails to send")

    key = settings.resend_api_key
    if not key:
        raise HTTPException(status_code=500, detail="RESEND_API_KEY not configured")

    results = []
    for em in req.emails:
        if not em.get("to_email") or em.get("to_email") == "unavailable":
            results.append({**em, "send_status": "skipped_no_email"})
            continue

        if req.dry_run:
            results.append({**em, "send_status": "dry_run_ok"})
            continue

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": em.get("from_email", settings.outreach_email_from),
                        "to": [em["to_email"]],
                        "subject": em["subject"],
                        "text": em["body"],
                    },
                )
                if resp.status_code in (200, 201, 202):
                    results.append({**em, "send_status": "sent"})
                else:
                    results.append({**em, "send_status": f"error_{resp.status_code}", "error": resp.text})
        except Exception as e:
            results.append({**em, "send_status": "exception", "error": str(e)})

    sent = sum(1 for r in results if r["send_status"] == "sent")
    skipped = sum(1 for r in results if "skipped" in r["send_status"])
    return {"results": results, "sent": sent, "skipped": skipped, "total": len(results)}


@app.post("/api/outreach/pipeline")
async def outreach_pipeline(city: Optional[str] = None, max_leads: int = 50, dry_run: bool = True):
    from agents.tier2_outreach import LeadScoutAgent, EmailFinderAgent
    from agents.tier4_outreach import OutreachWriterAgent
    from core.graph import AgentState

    city = city or settings.outreach_city

    # Step 1: Scrape
    scout = LeadScoutAgent()
    scrape_state: AgentState = {
        "messages": [], "next_agent": "orchestrator",
        "task": f"Find {city} businesses without websites",
        "context": {"city": city, "max_leads": max_leads},
        "result": None, "error": None, "retries": 0,
        "session_id": "pipeline", "user_id": "outreach", "agent_path": [],
    }
    scrape_result = await scout(scrape_state)
    leads = scrape_result.get("context", {}).get("leads", [])[:max_leads]

    if not leads:
        return {"stage": "scrape", "leads": [], "emails": [], "result": scrape_result.get("result", "")}

    # Step 2: Enrich
    enricher = EmailFinderAgent()
    enrich_state: AgentState = {
        "messages": [], "next_agent": "orchestrator",
        "task": "Find emails for these leads",
        "context": {"leads": leads},
        "result": None, "error": None, "retries": 0,
        "session_id": "pipeline", "user_id": "outreach", "agent_path": [],
    }
    enrich_result = await enricher(enrich_state)
    enriched = enrich_result.get("context", {}).get("leads", [])

    # Step 3: Generate
    writer = OutreachWriterAgent()
    write_state: AgentState = {
        "messages": [], "next_agent": "orchestrator",
        "task": "Generate outreach emails",
        "context": {"leads": enriched},
        "result": None, "error": None, "retries": 0,
        "session_id": "pipeline", "user_id": "outreach", "agent_path": [],
    }
    write_result = await writer(write_state)
    emails = write_result.get("context", {}).get("emails", [])

    # Step 4: Send
    send_results = []
    if not dry_run:
        sent = await _send_via_resend(emails)
        send_results = sent
    else:
        send_results = [
            {**em, "send_status": "dry_run_ok"}
            for em in emails if em.get("to_email") and em.get("to_email") != "unavailable"
        ]

    emails_with_send = [
        {**em, "send_status": next((r["send_status"] for r in send_results if r.get("id") == em.get("id")), "pending")}
        for em in emails
    ]

    return {
        "stage": "complete",
        "city": city,
        "leads_found": len(leads),
        "emails_generated": len(emails),
        "dry_run": dry_run,
        "send_results": send_results,
        "emails": emails_with_send,
    }


async def _send_via_resend(emails: list[dict]) -> list[dict]:
    import httpx
    from core.config import settings
    key = settings.resend_api_key
    results = []
    for em in emails:
        if not em.get("to_email") or em.get("to_email") == "unavailable":
            results.append({**em, "send_status": "skipped"})
            continue
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "from": em.get("from_email", settings.outreach_email_from),
                        "to": [em["to_email"]],
                        "subject": em["subject"],
                        "text": em["body"],
                    },
                )
                results.append({**em, "send_status": "sent" if resp.status_code < 300 else f"error_{resp.status_code}"})
        except Exception as e:
            results.append({**em, "send_status": f"exception: {e}"})
    return results


# ══════════════════════════════════════════════════════════════
# SEO & Web Design Endpoints
# ══════════════════════════════════════════════════════════════
class SEOAnalyzeRequest(BaseModel):
    url: str
    keyword: str = ""


class DesignConceptRequest(BaseModel):
    url: str = ""
    industry: str = ""
    city: str = "Vancouver"


class BacklinkRequest(BaseModel):
    url: str
    keyword: str = ""
    industry: str = ""
    city: str = "Vancouver"


@app.post("/api/seo/analyze")
async def seo_analyze(req: SEOAnalyzeRequest):
    from agents.tier2_seo_design import OnPageSEOAgent, TechnicalSEOAgent, ContentSEOAgent

    if not req.url:
        raise HTTPException(status_code=400, detail="URL required")

    context_base = {"url": req.url, "keyword": req.keyword}

    async def run_agent(AgentClass, session_suffix: str):
        state: AgentState = {
            "messages": [], "next_agent": "orchestrator",
            "task": f"Analyze {req.url}",
            "context": dict(context_base),
            "result": None, "error": None, "retries": 0,
            "session_id": f"seo-{session_suffix}", "user_id": "outreach", "agent_path": [],
        }
        agent = AgentClass()
        return await agent(state)

    onpage, technical, content = await asyncio.gather(
        run_agent(OnPageSEOAgent, "onpage"),
        run_agent(TechnicalSEOAgent, "technical"),
        run_agent(ContentSEOAgent, "content"),
    )

    onpage_score = onpage.get("context", {}).get("onpage_score", 0)
    technical_score = technical.get("context", {}).get("technical_score", 0)
    content_score = content.get("context", {}).get("content_score", 0)
    overall = (onpage_score + technical_score + content_score) / 3

    return {
        "url": req.url,
        "keyword": req.keyword,
        "overall_score": round(overall, 1),
        "on_page_seo": {"score": onpage_score, "audit": onpage.get("result", "")},
        "technical_seo": {"score": technical_score, "audit": technical.get("result", ""), "checks": technical.get("context", {}).get("technical_checks", {})},
        "content_seo": {"score": content_score, "audit": content.get("result", ""), "word_count": content.get("context", {}).get("word_count", 0)},
    }


@app.post("/api/seo/backlinks")
async def find_backlinks(req: BacklinkRequest):
    from agents.tier2_seo_design import BacklinkAgent
    from core.graph import AgentState

    if not req.url:
        raise HTTPException(status_code=400, detail="URL required")

    state: AgentState = {
        "messages": [], "next_agent": "orchestrator",
        "task": f"Find backlink opportunities for {req.url}",
        "context": {"url": req.url, "keyword": req.keyword, "industry": req.industry, "city": req.city},
        "result": None, "error": None, "retries": 0,
        "session_id": "backlink", "user_id": "outreach", "agent_path": [],
    }
    agent = BacklinkAgent()
    result = await agent(state)
    opportunities = result.get("context", {}).get("backlink_opportunities", [])
    summary = result.get("context", {}).get("backlink_summary", {})

    return {
        "url": req.url,
        "opportunities": opportunities,
        "summary": summary,
        "total": len(opportunities),
        "result": result.get("result", ""),
    }


@app.post("/api/design/concept")
async def design_concept(req: DesignConceptRequest):
    from agents.tier2_seo_design import WebDesignConceptAgent
    from core.graph import AgentState

    state: AgentState = {
        "messages": [], "next_agent": "orchestrator",
        "task": f"Research design trends for {req.industry} businesses",
        "context": {"url": req.url, "industry": req.industry, "city": req.city},
        "result": None, "error": None, "retries": 0,
        "session_id": "design-concept", "user_id": "outreach", "agent_path": [],
    }
    agent = WebDesignConceptAgent()
    result = await agent(state)
    design_concept = result.get("context", {}).get("design_concept", result.get("result", ""))
    trend_sources = result.get("context", {}).get("trend_sources", [])

    return {
        "url": req.url,
        "industry": req.industry,
        "city": req.city,
        "design_concept": design_concept,
        "trend_sources": trend_sources,
        "result": result.get("result", ""),
    }


@app.post("/api/seo/pipeline")
async def seo_pipeline(url: str, keyword: str = "", industry: str = ""):
    from agents.tier2_seo_design import OnPageSEOAgent, TechnicalSEOAgent, ContentSEOAgent, BacklinkAgent
    from core.graph import AgentState

    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    context = {"url": url, "keyword": keyword, "industry": industry}

    async def run_agent(AgentClass, session_suffix: str):
        state: AgentState = {
            "messages": [], "next_agent": "orchestrator",
            "task": f"Analyze {url}",
            "context": dict(context),
            "result": None, "error": None, "retries": 0,
            "session_id": f"seo-pipeline-{session_suffix}", "user_id": "outreach", "agent_path": [],
        }
        agent = AgentClass()
        return await agent(state)

    onpage, technical, content, backlinks = await asyncio.gather(
        run_agent(OnPageSEOAgent, "onpage"),
        run_agent(TechnicalSEOAgent, "technical"),
        run_agent(ContentSEOAgent, "content"),
        run_agent(BacklinkAgent, "backlinks"),
    )

    onpage_score = onpage.get("context", {}).get("onpage_score", 0)
    technical_score = technical.get("context", {}).get("technical_score", 0)
    content_score = content.get("context", {}).get("content_score", 0)
    opportunities = backlinks.get("context", {}).get("backlink_opportunities", [])
    overall = (onpage_score + technical_score + content_score) / 3

    return {
        "url": url,
        "keyword": keyword,
        "overall_seo_score": round(overall, 1),
        "on_page_seo": {"score": onpage_score},
        "technical_seo": {"score": technical_score},
        "content_seo": {"score": content_score},
        "backlink_opportunities": opportunities[:30],
        "total_opportunities": len(opportunities),
        "quick_wins": [op for op in opportunities if op.get("difficulty") == "EASY"][:10],
    }


# ──────────────────────────────────────────────
# Autopilot Endpoints
# ──────────────────────────────────────────────
class CreateAutopilotRequest(BaseModel):
    name: str
    agent_name: str
    cron: str
    task_template: str
    timezone: str = "UTC"
    inputs: dict = {}
    webhook_url: str | None = None
    notify_on: list[str] = ["failure"]


class UpdateAutopilotRequest(BaseModel):
    enabled: bool | None = None
    webhook_url: str | None = None
    notify_on: list[str] | None = None


@app.get("/api/autopilots")
async def list_autopilots():
    scheduler = get_autopilot_scheduler()
    autopilots = await scheduler.list_autopilots()
    return {
        "autopilots": [
            {
                "id": a.id,
                "name": a.name,
                "agent_name": a.agent_name,
                "cron": a.cron,
                "timezone": a.timezone,
                "task_template": a.task_template,
                "inputs": a.inputs,
                "enabled": a.enabled,
                "webhook_url": a.webhook_url,
                "notify_on": a.notify_on,
                "last_run": a.last_run,
                "next_run": a.next_run,
                "run_count": a.run_count,
            }
            for a in autopilots
        ]
    }


@app.post("/api/autopilots")
async def create_autopilot(req: CreateAutopilotRequest):
    scheduler = get_autopilot_scheduler()
    try:
        config = await scheduler.create_autopilot(
            name=req.name,
            agent_name=req.agent_name,
            cron=req.cron,
            task_template=req.task_template,
            timezone=req.timezone,
            inputs=req.inputs,
            webhook_url=req.webhook_url,
            notify_on=req.notify_on,
        )
        return {
            "id": config.id,
            "name": config.name,
            "agent_name": config.agent_name,
            "cron": config.cron,
            "timezone": config.timezone,
            "enabled": config.enabled,
            "next_run": config.next_run,
            "message": f"Autopilot '{config.name}' created successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/autopilots/{autopilot_id}")
async def get_autopilot(autopilot_id: str):
    scheduler = get_autopilot_scheduler()
    config = await scheduler.get_autopilot(autopilot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Autopilot not found")
    return {
        "id": config.id,
        "name": config.name,
        "agent_name": config.agent_name,
        "cron": config.cron,
        "timezone": config.timezone,
        "task_template": config.task_template,
        "inputs": config.inputs,
        "enabled": config.enabled,
        "webhook_url": config.webhook_url,
        "notify_on": config.notify_on,
        "last_run": config.last_run,
        "next_run": config.next_run,
        "run_count": config.run_count,
    }


@app.patch("/api/autopilots/{autopilot_id}")
async def update_autopilot(autopilot_id: str, req: UpdateAutopilotRequest):
    scheduler = get_autopilot_scheduler()
    if req.enabled is not None:
        config = await scheduler.toggle_autopilot(autopilot_id, req.enabled)
        if not config:
            raise HTTPException(status_code=404, detail="Autopilot not found")
        return {"id": config.id, "enabled": config.enabled, "message": f"Autopilot {'enabled' if config.enabled else 'disabled'}"}
    if req.webhook_url is not None or req.notify_on is not None:
        config = await scheduler.get_autopilot(autopilot_id)
        if not config:
            raise HTTPException(status_code=404, detail="Autopilot not found")
        if req.webhook_url is not None:
            config.webhook_url = req.webhook_url
        if req.notify_on is not None:
            config.notify_on = req.notify_on
        await scheduler._save_autopilot(config)
        return {"id": config.id, "message": "Autopilot updated"}
    raise HTTPException(status_code=400, detail="No updates provided")


@app.delete("/api/autopilots/{autopilot_id}")
async def delete_autopilot(autopilot_id: str):
    scheduler = get_autopilot_scheduler()
    config = await scheduler.get_autopilot(autopilot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Autopilot not found")
    await scheduler.delete_autopilot(autopilot_id)
    return {"message": f"Autopilot '{config.name}' deleted"}


@app.get("/api/autopilots/{autopilot_id}/history")
async def get_autopilot_history(autopilot_id: str, limit: int = 10):
    from core.redis_client import get_redis
    redis = get_redis()
    key = f"autopilot:history:{autopilot_id}"
    runs = await redis.lrange(key, 0, limit - 1)
    return {"history": [json.loads(r) for r in runs]}


# ══════════════════════════════════════════════════════════════
# Lead Pipeline Endpoints
# ══════════════════════════════════════════════════════════════

class LeadBatchRequest(BaseModel):
    leads: list[dict]

class LeadEnrichStages(BaseModel):
    stages: Optional[list[str]] = None

@app.post("/api/leads/deduplicate")
async def deduplicate_leads(req: LeadBatchRequest):
    from core.lead_manager import LeadDeduplicator
    dedup = LeadDeduplicator()
    result = await dedup.deduplicate(req.leads)
    return {"leads": result, "count": len(result)}

@app.post("/api/leads/score")
async def score_leads(req: LeadBatchRequest):
    from core.lead_manager import LeadScorer
    scorer = LeadScorer()
    result = scorer.score_all(req.leads)
    return {"leads": result, "count": len(result)}

@app.post("/api/leads/enrich")
async def enrich_leads(req: LeadBatchRequest):
    from core.lead_manager import LeadPipeline
    pipeline = LeadPipeline()
    result = await pipeline.process(req.leads)
    return {"leads": result, "count": len(result)}

@app.get("/api/leads/pipeline/{batch_id}")
async def get_lead_batch(batch_id: str):
    from core.lead_manager import LeadPipeline
    pipeline = LeadPipeline()
    result = await pipeline.get_batch(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"batch_id": batch_id, "leads": result, "count": len(result)}

@app.get("/api/leads/batches")
async def list_lead_batches():
    from core.lead_manager import LeadPipeline
    pipeline = LeadPipeline()
    batches = await pipeline.list_batches()
    return {"batches": batches, "count": len(batches)}

@app.post("/api/leads/enrich/batch")
async def enrich_leads_full(req: LeadBatchRequest, stages: Optional[str] = None):
    from core.lead_enrichment import EnrichmentPipeline
    pipeline = EnrichmentPipeline()
    stage_list = stages.split(",") if stages else None
    result = await pipeline.enrich_batch(req.leads, stage_list)
    return {"leads": result, "count": len(result)}

@app.post("/api/leads/validate")
async def validate_leads(req: LeadBatchRequest):
    from core.lead_enrichment import LeadValidator
    validator = LeadValidator()
    stats = validator.get_validation_stats(req.leads)
    valid = validator.filter_valid(req.leads)
    return {"stats": stats, "valid_leads": valid, "count": len(valid)}

@app.post("/api/leads/classify")
async def classify_leads(req: LeadBatchRequest):
    from core.lead_enrichment import IndustryClassifier
    classifier = IndustryClassifier()
    result = classifier.classify_batch(req.leads)
    return {"leads": result, "count": len(result)}

@app.get("/api/leads/categories")
async def get_industry_categories():
    from core.lead_enrichment import IndustryClassifier
    return {"categories": IndustryClassifier.get_categories()}

@app.get("/api/leads/enriched/{lead_id}")
async def get_enriched_lead(lead_id: str):
    from core.lead_enrichment import EnrichmentPipeline
    pipeline = EnrichmentPipeline()
    result = await pipeline.get_enriched(lead_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result

# ══════════════════════════════════════════════════════════════
# Campaign Endpoints
# ══════════════════════════════════════════════════════════════

class CampaignCreateRequest(BaseModel):
    name: str
    city: str
    max_leads: int = 50

class LeadTransitionRequest(BaseModel):
    state: str
    metadata: Optional[dict] = None

@app.get("/api/campaigns")
async def list_campaigns(status: Optional[str] = None):
    from core.campaign_tracker import CampaignTracker
    tracker = CampaignTracker()
    campaigns = await tracker.list_campaigns(status)
    return {"campaigns": campaigns, "count": len(campaigns)}

@app.post("/api/campaigns")
async def create_campaign(req: CampaignCreateRequest):
    from core.campaign_tracker import CampaignTracker
    tracker = CampaignTracker()
    campaign_id = await tracker.create_campaign(req.name, req.city, req.max_leads)
    campaign = await tracker.get_campaign(campaign_id)
    return {"campaign_id": campaign_id, "campaign": campaign}

@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    from core.campaign_tracker import CampaignTracker
    tracker = CampaignTracker()
    campaign = await tracker.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@app.get("/api/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: str):
    from core.campaign_tracker import CampaignStats
    stats = CampaignStats()
    result = await stats.get_stats(campaign_id, use_cache=False)
    if not result:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result

@app.get("/api/campaigns/{campaign_id}/leads")
async def get_campaign_leads(campaign_id: str, state: Optional[str] = None):
    from core.campaign_tracker import LeadStateMachine
    machine = LeadStateMachine()
    if state:
        leads = await machine.get_leads_by_state(campaign_id, state)
        return {"campaign_id": campaign_id, "state": state, "leads": leads, "count": len(leads)}
    return {"campaign_id": campaign_id, "message": "Specify ?state= to filter leads"}

@app.patch("/api/campaigns/{campaign_id}/leads/{lead_id}")
async def transition_lead(campaign_id: str, lead_id: str, req: LeadTransitionRequest):
    from core.campaign_tracker import LeadStateMachine
    machine = LeadStateMachine()
    ok = await machine.transition(lead_id, campaign_id, req.state, req.metadata)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid state transition")
    state = await machine.get_state(lead_id, campaign_id)
    return {"lead_id": lead_id, "state": state}

@app.post("/api/webhooks/resend")
async def resend_webhook(event: dict):
    from core.campaign_tracker import handle_resend_webhook
    result = await handle_resend_webhook(event)
    return result

@app.get("/api/stats/aggregate")
async def aggregate_stats():
    from core.campaign_tracker import CampaignStats
    stats = CampaignStats()
    result = await stats.get_aggregate_stats()
    return result

# ══════════════════════════════════════════════════════════════
# A/B Testing Endpoints
# ══════════════════════════════════════════════════════════════

class ABTestCreateRequest(BaseModel):
    name: str
    campaign_id: str
    variants: list[dict]

class ABTestRecordRequest(BaseModel):
    lead_id: str
    event: str

@app.post("/api/ab-tests")
async def create_ab_test(req: ABTestCreateRequest):
    from core.ab_testing import ABTest
    ab = ABTest()
    test_id = await ab.create_test(req.name, req.campaign_id, req.variants)
    test = await ab.get_test(test_id)
    return {"test_id": test_id, "test": test}

@app.get("/api/ab-tests")
async def list_ab_tests(campaign_id: Optional[str] = None):
    from core.ab_testing import ABTest
    ab = ABTest()
    tests = await ab.list_tests(campaign_id)
    return {"tests": tests, "count": len(tests)}

@app.get("/api/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    from core.ab_testing import ABTest
    ab = ABTest()
    test = await ab.get_test(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="A/B test not found")
    return test

@app.get("/api/ab-tests/{test_id}/results")
async def get_ab_results(test_id: str):
    from core.ab_testing import ABAnalyzer
    analyzer = ABAnalyzer()
    return await analyzer.get_results(test_id)

@app.get("/api/ab-tests/{test_id}/winner")
async def get_ab_winner(test_id: str):
    from core.ab_testing import ABAnalyzer
    analyzer = ABAnalyzer()
    return await analyzer.get_winner(test_id)

@app.post("/api/ab-tests/{test_id}/record")
async def record_ab_event(test_id: str, req: ABTestRecordRequest):
    from core.ab_testing import ResultsTracker
    tracker = ResultsTracker()
    if req.event == "send":
        await tracker.record_send(req.lead_id, test_id)
    elif req.event == "open":
        await tracker.record_open(req.lead_id, test_id)
    elif req.event == "reply":
        await tracker.record_reply(req.lead_id, test_id)
    elif req.event == "bounce":
        await tracker.record_bounce(req.lead_id, test_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown event: {req.event}")
    return {"status": "recorded", "event": req.event, "lead_id": req.lead_id}

# ══════════════════════════════════════════════════════════════
# SEO Tracking Endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/api/seo/audits/{domain}")
async def list_seo_audits(domain: str, limit: int = 10):
    from core.seo_tracker import SEOAuditStore
    store = SEOAuditStore()
    audits = await store.list_audits(domain, limit)
    return {"domain": domain, "audits": audits, "count": len(audits)}

@app.get("/api/seo/audits/{domain}/latest")
async def get_latest_seo_audit(domain: str):
    from core.seo_tracker import SEOAuditStore
    store = SEOAuditStore()
    audit = await store.get_latest(domain)
    if not audit:
        raise HTTPException(status_code=404, detail="No audits found for domain")
    return audit

@app.get("/api/seo/audits/{domain}/trend")
async def get_seo_trend(domain: str, days: int = 90):
    from core.seo_tracker import SEOChangeTracker
    tracker = SEOChangeTracker()
    return await tracker.get_score_trend(domain, days)

@app.get("/api/seo/compare")
async def compare_seo_audits(domain: str, id1: str, id2: str):
    from core.seo_tracker import SEOChangeTracker
    tracker = SEOChangeTracker()
    return await tracker.compare(domain, id1, id2)

class CompetitorAddRequest(BaseModel):
    competitor_url: str
    label: Optional[str] = None

@app.post("/api/seo/competitors/{domain}")
async def add_competitor(domain: str, req: CompetitorAddRequest):
    from core.seo_tracker import CompetitorMonitor
    monitor = CompetitorMonitor()
    await monitor.add_competitor(domain, req.competitor_url, req.label)
    return {"status": "added", "domain": domain, "competitor": req.competitor_url}

@app.get("/api/seo/competitors/{domain}")
async def list_competitors(domain: str):
    from core.seo_tracker import CompetitorMonitor
    monitor = CompetitorMonitor()
    competitors = await monitor.get_competitors(domain)
    return {"domain": domain, "competitors": competitors, "count": len(competitors)}

@app.get("/api/seo/competitors/{domain}/compare")
async def compare_competitors(domain: str):
    from core.seo_tracker import CompetitorMonitor
    monitor = CompetitorMonitor()
    return await monitor.compare_competitors(domain)

@app.get("/api/seo/report/weekly")
async def seo_weekly_report():
    from core.seo_tracker import SEOReportGenerator
    gen = SEOReportGenerator()
    return await gen.generate_weekly()

@app.get("/api/seo/report/monthly")
async def seo_monthly_report():
    from core.seo_tracker import SEOReportGenerator
    gen = SEOReportGenerator()
    return await gen.generate_monthly()

# ══════════════════════════════════════════════════════════════
# KPI Endpoints
# ══════════════════════════════════════════════════════════════

class KPIRecordRequest(BaseModel):
    name: str
    value: float
    tags: Optional[dict] = None

class KPIThresholdRequest(BaseModel):
    name: str
    warn: float
    critical: float
    direction: str = "lower_is_better"

@app.get("/api/kpis")
async def get_all_kpis():
    from core.kpi_tracker import KPITracker
    kpi = KPITracker()
    values = await kpi.get_all_current()
    return {"kpis": values}

@app.get("/api/kpis/{name}")
async def get_kpi(name: str):
    from core.kpi_tracker import KPITracker
    kpi = KPITracker()
    current = await kpi.get_current(name)
    history = await kpi.get_history(name, days=30)
    return {"name": name, "current": current, "history": history}

@app.get("/api/kpis/{name}/history")
async def get_kpi_history(name: str, days: int = 30):
    from core.kpi_tracker import KPITracker
    kpi = KPITracker()
    history = await kpi.get_history(name, days)
    return {"name": name, "history": history, "count": len(history)}

@app.post("/api/kpis/record")
async def record_kpi(req: KPIRecordRequest):
    from core.kpi_tracker import KPITracker
    kpi = KPITracker()
    await kpi.record(req.name, req.value, req.tags)
    return {"status": "recorded", "name": req.name, "value": req.value}

@app.get("/api/kpis/alerts")
async def get_kpi_alerts():
    from core.kpi_tracker import KPIAlerts
    alerts = KPIAlerts()
    statuses = await alerts.check_all()
    history = await alerts.get_alert_history(50)
    return {"statuses": statuses, "history": history}

@app.post("/api/kpis/alerts/thresholds")
async def set_kpi_threshold(req: KPIThresholdRequest):
    from core.kpi_tracker import KPIAlerts
    alerts = KPIAlerts()
    await alerts.set_threshold(req.name, req.warn, req.critical, req.direction)
    return {"status": "threshold_set", "name": req.name}

# ══════════════════════════════════════════════════════════════
# Report Endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/api/reports/weekly")
async def get_weekly_report():
    from core.report_generator import WeeklyDigest
    digest = WeeklyDigest()
    return await digest.generate()

@app.post("/api/reports/weekly/send")
async def send_weekly_report_discord():
    from core.report_generator import WeeklyDigest
    digest = WeeklyDigest()
    sent = await digest.send_to_discord()
    return {"sent": sent}

@app.get("/api/reports/monthly")
async def get_monthly_report():
    from core.report_generator import MonthlyReport
    report = MonthlyReport()
    return await report.generate()

@app.post("/api/reports/monthly/send")
async def send_monthly_report_discord():
    from core.report_generator import MonthlyReport
    report = MonthlyReport()
    sent = await report.send_to_discord()
    return {"sent": sent}

@app.get("/api/reports/costs")
async def get_cost_report():
    from core.report_generator import AgentCostReport
    report = AgentCostReport()
    return await report.estimate_cost()

# ══════════════════════════════════════════════════════════════
# Invoice Endpoints
# ══════════════════════════════════════════════════════════════

class InvoiceCreateRequest(BaseModel):
    lead: dict
    items: Optional[list[dict]] = None

@app.post("/api/invoices")
async def create_invoice(req: InvoiceCreateRequest):
    from core.invoice_system import get_invoice_pipeline
    pipeline = get_invoice_pipeline()
    result = await pipeline.deal_to_invoice(req.lead, req.items)
    return result

@app.get("/api/invoices")
async def list_invoices():
    from core.invoice_system import get_invoice_pipeline
    pipeline = get_invoice_pipeline()
    pipelines = await pipeline.list_pipelines()
    return {"invoices": pipelines, "count": len(pipelines)}

@app.get("/api/invoices/{pipeline_id}")
async def get_invoice(pipeline_id: str):
    from core.invoice_system import get_invoice_pipeline
    pipeline = get_invoice_pipeline()
    result = await pipeline.get_pipeline(pipeline_id)
    if not result:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return result

@app.post("/api/invoices/{pipeline_id}/send")
async def send_invoice(pipeline_id: str):
    return {"pipeline_id": pipeline_id, "message": "Invoice send requires Zoho configuration"}

@app.get("/api/invoices/{pipeline_id}/payment-link")
async def get_payment_link(pipeline_id: str):
    from core.invoice_system import get_invoice_pipeline
    pipeline = get_invoice_pipeline()
    state = await pipeline.get_pipeline(pipeline_id)
    if not state:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"payment_link": state.get("payment_link"), "status": state.get("status")}

@app.post("/api/webhooks/stripe")
async def stripe_webhook(event: dict):
    from core.invoice_system import get_invoice_pipeline
    pipeline = get_invoice_pipeline()
    result = await pipeline.handle_stripe_webhook(event)
    return result

@app.post("/api/invoices/test")
async def test_invoice_config():
    from core.invoice_system import ZohoInvoiceClient, StripePaymentLink
    from core.config import settings
    zoho_ok = False
    stripe_ok = False
    try:
        zoho = ZohoInvoiceClient(
            org_id=getattr(settings, "zoho_org_id", None),
            api_token=getattr(settings, "zoho_api_token", None),
        )
        zoho_ok = zoho.configured
    except Exception:
        pass
    try:
        stripe = StripePaymentLink(api_key=getattr(settings, "stripe_api_key", None))
        stripe_ok = stripe.configured
    except Exception:
        pass
    return {"zoho_configured": zoho_ok, "stripe_configured": stripe_ok}

# ══════════════════════════════════════════════════════════════
# Skill Mapping Endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/api/skills/mappings")
async def get_skill_mappings():
    from core.skill_mapper import SkillRegistry
    registry = SkillRegistry()
    return {"mappings": registry.get_all(), "count": registry.get_mapped_count()}

@app.get("/api/skills/agent/{agent_name}")
async def get_agent_skills(agent_name: str):
    from core.skill_mapper import SkillMapper
    mapper = SkillMapper()
    skills = mapper.find_skills_for_agent(agent_name)
    return {"agent": agent_name, "skills": skills, "count": len(skills)}

@app.get("/api/skills/skill/{skill_name}")
async def get_skill_agent(skill_name: str):
    from core.skill_mapper import SkillMapper
    mapper = SkillMapper()
    result = mapper.find_agent_for_skill(skill_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"No agent mapped for skill: {skill_name}")
    return result

@app.get("/api/skills/suggest")
async def suggest_agent(task: str):
    from core.skill_mapper import SkillMapper
    mapper = SkillMapper()
    return mapper.suggest_agent(task)

@app.get("/api/skills/coverage")
async def get_skill_coverage():
    from core.skill_mapper import SkillMapper
    mapper = SkillMapper()
    return mapper.get_coverage_stats()

@app.get("/api/skills/profiles")
async def get_skill_profiles():
    from core.skill_mapper import AgentSkillProfile
    profile = AgentSkillProfile()
    profiles = profile.list_all_profiles()
    return {"profiles": profiles, "count": len(profiles)}

class SkillMappingRequest(BaseModel):
    agent_name: str
    relevance: int = 80
    category: str = "general"

@app.post("/api/skills/mappings/{skill_name}")
async def update_skill_mapping(skill_name: str, req: SkillMappingRequest):
    from core.skill_mapper import SkillRegistry
    registry = SkillRegistry()
    registry.set_mapping(skill_name, req.agent_name, req.relevance, req.category)
    return {"status": "mapped", "skill": skill_name, "agent": req.agent_name}

# ══════════════════════════════════════════════════════════════
# Discord Extended Endpoints
# ══════════════════════════════════════════════════════════════

@app.post("/api/discord/daily-summary")
async def trigger_daily_summary():
    from core.discord_webhook import send_daily_summary
    sent = await send_daily_summary()
    return {"sent": sent}

@app.post("/api/discord/weekly-summary")
async def trigger_weekly_summary():
    from core.discord_webhook import send_weekly_summary
    sent = await send_weekly_summary()
    return {"sent": sent}

class AlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "info"

@app.post("/api/discord/alert")
async def send_discord_alert(req: AlertRequest):
    from core.discord_webhook import send_alert
    sent = await send_alert(req.title, req.message, req.severity)
    return {"sent": sent}

@app.get("/api/discord/alerts/history")
async def get_alert_history(limit: int = 50):
    from core.discord_webhook import get_alert_history
    history = get_alert_history(limit)
    return {"history": history, "count": len(history)}

@app.post("/api/discord/health")
async def send_health_report_discord():
    ollama = get_ollama()
    redis = get_redis()
    ollama_ok = await ollama.health()
    redis_ok = await redis.ping()
    models = []
    try:
        models = await ollama.list_models()
    except Exception:
        pass
    health_data = {
        "status": "ok" if ollama_ok and redis_ok else "degraded",
        "ollama": ollama_ok,
        "redis": redis_ok,
        "models": models,
        "agents_registered": len(get_agent_info()),
    }
    from core.discord_webhook import send_health_report
    sent = await send_health_report(health_data)
    return {"sent": sent, "health": health_data}

# ══════════════════════════════════════════════════════════════
# Autopilot Groups Endpoints
# ══════════════════════════════════════════════════════════════

class AutopilotGroupRequest(BaseModel):
    name: str
    autopilot_ids: list[str]

@app.get("/api/autopilots/groups")
async def list_autopilot_groups():
    scheduler = get_autopilot_scheduler()
    groups = await scheduler.list_groups()
    return {"groups": groups, "count": len(groups)}

@app.post("/api/autopilots/groups")
async def create_autopilot_group(req: AutopilotGroupRequest):
    scheduler = get_autopilot_scheduler()
    group_id = await scheduler.create_group(req.name, req.autopilot_ids)
    group = await scheduler.get_group(group_id)
    return {"group_id": group_id, "group": group}

@app.get("/api/autopilots/groups/{group_id}")
async def get_autopilot_group(group_id: str):
    scheduler = get_autopilot_scheduler()
    group = await scheduler.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group

@app.post("/api/autopilots/groups/{group_id}/run")
async def run_autopilot_group(group_id: str):
    scheduler = get_autopilot_scheduler()
    result = await scheduler.run_group(group_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ──────────────────────────────────────────────
# WebSocket endpoint
# ──────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    # Same extraction order as HTTP (headers then ?token= for browser UI).
    provided = _extract_api_secret_values(websocket.headers, websocket.query_params)

    if not settings.api_secret or not _secret_ok(provided):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    graph = get_graph()

    try:
        while True:
            data = await websocket.receive_text()
            try:
                req = json.loads(data)
                task = req.get("task", "")
            except Exception:
                task = data

            await websocket.send_json({"type": "start", "session_id": session_id})

            try:
                final_state = await asyncio.wait_for(
                    graph.run(task=task, session_id=session_id),
                    timeout=settings.agent_timeout,
                )
                result = final_state.get("result") or "No result"
                agent_path = final_state.get("agent_path") or []
            except asyncio.TimeoutError:
                result = "Timed out"
                agent_path = []
            except Exception as e:
                result = f"Error: {e}"
                agent_path = []

            await websocket.send_json(
                {"type": "result", "result": result, "agent_path": agent_path, "session_id": session_id}
            )

    except WebSocketDisconnect:
        log.info("ws.disconnect", session=session_id)


# ──────────────────────────────────────────────
# Simple HTML UI
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    ui_path = Path(__file__).parent / "ui" / "index.html"
    return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))


# Keep legacy helper name for any imports/tests; prefer file-backed UI.
def _get_ui_html() -> str:
    ui_path = Path(__file__).parent / "ui" / "index.html"
    return ui_path.read_text(encoding="utf-8")

