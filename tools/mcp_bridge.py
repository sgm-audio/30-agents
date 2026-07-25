#!/usr/bin/env python3
"""
MCP stdio bridge — expose the 30-agent REST API as Cursor MCP tools.

Cursor (or any MCP client) spawns this process and speaks JSON-RPC 2.0 over
stdin/stdout. Each tool call is proxied to the local FastAPI server.

Environment:
  AGENTS30_API_BASE  Base URL for the 30-agent API (default: http://127.0.0.1:8000)
  AGENTS30_TIMEOUT   HTTP timeout seconds (default: 180)
  API_SECRET         Same value as the API server's API_SECRET (sent as X-API-Key)
  AGENTS30_API_SECRET  Alias for API_SECRET

Usage (manual test):
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python tools/mcp_bridge.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = os.environ.get("AGENTS30_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = float(os.environ.get("AGENTS30_TIMEOUT", "180"))


def _resolve_api_secret() -> str:
    secret = os.environ.get("AGENTS30_API_SECRET") or os.environ.get("API_SECRET") or ""
    if secret:
        return secret
    # Match server/CLI: fall back to project .env when MCP env is unset.
    try:
        from pathlib import Path
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env")
        return os.environ.get("AGENTS30_API_SECRET") or os.environ.get("API_SECRET") or ""
    except Exception:
        return ""


API_SECRET = _resolve_api_secret()

SERVER_NAME = "30agents"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


# ──────────────────────────────────────────────
# Tool definitions
# ──────────────────────────────────────────────
TOOLS: list[dict[str, Any]] = [
    {
        "name": "agent_chat",
        "description": (
            "Run a task through the 30-agent orchestrator (LangGraph). "
            "Use for general reasoning, coding, writing, research, and multi-step work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Natural-language task for the agents"},
                "session_id": {"type": "string", "description": "Optional session ID for continuity"},
                "user_id": {"type": "string", "description": "Optional user ID", "default": "cursor"},
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
        "description": "List available squad pipelines (Outreach, SEO, Analytics, Content, Code, Vision).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_squad",
        "description": (
            "Run a squad pipeline by name (outreach, seo, analytics, content, code, vision)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "squad_name": {
                    "type": "string",
                    "description": "Squad name: outreach | seo | analytics | content | code | vision",
                },
                "task": {"type": "string", "description": "Task for the squad"},
                "city": {"type": "string", "description": "City for outreach/local tasks"},
                "max_leads": {"type": "integer", "description": "Max leads for outreach squad"},
                "url": {"type": "string", "description": "URL for SEO/design squads"},
                "session_id": {"type": "string"},
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
                "city": {"type": "string", "description": "City to search (default from server config)"},
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
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Lead objects from outreach_scrape",
                },
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
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Enriched lead objects",
                },
            },
            "required": ["leads"],
        },
    },
    {
        "name": "outreach_send",
        "description": "Send generated outreach emails via Resend. Defaults to dry_run=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emails": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Email objects from outreach_generate",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, simulate send without delivering",
                },
            },
            "required": ["emails"],
        },
    },
    {
        "name": "outreach_pipeline",
        "description": "Full outreach pipeline: scrape → enrich → generate → send (dry_run by default).",
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
        "description": "Check 30-agent system health (Ollama, Redis, registered agents).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────
def _request(method: str, path: str, body: dict | None = None, query: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})}"

    data = None
    headers = {"Accept": "application/json"}
    if API_SECRET:
        headers["X-API-Key"] = API_SECRET
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach 30-agent API at {API_BASE}: {e.reason}. "
            "Start it with: python main.py serve"
        ) from e


def _tool_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


# ──────────────────────────────────────────────
# Tool handlers
# ──────────────────────────────────────────────
def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}
    try:
        if name == "agent_chat":
            body = {
                "task": args["task"],
                "session_id": args.get("session_id"),
                "user_id": args.get("user_id", "cursor"),
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
            body = {"task": args["task"]}
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
                _request(
                    "POST",
                    "/api/outreach/send",
                    {"emails": args["emails"], "dry_run": args.get("dry_run", True)},
                )
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
                _request(
                    "POST",
                    "/api/seo/analyze",
                    {"url": args["url"], "keyword": args.get("keyword", "")},
                )
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
            query = {
                "url": args["url"],
                "keyword": args.get("keyword", ""),
                "industry": args.get("industry", ""),
            }
            return _tool_result(_request("POST", "/api/seo/pipeline", query=query))

        if name == "design_concept":
            return _tool_result(
                _request(
                    "POST",
                    "/api/design/concept",
                    {
                        "url": args.get("url", ""),
                        "industry": args.get("industry", ""),
                        "city": args.get("city", "Vancouver"),
                    },
                )
            )

        if name == "health_check":
            return _tool_result(_request("GET", "/api/health"))

        return _tool_result(f"Unknown tool: {name}", is_error=True)
    except Exception as e:
        return _tool_result(f"{type(e).__name__}: {e}", is_error=True)


# ──────────────────────────────────────────────
# JSON-RPC / MCP protocol
# ──────────────────────────────────────────────
def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    # Notifications have no id — acknowledge silently
    if msg_id is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"prompts": []}}

    # Unknown method
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def _write(response: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    # Keep stderr for diagnostics; MCP clients only read stdout for protocol.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
            )
            continue

        try:
            response = handle_message(msg)
            if response is not None:
                _write(response)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            if msg.get("id") is not None:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "error": {"code": -32603, "message": "Internal error"},
                    }
                )


if __name__ == "__main__":
    main()
