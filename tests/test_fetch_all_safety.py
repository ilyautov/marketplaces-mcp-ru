"""fetch_all must honour the same verb-floor as call_method.

Regression: fetch_all_tool checked only the raw `spec.safety`, so a mutating
verb mislabelled `read` in the catalog (PUT/PATCH/DELETE) would be executed in a
pagination loop with NO confirmation. call_method already floors by verb via
infer_safety; fetch_all must too. Also pins the end-to-end gate through the MCP
tool layer (not just the check_gate unit).
"""
from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.registry import Catalog, EndpointSpec
from core.tools import register_generic_tools


def _call(mcp, name, args):
    res = asyncio.run(mcp.call_tool(name, args))
    return json.loads(res[0][0].text)


def _server():
    specs = [
        # mislabelled: DELETE declared "read" — must still be gated/refused.
        EndpointSpec(operation_id="bad_delete", method="DELETE",
                     host="api-seller.ozon.ru", path="/v1/del", safety="read"),
        EndpointSpec(operation_id="real_write", method="POST",
                     host="api-seller.ozon.ru", path="/v1/write", safety="write"),
        EndpointSpec(operation_id="real_read", method="GET",
                     host="api-seller.ozon.ru", path="/v1/read", safety="read"),
    ]
    catalog = Catalog(specs, default_host="api-seller.ozon.ru")
    cfg = ServiceConfig(
        name="ozon", scheme="https", fields=["client_id", "api_key"],
        env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
        build_headers=lambda c: {}, allowed_host_suffixes=[".ozon.ru"])
    mcp = FastMCP("test")
    register_generic_tools(mcp, svc="ozon", client=MarketplaceClient(cfg),
                           catalog=catalog)
    return mcp


def test_fetch_all_refuses_mislabelled_mutating_endpoint():
    out = _call(_server(), "ozon_fetch_all", {"operation_id": "bad_delete"})
    assert out.get("error") == "invalid_params"
    assert "read" in out.get("message", "").lower()


def test_fetch_all_refuses_declared_write_endpoint():
    out = _call(_server(), "ozon_fetch_all", {"operation_id": "real_write"})
    assert out.get("error") == "invalid_params"


def test_call_method_gates_write_without_confirm(monkeypatch):
    monkeypatch.delenv("OZON_CLIENT_ID", raising=False)
    monkeypatch.delenv("OZON_API_KEY", raising=False)
    out = _call(_server(), "ozon_call_method", {"operation_id": "real_write"})
    assert out["error_type"] == "safety_gate"
    assert out["details"]["http_call_skipped"] is True


def test_call_method_verb_floor_gates_mislabelled_delete():
    out = _call(_server(), "ozon_call_method", {"operation_id": "bad_delete"})
    # DELETE floored to (at least) write despite the catalog's "read".
    assert out["error_type"] == "safety_gate"
