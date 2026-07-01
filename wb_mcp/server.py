#!/usr/bin/env python3
"""wb_mcp — MCP server for the Wildberries Seller API.

Exposes the whole WB Seller API through schema-driven meta-tools (search /
describe / call / fetch_all) plus a few typed convenience tools for the most
common manager tasks. Multi-host aware. Credentials come from the environment.

Auth: WB uses ONE token, sent in the `Authorization` header as the raw value
(no "Bearer " prefix). The token is scoped per category — a token must include
the category of the host it calls.

Run:
    WB_API_TOKEN=... python -m wb_mcp.server
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.entities import EntityIndex
from core.registry import Catalog
from core.tools import register_cabinet_tools, register_generic_tools
from core.workflows import Workflows, register_workflow_tools

CATALOG_PATH = Path(__file__).with_name("endpoints.yaml")
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    # Raw token, no "Bearer" prefix (per WB docs / community practice).
    return {"Authorization": creds.get("token", "")}


WB_CONFIG = ServiceConfig(
    name="wb",
    scheme="https",
    fields=["token"],
    env_map={"token": "WB_API_TOKEN"},
    build_headers=_build_headers,
    whoami=("wb_get_api_seller_info", ["name", "tradeMark"]),
    # WB is multi-host, but every host lives under wildberries.ru. Auth headers
    # (the raw seller token) may only ever be sent there.
    allowed_host_suffixes=[".wildberries.ru"],
)

mcp = FastMCP("wb_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(WB_CONFIG)

# Register the 8 generic schema-driven tools (wb_search_methods, wb_call_method, ...)
register_generic_tools(
    mcp, svc="wb", client=client, catalog=catalog, entities=entities,
    key_help="seller.wildberries.ru → Settings → Access tokens (one token, "
             "select the categories you need).",
)
register_cabinet_tools(mcp, svc="wb", client=client, catalog=catalog)
register_workflow_tools(mcp, svc="wb", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# --------------------------------------------------------------------------
# Typed convenience tools — the everyday manager workflows, one call each.
# They delegate to the same client; nothing is duplicated.
# --------------------------------------------------------------------------
@mcp.tool(
    name="wb_get_sales",
    annotations={"title": "WB sales & returns", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def wb_get_sales(date_from: str, flag: int = 0) -> str:
    """Get Wildberries sales and returns since a date (Statistics API, 1 req/min).

    Args:
        date_from: RFC3339 date/time in MSK, e.g. "2026-06-01" or "2026-06-01T00:00:00".
        flag: 0 = rows changed since date_from (incremental); 1 = rows dated on date_from.
    Returns JSON: {"ok": true, "status", "data": [ sale rows ]} or error envelope.
    Each row includes saleID, srid, nmId, totalPrice, forPay, lastChangeDate.
    """
    spec = catalog.get("wb_stats_sales")
    return _j(await client.call_spec(spec, query={"dateFrom": date_from, "flag": flag}))


@mcp.tool(
    name="wb_get_stocks",
    annotations={"title": "WB current stocks", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def wb_get_stocks(date_from: str = "2020-01-01") -> str:
    """Get the current Wildberries stock snapshot (Statistics API, 1 req/min).

    Stocks have no history — this is a point-in-time snapshot. Use an early
    date_from to get the full current set.

    Args:
        date_from: RFC3339 date; default "2020-01-01" returns everything in stock now.
    Returns JSON: {"ok": true, "data": [ stock rows ]} with quantity, warehouseName, nmId.
    """
    spec = catalog.get("wb_stats_stocks")
    return _j(await client.call_spec(spec, query={"dateFrom": date_from}))


@mcp.tool(
    name="wb_get_new_orders",
    annotations={"title": "WB new FBS orders", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def wb_get_new_orders() -> str:
    """Get new FBS assembly orders awaiting processing (Marketplace API).

    Returns JSON: {"ok": true, "data": {"orders": [...]}} — each order has id,
    rid, article, skus, createdAt, warehouseId.
    """
    spec = catalog.get("wb_fbs_orders_new")
    return _j(await client.call_spec(spec))


@mcp.tool(
    name="wb_get_prices",
    annotations={"title": "WB prices & discounts", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def wb_get_prices(limit: int = 1000, offset: int = 0,
                        filter_nm_id: Optional[int] = None) -> str:
    """Get current prices and discounts for products (Discounts-Prices API).

    Args:
        limit: page size (<=1000).
        offset: pagination offset.
        filter_nm_id: optional single nmID to filter by.
    Returns JSON: {"ok": true, "data": {"listGoods": [{nmID, sizes, discount, ...}]}}.
    """
    q = {"limit": min(limit, 1000), "offset": offset}
    if filter_nm_id is not None:
        q["filterNmID"] = filter_nm_id
    spec = catalog.get("wb_prices_list")
    return _j(await client.call_spec(spec, query=q))


@mcp.tool(
    name="wb_set_price",
    annotations={"title": "WB set price/discount", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False,
                 "openWorldHint": True},
)
async def wb_set_price(nm_id: int, price: int, discount: int = 0,
                       confirm_write: bool = False) -> str:
    """Set price and discount for ONE product (Discounts-Prices API). WRITE.

    Requires confirm_write=true (this changes your live price). A new price 3x
    below the old one lands the product in WB price quarantine.

    Args:
        nm_id: product nmID.
        price: new base price in rubles (integer).
        discount: discount percent (0-99).
        confirm_write: must be true to actually send the change.
    Returns JSON: {"ok": true, "data": {"id": uploadID}} — poll wb_prices_history_tasks.
    """
    from core.safety import check_gate
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=True,
                      operation_id="wb_set_price", endpoint="/api/v2/upload/task")
    if gate:
        return _j(gate)
    spec = catalog.get("wb_prices_set")
    body = {"data": [{"nmID": nm_id, "price": price, "discount": discount}]}
    return _j(await client.call_spec(spec, json_body=body))


def main() -> None:
    """Console entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
