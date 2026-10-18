"""The public MCP server over HTTP: an MCP client can list the read-only tools and call the gate; no write tool is exposed."""
import json

import pytest
from fastapi.testclient import TestClient

from moot import api
from moot.graph import connect

H = {"accept": "application/json, text/event-stream", "content-type": "application/json", "mcp-protocol-version": "2025-06-18"}


def rpc(c, method, params=None, i=1):
    r = c.post("/mcp/", headers=H, json=dict(jsonrpc="2.0", id=i, method=method, params=params or {}))
    assert r.status_code == 200, r.text
    return r.json()


def test_public_mcp_lists_only_read_tools_and_answers_the_gate():
    try:
        connect().connection.ping()
    except Exception:
        pytest.skip("FalkorDB not reachable")
    with TestClient(api.app) as c:
        rpc(c, "initialize", dict(protocolVersion="2025-06-18", capabilities={}, clientInfo=dict(name="test", version="0")))
        names = {t["name"] for t in rpc(c, "tools/list", i=2)["result"]["tools"]}
        assert "check_action" in names and "audit_decision" in names
        assert not names & {"record_finding", "record_ruling", "record_handover", "ingest_github", "ask"}
        res = rpc(c, "tools/call", dict(name="check_action", arguments=dict(decision_id="D01", as_of="2026-10-16")), i=3)["result"]
        body = json.loads(res["content"][0]["text"])
        assert body["gate"] == "DENY"
