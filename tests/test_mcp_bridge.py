"""Unit tests for the Cursor MCP stdio bridge (no live server required)."""
from __future__ import annotations

import json
from unittest.mock import patch

import tools.mcp_bridge as bridge


def test_initialize_handshake():
    resp = bridge.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "30agents"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_includes_core_tools():
    resp = bridge.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    expected = {
        "agent_chat",
        "list_agents",
        "list_squads",
        "run_squad",
        "outreach_scrape",
        "outreach_enrich",
        "outreach_generate",
        "outreach_send",
        "outreach_pipeline",
        "seo_analyze",
        "seo_backlinks",
        "seo_pipeline",
        "design_concept",
        "health_check",
    }
    assert expected.issubset(names)


def test_notification_returns_none():
    resp = bridge.handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    )
    assert resp is None


def test_unknown_method_error():
    resp = bridge.handle_message({"jsonrpc": "2.0", "id": 9, "method": "nope/here"})
    assert resp["error"]["code"] == -32601


def test_health_check_tool_proxies_get():
    with patch.object(bridge, "_request", return_value={"status": "ok", "ollama": True}) as mock_req:
        result = bridge.call_tool("health_check", {})
    mock_req.assert_called_once_with("GET", "/api/health")
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "ok"


def test_agent_chat_tool_proxies_post():
    with patch.object(bridge, "_request", return_value={"result": "done"}) as mock_req:
        result = bridge.call_tool(
            "agent_chat",
            {"task": "summarize AGENTS.md", "user_id": "cursor"},
        )
    mock_req.assert_called_once_with(
        "POST",
        "/api/chat",
        {"task": "summarize AGENTS.md", "session_id": None, "user_id": "cursor"},
    )
    assert result["isError"] is False


def test_run_squad_normalizes_name():
    with patch.object(bridge, "_request", return_value={"squad_name": "outreach"}) as mock_req:
        bridge.call_tool(
            "run_squad",
            {"squad_name": "@OutreachSquad", "task": "find leads", "city": "Vancouver"},
        )
    mock_req.assert_called_once_with(
        "POST",
        "/api/squads/outreach/run",
        {"task": "find leads", "city": "Vancouver"},
    )


def test_outreach_pipeline_query_params():
    with patch.object(bridge, "_request", return_value={"stage": "complete"}) as mock_req:
        bridge.call_tool(
            "outreach_pipeline",
            {"city": "Vancouver", "max_leads": 10, "dry_run": True},
        )
    mock_req.assert_called_once_with(
        "POST",
        "/api/outreach/pipeline",
        query={"city": "Vancouver", "max_leads": 10, "dry_run": "true"},
    )


def test_api_unreachable_is_error_result():
    with patch.object(bridge, "_request", side_effect=RuntimeError("Cannot reach API")):
        result = bridge.call_tool("health_check", {})
    assert result["isError"] is True
    assert "Cannot reach API" in result["content"][0]["text"]
