# tests/test_entity_map_tool.py
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _tools(server):
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def _call(server, name, args):
    # FastMCP call_tool returns a tuple: ([TextContent(text=...)], <meta>)
    res = asyncio.run(server.mcp.call_tool(name, args))
    return json.loads(res[0][0].text)


def test_map_tool_registered_on_all_servers():
    import wb_mcp.server as wb
    import ozon_mcp.server as oz
    import ozon_perf_mcp.server as pf
    assert "wb_map" in _tools(wb)
    assert "ozon_map" in _tools(oz)
    assert "ozon_perf_map" in _tools(pf)


def test_map_overview_lists_entities_with_counts():
    import wb_mcp.server as wb
    payload = _call(wb, "wb_map", {})
    keys = {e["key"] for e in payload["entities"]}
    assert "reviews" in keys
    rev = next(e for e in payload["entities"] if e["key"] == "reviews")
    assert rev["method_count"] >= 1
    assert rev["title_ru"] and isinstance(rev["headline"], list)


def test_map_zoom_lists_methods_of_one_entity():
    import wb_mcp.server as wb
    payload = _call(wb, "wb_map", {"entity": "reviews"})
    assert payload["entity"] == "reviews"
    assert payload["methods"], "zoom should list reviews methods"
    assert all("reviews" in m.get("entity", []) for m in payload["methods"])


def test_describe_method_includes_entity_tag():
    import wb_mcp.server as wb
    review = next(s for s in wb.catalog.all() if "reviews" in s.entity)
    payload = _call(wb, "wb_describe_method", {"operation_id": review.operation_id})
    assert "reviews" in payload.get("entity", [])
