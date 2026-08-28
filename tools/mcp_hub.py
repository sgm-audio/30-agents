#!/usr/bin/env python3
"""
mcp_hub.py — MCP stdio bridge exposing the 30-agent REST API as MCP tools.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio).
stdout is reserved for protocol frames; ALL logging goes to stderr.

Behavior:
  - Probes GET /api/health on startup; optionally spawns `python main.py serve`
    when unreachable (AGENTS30_AUTO_START=1, default).
  - Sends X-API-Key on every API call when AGENTS30_API_SECRET / API_SECRET set.
  - Exits when stdin closes; stops the API server only if this process spawned
    it AND AGENTS30_AUTO_STOP=1.

Env:
  AGENTS30_API_BASE             default http://127.0.0.1:8000
  AGENTS30_API_SECRET           API key (fallback: API_SECRET)
  AGENTS30_TIMEOUT              per-request timeout seconds (default 180)
  AGENTS30_AUTO_START           1 = spawn API server if unreachable (default 1)
  AGENTS30_AUTO_STOP            1 = stop spawned server on exit (default 0)
  AGENTS30_API_SECRET_REQUIRED  1 = refuse to start without a key (default 0)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"

API_BASE = os.environ.get("AGENTS30_API_BASE", "http://127.0.0.1:8000").rstrip("/")
API_SECRET = os.environ.get("AGENTS30_API_SECRET") or os.environ.get("API_SECRET", "")
API_TIMEOUT = float(os.environ.get("AGENTS30_TIMEOUT", "180"))
AUTO_START = os.environ.get("AGENTS30_AUTO_START", "1") == "1"
AUTO_STOP = os.environ.get("AGENTS30_AUTO_STOP", "0") == "1"
SECRET_REQUIRED = os.environ.get("AGENTS30_API_SECRET_REQUIRED", "0") == "1"

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="mcp_hub %(levelname)s %(message)s")
log = logging.getLogger("mcp_hub")

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: Optional[Dict] = None, query: Optional[Dict] = None) -> Any:
    url = f"{API_BASE}{path}"
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        if qs:
            url = f"{url}?{qs}"
    headers = {"Accept": "application/json"}
    if API_SECRET:
        headers["X-API-Key"] = API_SECRET
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {detail[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach 30-agent API at {API_BASE}: {e.reason}") from e


def _tool_result(payload: Any, is_error: bool = False) -> Dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}

# ---------------------------------------------------------------------------
# Tool definitions (14 tools; keep name list unique — clients reject dupes)
# ---------------------------------------------------------------------------

TOOLS: list[Dict[str, Any]] = [
    {
        "name": "agent_chat",
        "description": "Run a task through the 30-agent orchestrator (LangGraph). General reasoning, coding, writing, research, multi-step work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Natural-language task for the agents"},
                "session_id": {"type": "string", "description": "Optional session ID for continuity"},
                "user_id": {"type": "string", "description": "Optional user ID", "default": "mcp"},
                "context": {"type": "object", "description": "Optional context dict passed into agent state"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_agents",
        "description": "List all registered specialist agents and their metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_squads",
        "description": "List available squad pipelines (outreach, seo, analytics, content, code, vision).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_squad",
        "description": "Run a squad pipeline by name (outreach, seo, analytics, content, code, vision).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "squad_name": {"type": "string", "description": "Squad name, with or without '@...Squad' decoration"},
                "task": {"type": "string", "description": "Task for the squad"},
                "city": {"type": "string", "description": "City for outreach/local tasks"},
                "max_leads": {"type": "integer", "description": "Max leads for outreach squad"},
                "url": {"type": "string", "description": "URL for SEO/design squads"},
                "session_id": {"type": "string", "description": "Optional session ID"},
            },
            "required": ["squad_name", "task"],
        },
    },
    {
        "name": "outreach_scrape",
        "description": "Find local businesses without websites (lead discovery).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "region": {"type": "string"},
                "industry": {"type": "string"},
                "max_leads": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "outreach_enrich",
        "description": "Resolve email addresses for scraped leads via Hunter.io + domain inference.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "leads": {"type": "array", "items": {"type": "object"}, "description": "Lead objects from outreach_scrape"},
            },
            "required": ["leads"],
        },
    },
    {
        "name": "outreach_generate",
        "description": "Generate personalized cold emails for enriched leads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "leads": {"type": "array", "items": {"type": "object"}, "description": "Enriched lead objects"},
            },
            "required": ["leads"],
        },
    },
    {
        "name": "outreach_send",
        "description": "Send generated outreach emails via Resend. dry_run defaults to true (no delivery).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emails": {"type": "array", "items": {"type": "object"}, "description": "Email objects from outreach_generate"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["emails"],
        },
    },
    {
        "name": "outreach_pipeline",
        "description": "Full outreach pipeline: scrape -> enrich -> generate -> send (dry_run by default).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "max_leads": {"type": "integer", "default": 50},
                "dry_run": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "seo_analyze",
        "description": "Full SEO audit (on-page + technical + content) for a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "keyword": {"type": "string", "default": ""},
            },
            "required": ["url"],
        },
    },
    {
        "name": "seo_backlinks",
        "description": "Find backlink opportunities for a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "keyword": {"type": "string", "default": ""},
                "industry": {"type": "string", "default": ""},
                "city": {"type": "string", "default": "Vancouver"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "seo_pipeline",
        "description": "SEO audit + backlink analysis in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "keyword": {"type": "string", "default": ""},
                "industry": {"type": "string", "default": ""},
            },
            "required": ["url"],
        },
    },
    {
        "name": "design_concept",
        "description": "Research design trends and propose a website redesign concept.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "default": ""},
                "industry": {"type": "string", "default": ""},
                "city": {"type": "string", "default": "Vancouver"},
            },
        },
    },
    {
        "name": "health_check",
        "description": "Check 30-agent system health (Ollama, Redis, ChromaDB, registered agents).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "agent_chat":
            body: Dict[str, Any] = {
                "task": args["task"],
                "session_id": args.get("session_id"),
                "user_id": args.get("user_id", "mcp"),
            }
            if args.get("context") is not None:
                body["context"] = args["context"]
            return _tool_result(_request("POST", "/api/chat", body))

        if name == "list_agents":
            return _tool_result(_request("GET", "/api/agents"))

        if name == "list_squads":
            return _tool_result(_request("GET", "/api/squads"))

        if name == "run_squad":
            squad = args["squad_name"].strip().lower().removeprefix("@").removesuffix("squad")
            body: Dict[str, Any] = {"task": args["task"]}
            for key in ("session_id", "city", "max_leads", "url", "context"):
                if args.get(key) is not None:
                    body[key] = args[key]
            return _tool_result(_request("POST", f"/api/squads/{squad}/run", body))

        if name == "outreach_scrape":
            body = {k: args[k] for k in ("city", "region", "industry", "max_leads") if k in args}
            return _tool_result(_request("POST", "/api/outreach/scrape", body))

        if name == "outreach_enrich":
            return _tool_result(_request("POST", "/api/outreach/enrich", {"leads": args["leads"]}))

        if name == "outreach_generate":
            return _tool_result(_request("POST", "/api/outreach/generate", {"leads": args["leads"]}))

        if name == "outreach_send":
            return _tool_result(
                _request("POST", "/api/outreach/send", {"emails": args["emails"], "dry_run": args.get("dry_run", True)})
            )

        if name == "outreach_pipeline":
            query = {
                "city": args.get("city"),
                "max_leads": args.get("max_leads", 50),
                "dry_run": str(args.get("dry_run", True)).lower(),
            }
            return _tool_result(_request("POST", "/api/outreach/pipeline", query=query))

        if name == "seo_analyze":
            return _tool_result(
                _request("POST", "/api/seo/analyze", {"url": args["url"], "keyword": args.get("keyword", "")})
            )

        if name == "seo_backlinks":
            return _tool_result(
                _request(
                    "POST",
                    "/api/seo/backlinks",
                    {
                        "url": args["url"],
                        "keyword": args.get("keyword", ""),
                        "industry": args.get("industry", ""),
                        "city": args.get("city", "Vancouver"),
                    },
                )
            )

        if name == "seo_pipeline":
            query = {"url": args["url"], "keyword": args.get("keyword", ""), "industry": args.get("industry", "")}
            return _tool_result(_request("POST", "/api/seo/pipeline", query=query))

        if name == "design_concept":
            return _tool_result(
                _request(
                    "POST",
                    "/api/design/concept",
                    {"url": args.get("url", ""), "industry": args.get("industry", ""), "city": args.get("city", "Vancouver")},
                )
            )

        if name == "health_check":
            return _tool_result(_request("GET", "/api/health"))

        return _tool_result(f"Unknown tool: {name}", is_error=True)

    except Exception as e:
        return _tool_result(f"{type(e).__name__}: {e}", is_error=True)

# ---------------------------------------------------------------------------
# JSON-RPC handling
# ---------------------------------------------------------------------------

def _write(response: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if msg_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "30agents", "version": "1.1.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        try:
            result = call_tool(params.get("name", ""), params.get("arguments") or {})
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"prompts": []}}

    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def _stdio_loop() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}})
            continue
        try:
            response = _handle_message(msg)
        except Exception as e:
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}
        if response is not None:
            _write(response)

# ---------------------------------------------------------------------------
# API server lifecycle (Windows + POSIX)
# ---------------------------------------------------------------------------

def _api_is_up() -> bool:
    headers = {"X-API-Key": API_SECRET} if API_SECRET else {}
    req = urllib.request.Request(f"{API_BASE}/api/health", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return 200 <= resp.status < 500  # 401/403 still means the server is up
    except Exception:
        return False


def _spawn_server() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_DIR / "mcp_hub_server.log", "ab")
    port = urllib.parse.urlparse(API_BASE).port or 8000
    cmd = [sys.executable, "main.py", "serve", "--host", "127.0.0.1", "--port", str(port)]
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    else:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    log.info("spawned API server pid=%s", proc.pid)
    return int(proc.pid)


def _stop_server(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        log.info("stopped API server pid=%s", pid)
    except Exception as e:
        log.warning("failed to stop API server pid=%s: %s", pid, e)


def _ensure_server() -> Optional[int]:
    """Return pid we spawned (so caller can stop it), or None."""
    if _api_is_up():
        log.info("API already reachable at %s", API_BASE)
        return None
    if not AUTO_START:
        log.warning("API unreachable and AGENTS30_AUTO_START=0; tool calls will fail until the API is started")
        return None
    pid = _spawn_server()
    for _ in range(60):
        if _api_is_up():
            log.info("API ready at %s", API_BASE)
            return pid
        time.sleep(1)
    log.error("API server did not become ready within 60s; see %s", LOG_DIR / "mcp_hub_server.log")
    return pid

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_REQUIRED and not API_SECRET:
        log.error("AGENTS30_API_SECRET_REQUIRED=1 but no API key is configured")
        sys.exit(1)

    spawned_pid = _ensure_server()
    try:
        _stdio_loop()
    except KeyboardInterrupt:
        pass
    finally:
        if spawned_pid is not None and AUTO_STOP:
            _stop_server(spawned_pid)


if __name__ == "__main__":
    main()
