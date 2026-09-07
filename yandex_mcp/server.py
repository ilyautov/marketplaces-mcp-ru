#!/usr/bin/env python3
"""yandex_mcp — MCP server for the Yandex Market Partner API (Яндекс Маркет).

Exposes the whole Partner API (api.partner.market.yandex.ru, 165 methods) through
schema-driven meta-tools (search / describe / call / fetch_all) plus typed
convenience tools for everyday seller tasks: shops, orders, offers, stocks, prices.

Auth: one header — ``Api-Key`` (Кабинет продавца → Настройки → Доступ к API).
Most methods take a ``campaignId`` (магазин) or ``businessId`` (кабинет);
``ym_get_campaigns`` returns both.

Catalog: yandex_mcp/endpoints.yaml, generated from the official OpenAPI spec
(github.com/yandex-market/yandex-market-partner-api) by scripts/ingest_openapi.py.

Run:
    YANDEX_MARKET_API_KEY=... python -m yandex_mcp.server
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
from core.transport import run as run_transport

CATALOG_PATH = Path(__file__).with_name("endpoints.yaml")
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    return {
        "Api-Key": creds.get("api_key", ""),
        "Content-Type": "application/json",
    }


YANDEX_CONFIG = ServiceConfig(
    name="yandex",
    scheme="https",
    fields=["api_key"],
    env_map={"api_key": "YANDEX_MARKET_API_KEY"},  # pragma: allowlist secret
    build_headers=_build_headers,
    # GET /v2/campaigns is the cheapest authenticated read; the shop name lives
    # inside a list (campaigns[0].domain), which the flat whoami digger cannot
    # reach — so the cabinet is named by the user, but the probe still works.
    whoami=("ym_get_campaigns", []),
    # The Api-Key may only be sent to Yandex Market hosts.
    allowed_host_suffixes=[".market.yandex.ru"],
)

mcp = FastMCP("yandex_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(YANDEX_CONFIG)

register_generic_tools(
    mcp, svc="ym", client=client, catalog=catalog, entities=entities,
    key_help="partner.market.yandex.ru → Настройки → Доступ к API → Api-Key.",
)
register_cabinet_tools(mcp, svc="ym", client=client, catalog=catalog)
register_workflow_tools(mcp, svc="ym", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _paging(page_token: str, limit: int, ceiling: int) -> dict:
    q: dict = {"limit": max(1, min(limit, ceiling))}
    if page_token:
        q["pageToken"] = page_token
    return q


# --------------------------------------------------------------------------
# Typed convenience tools — everyday workflows.
# --------------------------------------------------------------------------
@mcp.tool(
    name="ym_get_campaigns",
    annotations={"title": "Yandex Market shops (campaigns)", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ym_get_campaigns(page_token: str = "", limit: int = 50) -> str:
    """List the seller's shops (кампании) with their campaignId and businessId.

    Call this first: nearly every other Yandex Market method needs a campaignId
    (магазин) or businessId (кабинет продавца). Both are in the response:
    campaigns[].id and campaigns[].business.id.

    Args:
        page_token: pageToken from a previous page (empty for the first page).
        limit: page size (<=100).
    Returns JSON: {"ok": true, "data": {"campaigns": [...], "paging": {...}}}.
    """
    spec = catalog.get("ym_get_campaigns")
    return _j(await client.call_spec(spec, query=_paging(page_token, limit, 100)))


@mcp.tool(
    name="ym_get_orders",
    annotations={"title": "Yandex Market orders", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ym_get_orders(campaign_id: int, status: str = "", from_date: str = "",
                        to_date: str = "", page_token: str = "", limit: int = 50) -> str:
    """List orders of one shop (GET /v2/campaigns/{campaignId}/orders).

    Args:
        campaign_id: shop id from ym_get_campaigns.
        status: filter, e.g. PROCESSING | DELIVERY | PICKUP | DELIVERED |
            CANCELLED | UNPAID (comma-separated allowed). Empty = all.
        from_date: order creation date lower bound, DD-MM-YYYY (Yandex format).
        to_date: upper bound, DD-MM-YYYY.
        page_token: pageToken from a previous page.
        limit: page size (<=50).
    Returns JSON: {"ok": true, "data": {"orders": [...], "paging": {...}}}.
    For every order across pages use ym_fetch_all with ym_get_orders.
    """
    q = _paging(page_token, limit, 50)
    if status:
        q["status"] = status
    if from_date:
        q["fromDate"] = from_date
    if to_date:
        q["toDate"] = to_date
    spec = catalog.get("ym_get_orders")
    return _j(await client.call_spec(spec, path_values={"campaignId": campaign_id}, query=q))


@mcp.tool(
    name="ym_get_offers",
    annotations={"title": "Yandex Market offers (catalog)", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ym_get_offers(business_id: int, offer_ids: str = "", page_token: str = "",
                        limit: int = 100) -> str:
    """List the seller's offers (товары) with their Market card mapping
    (POST /v2/businesses/{businessId}/offer-mappings).

    Args:
        business_id: cabinet id (campaigns[].business.id).
        offer_ids: comma-separated offerId (SKU) filter; empty = all.
        page_token: pageToken from a previous page.
        limit: page size (<=200).
    Returns JSON: {"ok": true, "data": {"result": {"offerMappings": [...], "paging": {...}}}}.
    """
    body: dict = {}
    if offer_ids:
        body["offerIds"] = [s.strip() for s in offer_ids.split(",") if s.strip()]
    spec = catalog.get("ym_get_offer_mappings")
    return _j(await client.call_spec(
        spec, path_values={"businessId": business_id},
        query=_paging(page_token, limit, 200), json_body=body))


@mcp.tool(
    name="ym_get_stocks",
    annotations={"title": "Yandex Market stocks", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ym_get_stocks(campaign_id: int, offer_ids: str = "", with_turnover: bool = False,
                        page_token: str = "", limit: int = 100) -> str:
    """Stock per offer per warehouse for one shop, with optional turnover
    (POST /v2/campaigns/{campaignId}/offers/stocks).

    Args:
        campaign_id: shop id.
        offer_ids: comma-separated offerId filter; empty = all.
        with_turnover: also return turnover (оборачиваемость) per offer.
        page_token: pageToken from a previous page.
        limit: page size (<=200).
    Returns JSON: {"ok": true, "data": {"result": {"warehouses": [{"warehouseId", "offers": [...]}]}}}.
    """
    body: dict = {"withTurnover": with_turnover}
    if offer_ids:
        body["offerIds"] = [s.strip() for s in offer_ids.split(",") if s.strip()]
    spec = catalog.get("ym_get_stocks")
    return _j(await client.call_spec(
        spec, path_values={"campaignId": campaign_id},
        query=_paging(page_token, limit, 200), json_body=body))


@mcp.tool(
    name="ym_get_prices",
    annotations={"title": "Yandex Market prices", "readOnlyHint": True,
                 "openWorldHint": True},
)
async def ym_get_prices(business_id: int, offer_ids: str = "", page_token: str = "",
                        limit: int = 100) -> str:
    """Base prices set for all shops of the cabinet
    (POST /v2/businesses/{businessId}/offer-prices).

    Args:
        business_id: cabinet id.
        offer_ids: comma-separated offerId filter; empty = all.
        page_token: pageToken from a previous page.
        limit: page size (<=200).
    Returns JSON with result.offers[].price {value, currencyId, discountBase, updatedAt}.
    """
    body: dict = {}
    if offer_ids:
        body["offerIds"] = [s.strip() for s in offer_ids.split(",") if s.strip()]
    spec = catalog.get("ym_get_default_prices")
    return _j(await client.call_spec(
        spec, path_values={"businessId": business_id},
        query=_paging(page_token, limit, 200), json_body=body))


@mcp.tool(
    name="ym_set_price",
    annotations={"title": "Yandex Market set price", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": True,
                 "openWorldHint": True},
)
async def ym_set_price(business_id: int, offer_id: str, price: float,
                       discount_base: float = 0, currency: str = "RUR",
                       confirm_write: bool = False) -> str:
    """Set the base price of ONE offer for all shops of the cabinet
    (POST /v2/businesses/{businessId}/offer-prices/updates). WRITE.

    Requires confirm_write=true. discount_base is the strikethrough price
    (must be higher than price); 0 = no discount shown.

    Args:
        business_id: cabinet id.
        offer_id: seller's SKU (offerId).
        price: new price, e.g. 1499.
        discount_base: pre-discount price, or 0 to clear.
        currency: RUR (default) — Yandex uses "RUR", not "RUB".
        confirm_write: must be true to send.
    Returns JSON: {"ok": true, "data": {"status": "OK"}} on success.
    """
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=True,
                      operation_id="ym_set_price",
                      endpoint="/v2/businesses/{businessId}/offer-prices/updates")
    if gate:
        return _j(gate)
    price_obj: dict = {"value": price, "currencyId": currency}
    if discount_base:
        price_obj["discountBase"] = discount_base
    body = {"offers": [{"offerId": offer_id, "price": price_obj}]}
    spec = catalog.get("ym_update_business_prices")
    return _j(await client.call_spec(spec, path_values={"businessId": business_id},
                                     json_body=body))


def main() -> None:
    """Console entry point: stdio by default, HTTP with MCP_TRANSPORT=http."""
    run_transport(mcp)


if __name__ == "__main__":
    main()
