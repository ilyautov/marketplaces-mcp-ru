#!/usr/bin/env python3
"""ozon_mcp — MCP server for the Ozon Seller API.

Exposes the whole Ozon Seller API through schema-driven meta-tools (search /
describe / call / fetch_all) plus typed convenience tools for everyday tasks.
Single host (api-seller.ozon.ru). Credentials come from the environment.

Auth: two flat headers — Client-Id and Api-Key.

Run:
    OZON_CLIENT_ID=... OZON_API_KEY=... python -m ozon_mcp.server
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.entities import EntityIndex
from core.registry import Catalog
from core.safety import check_gate
from core.tools import register_cabinet_tools, register_generic_tools
from core.workflows import Workflows, register_workflow_tools

CATALOG_PATH = Path(__file__).with_name("endpoints.yaml")
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    return {
        "Client-Id": creds.get("client_id", ""),
        "Api-Key": creds.get("api_key", ""),
        "Content-Type": "application/json",
    }


OZON_CONFIG = ServiceConfig(
    name="ozon",
    scheme="https",
    fields=["client_id", "api_key"],
    env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
    build_headers=_build_headers,
    # POST /v1/seller/info — exact name field not yet live-verified; we try a few
    # candidates and fall back gracefully if none match.
    whoami=("ozon_post_v1_seller_info",
            ["name", "company_name", "result.name", "result.company_name"]),
)

mcp = FastMCP("ozon_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(OZON_CONFIG)

register_generic_tools(
    mcp, svc="ozon", client=client, catalog=catalog, entities=entities,
    key_help="seller.ozon.ru → Settings → API keys (Client-Id + Api-Key).",
)
register_cabinet_tools(mcp, svc="ozon", client=client, catalog=catalog)
register_workflow_tools(mcp, svc="ozon", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# --------------------------------------------------------------------------
# Typed convenience tools — everyday workflows.
# --------------------------------------------------------------------------
@mcp.tool(
    name="ozon_get_products",
    annotations={"title": "Ozon product list", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ozon_get_products(visibility: str = "ALL", limit: int = 100,
                            last_id: str = "") -> str:
    """List Ozon products (one page).

    Args:
        visibility: ALL | VISIBLE | INVISIBLE | ARCHIVED | IN_SALE ...
        limit: page size (<=1000).
        last_id: cursor from a previous page (empty for first page).
    Returns JSON: {"ok": true, "data": {"result": {"items": [...], "last_id": "..."}}}.
    For every product across pages use ozon_fetch_all with ozon_product_list.
    """
    body = {"filter": {"visibility": visibility}, "limit": min(limit, 1000)}
    if last_id:
        body["last_id"] = last_id
    spec = catalog.get("ozon_product_list")
    return _j(await client.call_spec(spec, json_body=body))


@mcp.tool(
    name="ozon_get_stocks",
    annotations={"title": "Ozon stocks", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ozon_get_stocks(visibility: str = "ALL", limit: int = 100,
                          last_id: str = "") -> str:
    """Get available + reserved stock per product (v4/product/info/stocks).

    Args:
        visibility: product visibility filter (default ALL).
        limit: page size (<=1000).
        last_id: cursor for pagination.
    Returns JSON with stock per product (present, reserved) per warehouse type.
    """
    body = {"filter": {"visibility": visibility}, "limit": min(limit, 1000)}
    if last_id:
        body["last_id"] = last_id
    spec = catalog.get("ozon_stocks_info")
    return _j(await client.call_spec(spec, json_body=body))


@mcp.tool(
    name="ozon_get_prices",
    annotations={"title": "Ozon prices", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ozon_get_prices(visibility: str = "ALL", limit: int = 100,
                          cursor: str = "") -> str:
    """Get prices, commissions and price indexes per product (v5/product/info/prices).

    Args:
        visibility: product visibility filter (default ALL).
        limit: page size (<=1000).
        cursor: pagination cursor from a previous response.
    Returns JSON with price, marketing_seller_price, min_price, commissions, price_indexes.
    """
    body = {"filter": {"visibility": visibility}, "limit": min(limit, 1000)}
    if cursor:
        body["cursor"] = cursor
    spec = catalog.get("ozon_prices_get")
    return _j(await client.call_spec(spec, json_body=body))


@mcp.tool(
    name="ozon_get_fbs_unfulfilled",
    annotations={"title": "Ozon unfulfilled FBS orders", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ozon_get_fbs_unfulfilled(cutoff_from: str, cutoff_to: str,
                                   limit: int = 100, offset: int = 0) -> str:
    """List new/unprocessed FBS shipments awaiting assembly.

    Args:
        cutoff_from: ISO datetime lower bound, e.g. "2026-06-01T00:00:00Z".
        cutoff_to: ISO datetime upper bound.
        limit: page size.
        offset: pagination offset.
    Returns JSON: {"ok": true, "data": {"result": {"postings": [...]}}}.
    """
    body = {"filter": {"cutoff_from": cutoff_from, "cutoff_to": cutoff_to},
            "limit": limit, "offset": offset}
    spec = catalog.get("ozon_fbs_unfulfilled")
    return _j(await client.call_spec(spec, json_body=body))


@mcp.tool(
    name="ozon_set_price",
    annotations={"title": "Ozon set price", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": True,
                 "openWorldHint": True},
)
async def ozon_set_price(offer_id: str, price: str, old_price: str = "0",
                         min_price: str = "0", currency_code: str = "RUB",
                         confirm_write: bool = False) -> str:
    """Set the price for ONE product by offer_id (v1/product/import/prices). WRITE.

    Requires confirm_write=true. Ozon limits price updates to ~10/product/hour.
    Prices are strings. old_price="0" clears the strikethrough old price.

    Args:
        offer_id: seller's article (offer_id).
        price: new price as a string, e.g. "1499".
        old_price: pre-discount price as string, or "0" to clear.
        min_price: minimum price as string, or "0".
        currency_code: default "RUB".
        confirm_write: must be true to send.
    Returns JSON: {"ok": true, "data": {"result": [{"offer_id", "updated", "errors"}]}}.
    """
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=True,
                      operation_id="ozon_set_price",
                      endpoint="/v1/product/import/prices")
    if gate:
        return _j(gate)
    body = {"prices": [{
        "offer_id": offer_id, "price": price, "old_price": old_price,
        "min_price": min_price, "currency_code": currency_code,
    }]}
    spec = catalog.get("ozon_prices_update")
    return _j(await client.call_spec(spec, json_body=body))


def main() -> None:
    """Console entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
